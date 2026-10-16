"""Evaluate rollout values in batches before updating the PPO models."""

import torch

from dataset import CustomDataset


@torch.no_grad()
def evaluate_critic_values(critic_model, states, *, batch_size=32, device=None,
                           on_batch=None):
    """Return detached values in episode order, restoring the critic's mode."""
    if not states:
        raise ValueError('Cannot evaluate an empty episode.')
    if batch_size < 1:
        raise ValueError('Critic batch size must be at least 1.')

    was_training = critic_model.training
    critic_model.eval()  # Disable dropout for the fixed value targets.
    try:
        values = []
        for start in range(0, len(states), batch_size):
            batch = CustomDataset.collate_states(states[start:start + batch_size])
            values.append(critic_model(batch, device=device).reshape(-1))
            if on_batch is not None:
                on_batch()
        return torch.cat(values)
    finally:
        critic_model.train(was_training)
