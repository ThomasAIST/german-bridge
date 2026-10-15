# Training observer

Run `train.ipynb` using the `german_bridge` Python kernel. The **GUI settings**
section at the very top contains `show_gui = True`. Re-run the settings, imports,
`train` function, and final cell after updating the files (or restart the kernel).

The window shows every player's hand, bid, tricks won, cumulative score, the
current turn, trump suit, current and previous tricks, and a recent-action log.
The sidebar shows the episode, collected samples, last reward, and episode reward.
It also shows total training time as `HH:MM:SS` and the average seconds per fully
completed episode. Timing starts when `train()` begins and includes data
collection, model updates, playback delays, and pauses. The average appears
after the first episode's model updates finish and excludes the current
unfinished episode. Counters persist across episode resets and restart for a
new training run. The elapsed counter updates while the viewer is paused.
One full game contains 104 agent decisions: 13 bids and 91 card plays.

Open the **Episode history** tab to see the AI's final score and finishing rank
for each completed episode. The rank chart puts **1st place at the top** and 4th
at the bottom. Equal scores share a rank. History updates automatically when a
game finishes and remains across episode resets within the same environment;
creating a new training environment starts a new history. Incomplete episodes
are not plotted. The charts use Tkinter and need no additional plotting package.

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
conda run -n german_bridge python -m unittest discover -s "AI bots" -p "test_training_gui.py"
```
