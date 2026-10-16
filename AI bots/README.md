# Training observer

Run `train.ipynb` using the `german_bridge` Python kernel. The **GUI settings**
section at the very top contains `show_gui = True`. Re-run the settings, imports,
`train` function, and final cell after updating the files (or restart the kernel).

The same settings cell also contains `charts_only = True`, the default for fast
training with charts. With `show_gui = True`, this displays score, rank, and
reward charts plus training metrics, without rendering the game or adding
playback delays. Routine progress updates are limited to four per second;
episode results refresh immediately. Set `charts_only = False` for the full
game viewer. `show_gui = False` disables both GUI modes.

The window shows every player's hand, bid, tricks won, cumulative score, the
current turn, trump suit, current and previous tricks, and a recent-action log.
The sidebar shows the episode, collected samples, last reward, and episode reward.
It also shows total training time as `HH:MM:SS` and the average seconds per fully
completed episode. Timing starts when `train()` begins and includes data
collection, model updates, playback delays, and pauses. The average appears
after the first episode's model updates finish and excludes the current
unfinished episode. Counters persist across episode resets and restart for a
new training run. The elapsed counter updates while the viewer is paused.
Training information updates in place as a three-line block in notebooks and
terminals: episode/phase; samples/rewards; average episode time/total elapsed
time. It also works when the GUI is disabled. Updates are throttled to four per second during a phase, with
immediate updates at phase changes and completion. The final status remains
visible; a terminal adds a newline at the end so later output stays separate.
One full game contains 104 agent decisions: 13 bids and 91 card plays.

The main training cell exposes `critic_batch_size = 32` and
`shuffle_minibatches = True`. Rollout collection runs only the Actor; once the
episode finishes, the Critic evaluates observations in their original order,
before either model is updated. At size 32, 104 decisions require four Critic
calls for these fixed value targets. Critic dropout is disabled for target
evaluation and restored for optimization. Update minibatches reshuffle every
epoch when `shuffle_minibatches` is true. The LSTM processes each observation's
own history, so shuffling observations does not reorder that history.
Collation preserves the stored observations, and the hand encoder pools the
last real token and returns zero for empty histories.
The PPO Actor stays in training mode for collection and updates so cuDNN can
backpropagate through its LSTM. At the start of `train()`, ordinary dropout,
attention dropout, and RNN dropout are set to zero on the Actor, keeping action
log probabilities consistent between collection and updates. Critic dropout
retains its existing behavior. For this mode fix alone, rerun the `train()`
definition cell and then the training call; existing model weights can be reused.
After changing encoder class definitions, restart the kernel and run the setup
cells; rerunning only the training call leaves older model classes in memory.

Open the **Episode history** tab to see the AI's final score and finishing rank
for each completed episode. The rank chart puts **1st place at the top** and 4th
at the bottom. Equal scores share a rank. History updates automatically when a
game finishes and remains across episode resets within the same environment;
creating a new training environment starts a new history. Incomplete episodes
are not plotted. The charts use Tkinter and need no additional plotting package.
The **Episode reward** tab shows the sum of rewards collected in each episode.
Rewards are retained as soon as collection finishes, including if model updates
are interrupted afterward.

Training completion freezes the elapsed timer and leaves the GUI open. The
notebook enables IPython's Tk event integration so tabs remain responsive while
you run other cells. Close the window manually when finished inspecting it.

The final **Save model parameters and charts** cell creates a unique folder
under `training_runs` (relative to the notebook's working directory). It saves
`actor_state_dict.pt`, `critic_state_dict.pt`, `score_history.png`,
`rank_history.png`, `reward_history.png`, `episode_history.csv`, and
`run_metadata.json`. The rank image also places first at the top. Each save
creates a separate folder; weights load with `model.load_state_dict(torch.load(
path, map_location='cpu', weights_only=True))` after constructing the same model.
Saving also works with `show_gui = False` or after the viewer is closed.
PNG export uses Pillow, which is already installed in the `german_bridge`
environment; dependencies are listed in `requirements.txt`.

- **Pause / Resume** holds collection at the current game event.
- **Next event** advances one event while paused (a bid, play, result, or turn).
- **Seconds per event** controls playback speed; zero collects as fast as possible.
- Closing the window lets training continue without reopening it.
- During model updates, the final game stays visible and the status shows the
  update epoch. Controls are serviced between optimizer batches.

Set `show_gui = True` or `show_gui = False` in the first code cell and run it
before starting training to enable or disable the observer. The training cell
uses this value directly and does not overwrite it.
The observer runs on the notebook/training thread; no separate `mainloop()` is
needed. All hands are visible for inspection, including the opponents' hands.

Seats run clockwise as P0 (bottom right), P1 (bottom left), P2 (top left), and
P3 (top right). The player immediately after the first bidder leads the round's
first trick; each trick's winner leads the next trick.
Each ComputerBot excludes the bid that would make the current total equal the
round number, using all bids already made (including the AI's bid).

To preview the GUI without initializing the actor and critic, run from the repo:

```powershell
conda run -n german_bridge python "AI bots/watch_game.py" --episodes 1 --delay 0.25
```

Use an environment with `gymnasium`, `numpy`, `torch`, and Tkinter installed.
The notebook keeps Gym's observation checker disabled because the existing
environment returns model-ready tensors and variable-length lists that do not
match its declared observation spaces.

Verification:

```powershell
conda run -n german_bridge python -m unittest discover -s "AI bots" -p "test_training*.py"
```

## Profiling the notebook's training loop

`profile_train.py` loads the notebook's actual model definitions and `train()`
function, then profiles only the training call using the built-in `cProfile`.
It does not execute the notebook's 1000-episode training cell or save models.

```powershell
conda run -n german_bridge python "AI bots/profile_train.py" --episodes 1 --epochs 1 --threads 1
```

Each run creates a folder under `AI bots/profiling_runs` with `train.prof`,
`report.txt`, `functions.csv`, and `run.json`. The report lists the slowest
functions by cumulative time (including callees) and self time. Partial results
are saved if training raises an exception or you interrupt with Ctrl+C.

Use `--episodes`, `--epochs`, `--batch-size`, `--device cpu|cuda|auto`, and
`--output-dir` to adjust the run; other training hyperparameters come from the
notebook. Use `--critic-batch-size` to compare rollout evaluation batch sizes,
or `--no-shuffle` for fixed update minibatches. The GUI is off by default;
`--gui --render-delay 0.25` includes its
overhead. Use `--charts-only` to profile the fast charts-only GUI. The standalone
profiler closes its viewer when profiling finishes.
CPU is the default because cProfile measures Python/CPU calls, not individual
asynchronous CUDA kernels. `--threads` is optional and changes the CPU workload,
so use the same thread count when comparing runs.

Reopen the raw profile with the same environment:

```powershell
conda run -n german_bridge python -m pstats "AI bots/profiling_runs/RUN_FOLDER/train.prof"
```

At the pstats prompt, enter `sort cumulative` followed by `stats 30`.
