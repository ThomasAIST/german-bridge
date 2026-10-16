"""Check rollout value ordering, padding, and real notebook training."""

import contextlib
import copy
import io
from pathlib import Path
import unittest

import torch

from dataset import CustomDataset
from profile_train import load_notebook_training
from training_collection import evaluate_critic_values


def observation(marker, length):
    cards = torch.zeros(length, 52)
    cards[torch.arange(length), torch.arange(length)] = 1
    return {
        'hand': cards,
        'context': torch.tensor([float(marker)] + [0.0] * 19),
        'previous': {
            'hand1': torch.full((1, 52), -1.0),
            'hand2': cards.clone(),
            'hand3': torch.full((1, 52), -1.0),
            'played_cards': cards.clone(),
        },
        'phase': 1, 'round': length, 'fixed_suit': -1, 'triumph_suit': -1,
        'own hand': list(range(length)), 'players bids': [0, 1],
        'action_mask': torch.ones(66, dtype=torch.bool),
    }


class RecordingCritic(torch.nn.Module):
    def __init__(self):
        super().__init__()
        self.scale = torch.nn.Parameter(torch.tensor(2.0))
        self.calls = []

    def forward(self, state, device=None):
        self.calls.append((self.training, torch.is_grad_enabled(), len(state['hand'])))
        return state['context'][:, 0] * self.scale


class CollectionValueTests(unittest.TestCase):
    def test_values_preserve_order_use_partial_batch_and_restore_mode(self):
        critic = RecordingCritic()
        states = [observation(i, i % 3 + 1) for i in [4, 1, 3, 0, 2]]
        callbacks = []
        values = evaluate_critic_values(critic, states, batch_size=2,
                                        on_batch=lambda: callbacks.append(True))
        torch.testing.assert_close(values, torch.tensor([8., 2., 6., 0., 4.]))
        self.assertFalse(values.requires_grad)
        self.assertEqual(critic.calls, [(False, False, 2), (False, False, 2), (False, False, 1)])
        self.assertEqual(len(callbacks), 3)
        self.assertTrue(critic.training)
        critic.eval()
        evaluate_critic_values(critic, states, batch_size=10)
        self.assertFalse(critic.training)

    def test_mode_is_restored_after_callback_failure(self):
        critic = RecordingCritic()

        def fail():
            raise RuntimeError('stop evaluation')

        with self.assertRaisesRegex(RuntimeError, 'stop evaluation'):
            evaluate_critic_values(critic, [observation(0, 1)], on_batch=fail)
        self.assertTrue(critic.training)

    def test_collation_does_not_pad_stored_observations(self):
        states = [observation(0, 1), observation(1, 4)]
        original = copy.deepcopy(states)
        batched = CustomDataset.collate_states(states)
        self.assertEqual(tuple(batched['hand'].shape), (2, 4, 52))
        self.assertTrue(batched['hand'][0, 1:].eq(-1).all())
        CustomDataset.collate_states(states[::-1])
        for state, before in zip(states, original):
            for key in state:
                if key == 'previous':
                    for subkey in state[key]:
                        torch.testing.assert_close(state[key][subkey], before[key][subkey])
                elif isinstance(state[key], torch.Tensor):
                    torch.testing.assert_close(state[key], before[key])
                else:
                    self.assertEqual(state[key], before[key])

    def test_collate_keeps_advantages_and_returns_in_notebook_order(self):
        dataset = CustomDataset([observation(0, 1)], torch.tensor([14]),
                                torch.tensor([-0.5]), torch.tensor([7.]), torch.tensor([-2.]))
        _, actions, logs, advantages, returns = CustomDataset.collate_fn([dataset[0]])
        torch.testing.assert_close(advantages, torch.tensor([-2.]))
        torch.testing.assert_close(returns, torch.tensor([7.]))


class NotebookCollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old_threads = torch.get_num_threads()
        torch.set_num_threads(1)
        cls.namespace = load_notebook_training(Path(__file__).with_name('train.ipynb'))

    @classmethod
    def tearDownClass(cls):
        torch.set_num_threads(cls.old_threads)

    def test_encoder_handles_empty_histories_and_padding_invariant_pooling(self):
        encoder = self.namespace['HandEncoder'](52, 32, 8, 4, 1)
        encoder.eval()
        hand = observation(0, 2)['hand']
        padded = torch.cat([hand, torch.full((3, 52), -1.0)])
        with torch.no_grad():
            torch.testing.assert_close(encoder(hand), encoder(padded), atol=1e-6, rtol=1e-5)
            encoded = encoder(torch.full((3, 4, 52), -1.0))
        torch.testing.assert_close(encoded, torch.zeros(3, 8))
        encoder.train()
        encoder(torch.stack([padded, torch.full_like(padded, -1)])).sum().backward()
        self.assertTrue(all(parameter.grad is None or torch.isfinite(parameter.grad).all()
                            for parameter in encoder.parameters()))

    def test_real_critic_matches_individual_evaluation(self):
        critic = self.namespace['critic_model']
        context_dim = critic.context_encoder.mlp[0].in_features
        states = [observation(i, length) for i, length in enumerate([1, 4, 2, 3, 1])]
        for state in states:
            state['context'] = torch.zeros(context_dim)
        individual = evaluate_critic_values(critic, states, batch_size=1, device='cpu')
        batched = evaluate_critic_values(critic, states, batch_size=3, device='cpu')
        self.assertTrue(torch.isfinite(batched).all())
        torch.testing.assert_close(individual, batched, atol=1e-6, rtol=1e-5)

    def test_full_episode_batches_targets_and_still_updates_both_models(self):
        ns = self.namespace
        actor, critic = ns['actor_model'], ns['critic_model']
        actor.eval()  # train() must reactivate the RNN before any update forward.
        critic.eval()
        actor_before = next(actor.parameters()).detach().clone()
        critic_before = next(critic.parameters()).detach().clone()
        env = ns['GermanBridgeGameEnv']()
        calls = []
        actor_calls = []
        handle = critic.register_forward_pre_hook(
            lambda model, args: calls.append((model.training, torch.is_grad_enabled(), len(args[0]['hand']))))
        actor_handle = actor.register_forward_pre_hook(
            lambda model, args: actor_calls.append((model.training, model.previous_encoder.lstm.training,
                                                    torch.is_grad_enabled())))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                ns['train'](actor, critic, None, None,
                            torch.optim.Adam(actor.parameters(), lr=0.001),
                            torch.optim.Adam(critic.parameters(), lr=0.001), env,
                            episode=1, epoch=2, batch_size=32, device='cpu',
                            critic_batch_size=32, shuffle_minibatches=True)
        finally:
            handle.remove()
            actor_handle.remove()
            env.close()
        self.assertEqual(calls[:4], [(False, False, 32)] * 3 + [(False, False, 8)])
        self.assertEqual(len(calls), 4 + 2 * 4)
        self.assertTrue(all(training and grad for training, grad, size in calls[4:]))
        self.assertEqual(actor_calls[:104], [(True, True, False)] * 104)
        self.assertEqual(actor_calls[104:], [(True, True, True)] * 8)
        self.assertEqual(len(env.episode_history), 1)
        self.assertFalse(torch.equal(actor_before, next(actor.parameters())))
        self.assertFalse(torch.equal(critic_before, next(critic.parameters())))
        for model in (actor, critic):
            self.assertTrue(all(torch.isfinite(parameter).all() for parameter in model.parameters()))

        # Attention has its own dropout setting, separate from nn.Dropout.
        for layer in actor.modules():
            if isinstance(layer, torch.nn.Dropout):
                self.assertEqual(layer.p, 0.0)
            elif isinstance(layer, (torch.nn.MultiheadAttention, torch.nn.LSTM)):
                self.assertEqual(layer.dropout, 0.0)
        self.assertTrue(any(layer.p > 0 for layer in critic.modules()
                            if isinstance(layer, torch.nn.Dropout)))

        state = observation(0, 3)
        state['context'] = torch.zeros(actor.context_encoder.mlp[0].in_features)
        with torch.no_grad():
            old_dist = torch.distributions.Categorical(probs=actor(state, device='cpu').softmax(-1))
            action = old_dist.sample()
            old_log_prob = old_dist.log_prob(action)
        new_logits = actor(state, device='cpu')
        self.assertTrue(new_logits.requires_grad)
        new_dist = torch.distributions.Categorical(probs=new_logits.softmax(-1))
        ratio = (new_dist.log_prob(action) - old_log_prob).exp()
        torch.testing.assert_close(ratio, torch.ones_like(ratio), atol=1e-6, rtol=1e-6)

    @unittest.skipUnless(torch.cuda.is_available() and torch.backends.cudnn.is_available()
                         and torch.backends.cudnn.enabled, 'CUDA/cuDNN is required')
    def test_cuda_rnn_backward_uses_training_mode(self):
        with contextlib.redirect_stdout(io.StringIO()):
            ns = load_notebook_training(Path(__file__).with_name('train.ipynb'), device='cuda')
        actor, critic = ns['actor_model'].cuda(), ns['critic_model'].cuda()
        actor.eval()
        critic.eval()
        env = ns['GermanBridgeGameEnv']()
        rnn_calls = []
        handle = actor.previous_encoder.lstm.register_forward_pre_hook(
            lambda model, args: rnn_calls.append((model.training, torch.is_grad_enabled(),
                                                  args[0].data.is_cuda)))
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                ns['train'](actor, critic, None, None,
                            torch.optim.Adam(actor.parameters(), lr=0.001),
                            torch.optim.Adam(critic.parameters(), lr=0.001), env,
                            episode=1, epoch=1, batch_size=32, device='cuda',
                            critic_batch_size=32, shuffle_minibatches=True)
            torch.cuda.synchronize()
        finally:
            handle.remove()
            env.close()
        self.assertEqual(rnn_calls[:104], [(True, False, True)] * 104)
        self.assertEqual(rnn_calls[104:], [(True, True, True)] * 4)
        self.assertTrue(actor.training)
        self.assertTrue(critic.training)
        for model in (actor, critic):
            self.assertTrue(all(torch.isfinite(parameter).all() for parameter in model.parameters()))


if __name__ == '__main__':
    unittest.main()
