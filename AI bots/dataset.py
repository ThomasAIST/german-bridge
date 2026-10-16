import torch
from torch.nn.utils.rnn import pad_sequence


class CustomDataset(torch.utils.data.Dataset):
    def __init__(self, states, actions, action_log_probs, returns, advantages):
        self.states = states
        self.actions = actions
        self.action_log_probs = action_log_probs
        self.returns = returns
        self.advantages = advantages

    def __len__(self):
        return len(self.states)

    def __getitem__(self, idx):
        return (self.states[idx], self.actions[idx], self.action_log_probs[idx], self.returns[idx], self.advantages[idx])

    @staticmethod
    def collate_states(states):
        """Right-pad observations without changing the stored episode states."""
        batch_state = {}
        for key, first in states[0].items():
            if key == 'previous':
                batch_state[key] = {
                    subkey: pad_sequence(
                        [state[key][subkey] for state in states],
                        batch_first=True, padding_value=-1)
                    for subkey in first
                }
            elif key == 'hand':
                batch_state[key] = pad_sequence(
                    [state[key] for state in states],
                    batch_first=True, padding_value=-1)
            elif isinstance(first, torch.Tensor):
                batch_state[key] = torch.stack([state[key] for state in states])
            elif isinstance(first, list):
                width = max(len(state[key]) for state in states)
                batch_state[key] = torch.tensor([
                    state[key] + [-1] * (width - len(state[key]))
                    for state in states
                ])
            else:
                batch_state[key] = torch.tensor([state[key] for state in states])
        return batch_state

    @staticmethod
    def collate_fn(batch):
        states, actions, action_log_probs, returns, advantages = zip(*batch)
        # Keep the notebook's existing public batch order: advantages, returns.
        return (CustomDataset.collate_states(states), torch.stack(actions),
                torch.stack(action_log_probs), torch.stack(advantages),
                torch.stack(returns))
