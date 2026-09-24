"""IDLE-friendly launcher for the CFX-Post Automation Toolkit GUI."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIRECTORY = PROJECT_ROOT / "src"
if str(SRC_DIRECTORY) not in sys.path:
    sys.path.insert(0, str(SRC_DIRECTORY))

from cfxpost_toolkit.gui import launch_gui


if __name__ == "__main__":
    launch_gui()
