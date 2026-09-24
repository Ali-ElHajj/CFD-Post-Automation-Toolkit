"""Calculate the bundled synthetic CSV without interacting with CFX-Post.

Windows/dependencies are still required by the current engine. Replace INPUT
with your own export folder to process real data. The import session generated
here is not executed and assumes existing imported surfaces if loaded later.
"""
from pathlib import Path
from _bootstrap import add_project_src, print_progress

ROOT = add_project_src()

from cfxpost_toolkit import ThermalComfortConfig
from cfxpost_toolkit.workflows import run_thermal_comfort_directory_workflow

INPUT = Path(__file__).resolve().parent / "data"
OUTPUT = ROOT / "runs" / "csv-demo"


def main():
    result = run_thermal_comfort_directory_workflow(
        INPUT, OUTPUT,
        ThermalComfortConfig(met=1.7, clo=0.57),
        execute_import=False,
        progress_callback=print_progress,
    )
    for path in result["import_files"]:
        print("Calculated CSV:", path)
    print("Unexecuted update-existing import session:", result["import_session"])


if __name__ == "__main__":
    main()
