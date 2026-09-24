"""Load the checkout's source when running an example directly or from IDLE."""
from pathlib import Path
import sys


def add_project_src():
    root = Path(__file__).resolve().parents[1]
    source = root / "src"
    if not (source / "cfxpost_toolkit").is_dir():
        raise RuntimeError("Keep examples/ inside the complete repository checkout.")
    if str(source) not in sys.path:
        sys.path.insert(0, str(source))
    return root


def print_progress(event):
    count = ""
    if event.current is not None and event.total is not None:
        count = f" {event.current}/{event.total}"
    print(f"[{event.stage}{count}] {event.message}")
