import torch



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
        # print(self.states[idx]['hand'].shape, self.states[idx]['context'].shape, self.states[idx]['previous']['hand1'].shape, self.states[idx]['previous']['hand2'].shape, self.states[idx]['previous']['hand3'].shape, self.states[idx]['previous']['played_cards'].shape, 'states[idx]')
        assert(self.states[idx] is not None), "State at index {} is None".format(idx)
        assert(self.action_log_probs[idx] is not None), "Action log prob at index {} is None".format(idx)
        assert(self.returns[idx] is not None), "Return at index {} is None".format(idx)
        assert(self.advantages[idx] is not None), "Advantage at index {} is None".format(idx)
        assert(self.actions[idx] is not None), "Action at index {} is None".format(idx)
        return (self.states[idx], self.actions[idx], self.action_log_probs[idx], self.returns[idx], self.advantages[idx])