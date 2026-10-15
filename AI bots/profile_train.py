"""Profile the real train() function in train.ipynb with Python's cProfile.

Example: python "AI bots/profile_train.py" --episodes 1 --epochs 1 --threads 1
Setup, model creation, and report generation are excluded from the profile.
"""

import argparse
import ast
import cProfile
import csv
from datetime import datetime, timedelta, timezone
from functools import partial
import json
import linecache
from pathlib import Path
import pstats
import random
import sys
import tempfile
import time


CONFIG_NAMES = {"episode", "epoch", "batch_size", "learning_rate", "gamma",
                "epsilon", "entropy_coefficient"}


def _assigns_device(statement):
    return any(isinstance(node, ast.Assign) and any(
        isinstance(target, ast.Name) and target.id == "device" for target in node.targets)
        for node in ast.walk(statement))


def load_notebook_training(notebook_path, device="cpu"):
    """Run setup cells through train's definition, never the training/save calls."""
    notebook_path = Path(notebook_path).resolve()
    notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    namespace = {"__name__": "notebook_profile", "device": device, "show_gui": False}
    found_train = False
    sys.path.insert(0, str(notebook_path.parent))
    try:
        for index, cell in enumerate(notebook["cells"], 1):
            if cell["cell_type"] != "code":
                continue
            source = "".join(cell.get("source", []))
            # IPython's autoreload magics are not needed in a fresh Python process.
            if source.lstrip().startswith(("%", "!")):
                continue
            filename = f"{notebook_path}::cell_{index}"
            linecache.cache[filename] = (len(source), None, source.splitlines(True), filename)
            tree = ast.parse(source, filename=filename)
            if found_train:
                # Read the notebook's hyperparameters without running gym.make,
                # train(), Tk integration, or its artifact-saving cell.
                nodes = [node for node in tree.body if isinstance(node, ast.Assign)
                         and all(isinstance(target, ast.Name) and target.id in CONFIG_NAMES
                                 for target in node.targets)]
            else:
                nodes = []
                for node in tree.body:
                    # The profiler chooses the device; keep the notebook's models
                    # on that device even if its normal setup auto-selects CUDA.
                    if isinstance(node, ast.If) and _assigns_device(node):
                        continue
                    nodes.append(node)
                    if isinstance(node, ast.FunctionDef) and node.name == "train":
                        found_train = True
                        break
            exec(compile(ast.Module(body=nodes, type_ignores=[]), filename, "exec"), namespace)
            namespace.update(show_gui=False, device=device)
        if not found_train:
            raise ValueError(f"No train() definition found in {notebook_path}")
    finally:
        sys.path.pop(0)
    return namespace


def profile_call(function, output_dir, *, top=30, metadata=None, synchronize=None):
    """Save raw stats, readable reports, and CSV even if the call raises."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    profiler = cProfile.Profile()
    status, error = "completed", None
    if synchronize is not None:
        synchronize()
    started = time.perf_counter()
    try:
        profiler.enable()
        function()
    except BaseException as exc:
        status = "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed"
        error = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        profiler.disable()
        if synchronize is not None:
            synchronize()
        elapsed = time.perf_counter() - started
        profiler.dump_stats(str(output_dir / "train.prof"))
        with (output_dir / "report.txt").open("w", encoding="utf-8") as report:
            report.write("cumtime: function plus callees; tottime: function itself.\n")
            report.write("CUDA kernels run asynchronously; these are Python/CPU call timings.\n\n")
            stats = pstats.Stats(profiler, stream=report).strip_dirs()
            report.write("=== Top functions by cumulative time ===\n")
            stats.sort_stats(pstats.SortKey.CUMULATIVE).print_stats(top)
            report.write("\n=== Top functions by self time ===\n")
            stats.sort_stats(pstats.SortKey.TIME).print_stats(top)
        raw_stats = pstats.Stats(profiler)
        with (output_dir / "functions.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.writer(handle)
            writer.writerow(["file", "line", "function", "primitive_calls", "total_calls",
                             "self_seconds", "cumulative_seconds"])
            for (filename, line, name), (primitive, total, own, cumulative, _) in sorted(
                    raw_stats.stats.items(), key=lambda item: item[1][3], reverse=True):
                writer.writerow([filename, line, name, primitive, total, own, cumulative])
        details = dict(metadata or {}, status=status, error=error, wall_seconds=elapsed)
        (output_dir / "run.json").write_text(json.dumps(details, indent=2), encoding="utf-8")
        print(f"\nProfile {status}. Results: {output_dir.resolve()}")
        print((output_dir / "report.txt").read_text(encoding="utf-8"))
    return output_dir


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return number


def main(argv=None):
    folder = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--notebook", type=Path, default=folder / "train.ipynb")
    parser.add_argument("--episodes", type=positive_int, default=1)
    parser.add_argument("--epochs", type=positive_int, default=1)
    parser.add_argument("--batch-size", type=positive_int, default=None,
                        help="default: batch_size from the notebook")
    parser.add_argument("--device", choices=("cpu", "cuda", "auto"), default="cpu")
    parser.add_argument("--threads", type=positive_int, default=None,
                        help="optional PyTorch CPU thread count")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--gui", action="store_true", help="include GUI overhead in the profile")
    parser.add_argument("--render-delay", type=float, default=0.0)
    parser.add_argument("--top", type=positive_int, default=30)
    parser.add_argument("--output-dir", type=Path, default=folder / "profiling_runs",
                        help="parent folder for a new profiling run")
    args = parser.parse_args(argv)
    if args.render_delay < 0:
        parser.error("--render-delay must be nonnegative")

    import numpy as np
    import torch

    device = ("cuda" if torch.cuda.is_available() else "cpu") if args.device == "auto" else args.device
    if device == "cuda" and not torch.cuda.is_available():
        parser.error("CUDA was requested but is not available")
    if args.threads is not None:
        torch.set_num_threads(args.threads)
    random.seed(args.seed)
    np.random.seed(args.seed)
    torch.manual_seed(args.seed)
    namespace = load_notebook_training(args.notebook, device=device)
    actor, critic = namespace["actor_model"].to(device), namespace["critic_model"].to(device)
    env = namespace["GermanBridgeGameEnv"](
        render_mode="human" if args.gui else None, render_delay=args.render_delay)
    learning_rate = namespace.get("learning_rate", 0.001)
    batch_size = args.batch_size or namespace.get("batch_size", 32)
    gamma = namespace.get("gamma", 0.99)
    epsilon = namespace.get("epsilon", 0.2)
    entropy = namespace.get("entropy_coefficient", 0.01)
    actor_optimizer = torch.optim.Adam(actor.parameters(), lr=learning_rate)
    critic_optimizer = torch.optim.Adam(critic.parameters(), lr=learning_rate)
    output_root = args.output_dir.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone(timedelta(hours=8)))
    output = Path(tempfile.mkdtemp(prefix=f"run_{timestamp:%Y%m%d_%H%M%S}_", dir=output_root))
    print(f"Profiling {args.episodes} episode(s), {args.epochs} epoch(s), device={device}, GUI={args.gui}")
    training_call = partial(namespace["train"], actor, critic,
                            torch.nn.CrossEntropyLoss(), torch.nn.MSELoss(),
                            actor_optimizer, critic_optimizer, env,
                            episode=args.episodes, epoch=args.epochs, batch_size=batch_size,
                            gamma=gamma, epsilon=epsilon, entropy_coefficient=entropy, device=device)
    try:
        profile_call(training_call, output, top=args.top,
            metadata={"notebook": str(args.notebook.resolve()), "device": device,
                      "episodes": args.episodes, "epochs": args.epochs, "batch_size": batch_size,
                      "learning_rate": learning_rate, "gamma": gamma, "epsilon": epsilon,
                      "entropy_coefficient": entropy, "gui": args.gui,
                      "render_delay": args.render_delay, "seed": args.seed,
                      "torch_threads": torch.get_num_threads()},
            synchronize=torch.cuda.synchronize if device == "cuda" else None)
    finally:
        env.close()
    return output


if __name__ == "__main__":
    main()
