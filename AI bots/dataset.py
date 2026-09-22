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
        # assert(self.states[idx] is not None), "State at index {} is None".format(idx)
        # assert(self.action_log_probs[idx] is not None), "Action log prob at index {} is None".format(idx)
        # assert(self.returns[idx] is not None), "Return at index {} is None".format(idx)
        # assert(self.advantages[idx] is not None), "Advantage at index {} is None".format(idx)
        # assert(self.actions[idx] is not None), "Action at index {} is None".format(idx) 
        return (self.states[idx], self.actions[idx], self.action_log_probs[idx], self.returns[idx], self.advantages[idx])

    @staticmethod
    def collate_fn(batch):
        states, actions, action_log_probs, returns, advantages = zip(*batch)
        max_hand_length = max(x['hand'].shape[0] for x in states)
        max_previous_hand_length = max(max(x['previous']['hand1'].shape[0], x['previous']['hand2'].shape[0], x['previous']['hand3'].shape[0]) for x in states)
        max_previous_played_cards_length = max(x['previous']['played_cards'].shape[0] for x in states)
        for i in range(len(states)):
            if states[i]['hand'].shape[0] < max_hand_length:
                states[i]['hand'] = torch.cat((states[i]['hand'], torch.full((max_hand_length - states[i]['hand'].shape[0], 52), -1, dtype=torch.float32)), dim=0)
            for j in range(1, 4):
                if states[i]['previous'][f'hand{j}'].shape[0] < max_previous_hand_length:
                    states[i]['previous'][f'hand{j}'] = torch.cat((states[i]['previous'][f'hand{j}'], torch.full((max_previous_hand_length - states[i]['previous'][f'hand{j}'].shape[0], 52), -1, dtype=torch.float32)), dim=0)
            if states[i]['previous']['played_cards'].shape[0] < max_previous_played_cards_length:
                states[i]['previous']['played_cards'] = torch.cat((states[i]['previous']['played_cards'], torch.full((max_previous_played_cards_length - states[i]['previous']['played_cards'].shape[0], 52), -1, dtype=torch.float32)), dim=0)

        batch_state = {}
        for key in states[0].keys():
            if key == 'previous':
                batch_state[key] = {}
                for subkey in states[0][key].keys():
                    batch_state[key][subkey] = torch.stack([state[key][subkey] for state in states])
            else:
                if isinstance(states[0][key], torch.Tensor):
                    batch_state[key] = torch.stack([state[key] for state in states])
                elif isinstance(states[0][key], list):
                    # print([state[key] for state in states], 'state[key] for state in states')
                    max_length = max(len(state[key]) for state in states)
                    
                    for i in range(len(states)):
                        if len(states[i][key]) < max_length:
                            states[i][key] = states[i][key] + [-1] * (max_length - len(states[i][key]))
                    # print([state[key] for state in states], 'state[key] for state in states')
                    batch_state[key] = torch.tensor([state[key] for state in states])
                else:
                    batch_state[key] = torch.tensor([state[key] for state in states])

        actions = torch.cat([action.unsqueeze(0) for action in actions], dim=0)
        action_log_probs = torch.cat([log_prob.unsqueeze(0) for log_prob in action_log_probs], dim=0)
        returns = torch.cat([ret.unsqueeze(0) for ret in returns], dim=0)
        advantages = torch.cat([adv.unsqueeze(0) for adv in advantages], dim=0)

        return batch_state, actions, action_log_probs, returns, advantages