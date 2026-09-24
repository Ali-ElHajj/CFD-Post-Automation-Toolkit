"""Install this checkout into the Python environment running this script.

IDLE: open this file and press F5. Installs dependencies using pip; requires
package-index access. Does not rewrite source files or inject local paths.
"""
from pathlib import Path
import importlib
import subprocess
import sys


def main():
    if sys.platform != "win32":
        raise SystemExit("The v1 runtime requires Windows and pywin32.")
    if sys.version_info < (3, 10):
        raise SystemExit("Python 3.10 or later is required.")
    root = Path(__file__).resolve().parents[1]
    executable = Path(sys.executable)
    if executable.name.lower() == "pythonw.exe":
        executable = executable.with_name("python.exe")
    print(f"Installing {root} into {executable}")
    subprocess.run(
        [str(executable), "-m", "pip", "install", "-e", str(root)],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    sys.path.insert(0, str(root / "src"))
    importlib.invalidate_caches()
    # Verify in a fresh process so newly installed .pth files are initialized.
    subprocess.run(
        [str(executable), "-c",
         "import tkinter; import cfxpost_toolkit._engine; "
         "from cfxpost_toolkit.gui import launch_gui; print('Imports OK')"],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    print("Setup complete. Open CFX_Post_Toolkit_GUI.py and press F5.")


if __name__ == "__main__":
    main()
