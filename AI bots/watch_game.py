"""Preview the training observer using random actions, without loading a model."""

import argparse
import random

from germanbridgegameenv import GermanBridgeGameEnv


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--episodes", type=int, default=1)
    parser.add_argument("--delay", type=float, default=0.25)
    parser.add_argument("--charts-only", action="store_true")
    args = parser.parse_args()
    env = GermanBridgeGameEnv(render_mode="human", render_delay=args.delay,
                              charts_only=args.charts_only)
    try:
        env.start_training_timer()
        for episode in range(1, args.episodes + 1):
            env.set_training_progress(episode=episode, total_episodes=args.episodes,
                                      phase="Data collection")
            state, _ = env.reset()
            done, steps, total_reward = False, 0, 0
            while not done:
                if env.bidding_stage:
                    action = random.randint(0, env.round)
                else:
                    hand = state["own hand"]
                    lead = state["fixed_suit"]
                    # Match the legal-card mask currently used by the training policy.
                    follows = any(card // 13 == lead for card in hand)
                    legal = [card for card in hand if not follows or
                             card // 13 in (lead, env.triumph_suit)]
                    action = 14 + random.choice(legal)
                state, reward, terminated, truncated, _ = env.step(action)
                done = terminated or truncated
                steps += 1
                total_reward += reward
                env.set_training_progress(steps=steps, episode_reward=total_reward,
                                          last_reward=reward)
            env.record_episode_reward(total_reward)
            env.finish_training_episode()
        # Leave the final scores visible until the preview window is closed.
        env.finish_training(phase="Preview complete")
        if env._gui is not None and not env._gui.closed:
            env._gui.root.mainloop()
    finally:
        env.close()


if __name__ == "__main__":
    main()
