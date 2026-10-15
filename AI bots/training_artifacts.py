"""Save portable model weights and episode charts, with or without the GUI."""

import csv
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import tempfile

import torch


def create_history_image(history, key):
    """Render a standalone PNG chart without creating a GUI or changing backends."""
    from PIL import Image, ImageDraw, ImageFont

    def font(size):
        for name in ("DejaVuSans.ttf", "arial.ttf"):
            try:
                return ImageFont.truetype(name, size)
            except OSError:
                pass
        return ImageFont.load_default()

    titles = {"score": "AI final score by episode", "rank": "AI final rank by episode",
              "reward": "AI episode reward by episode"}
    labels = {"score": "Final score", "rank": "Rank (1 = best)", "reward": "Episode reward"}
    colors = {"score": "#326ed1", "rank": "#27826b", "reward": "#df8a20"}
    results = [row for row in history if row.get(key) is not None]
    image = Image.new("RGB", (1440, 720), "white")
    draw = ImageDraw.Draw(image)
    title_font, text_font = font(30), font(21)
    draw.text((55, 25), titles[key], font=title_font, fill="#17232b")
    draw.text((125, 73), labels[key], font=text_font, fill="#536573")
    left, right, top, bottom = 125, 1398, 110, 620
    values = [row[key] for row in results]
    if key == "rank":
        low, high, ticks = 1, 4, [1, 2, 3, 4]
    else:
        low, high = min([0] + values), max([0] + values)
        padding = max(1, (high - low) * 0.1)
        low, high = low - padding, high + padding
        ticks = [low + i * (high - low) / 4 for i in range(5)]

    def y_position(value):
        fraction = (value - low) / (high - low)
        return top + fraction * (bottom - top) if key == "rank" else bottom - fraction * (bottom - top)

    for value in ticks:
        y = y_position(value)
        draw.line((left, y, right, y), fill="#dde5ec", width=1)
        draw.text((left - 16, y), f"{value:g}", anchor="rm", font=text_font, fill="#536573")
    draw.line([(left, top), (left, bottom), (right, bottom)], fill="#536573", width=2)
    draw.text(((left + right) / 2, 686), "Episode", anchor="mm", font=text_font, fill="#536573")
    if not results:
        draw.text(((left + right) / 2, (top + bottom) / 2), "No completed episode results yet",
                  anchor="mm", font=text_font, fill="#536573")
        return image
    episodes = [row["episode"] for row in results]
    first, last = min(episodes), max(episodes)
    if first == last:
        first, last = first - 0.5, last + 0.5

    def x_position(episode):
        return left + (episode - first) / (last - first) * (right - left)

    for episode in sorted({episodes[round(i * (len(episodes) - 1) / 4)] for i in range(5)}):
        x = x_position(episode)
        draw.text((x, bottom + 20), str(episode), anchor="mt", font=text_font, fill="#536573")
    points = [(x_position(row["episode"]), y_position(row[key])) for row in results]
    if len(points) > 1:
        draw.line(points, fill=colors[key], width=3)
    for x, y in points if len(points) <= 40 else points[-1:]:
        draw.ellipse((x - 5, y - 5, x + 5, y + 5), fill=colors[key])
    return image


def save_training_run(actor_model, critic_model, env, output_root="training_runs", config=None):
    """Create a unique run folder; never overwrite an earlier save."""
    # Verify PNG support before creating any partial output folder.
    from PIL import Image  # noqa: F401

    game = env.unwrapped
    history = [dict(row) for row in game.episode_history]
    root = Path(output_root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone(timedelta(hours=8)))
    folder = Path(tempfile.mkdtemp(prefix=f"run_{timestamp:%Y%m%d_%H%M%S}_", dir=root))
    for name, model in (("actor", actor_model), ("critic", critic_model)):
        weights = {key: value.detach().cpu() if isinstance(value, torch.Tensor) else value
                   for key, value in model.state_dict().items()}
        torch.save(weights, folder / f"{name}_state_dict.pt")

    for key in ("score", "rank", "reward"):
        image = create_history_image(history, key)
        try:
            image.save(folder / f"{key}_history.png", format="PNG", dpi=(160, 160))
        finally:
            image.close()

    with (folder / "episode_history.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["episode", "score", "rank", "reward"],
                                extrasaction="ignore")
        writer.writeheader()
        writer.writerows(history)
    elapsed, average = game.get_training_timing()
    metadata = {"saved_at": timestamp.isoformat(), "phase": game.training_progress["phase"],
                "episodes_with_results": len(history),
                "training_episodes_completed": game._completed_training_episodes,
                "elapsed_seconds": elapsed, "average_episode_seconds": average,
                "actor_class": type(actor_model).__name__,
                "critic_class": type(critic_model).__name__, "config": config or {}}
    (folder / "run_metadata.json").write_text(json.dumps(metadata, indent=2, default=str),
                                             encoding="utf-8")
    return folder
