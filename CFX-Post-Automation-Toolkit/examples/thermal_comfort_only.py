"""Recalculate a previous full run and update its existing imported CFX surface.

First run full_automation.py with your surface name, and retain that CFX state.
This example actively updates the open case; it does not export new CFD data.
"""
from _bootstrap import add_project_src, print_progress

ROOT = add_project_src()

from cfxpost_toolkit import ProjectConfig, ThermalComfortConfig, ToolkitConfig
from cfxpost_toolkit.workflows import run_thermal_comfort_workflow

SURFACE = "Occupied Plane"  # Must match the previous run and loaded CFX state.
RUN_DIRECTORY = ROOT / "runs" / "full-automation"


def main():
    config = ToolkitConfig(
        project=ProjectConfig(RUN_DIRECTORY, surfaces=[SURFACE]),
        thermal_comfort=ThermalComfortConfig(met=1.2, clo=0.5),
    )
    files = run_thermal_comfort_workflow(
        config, execute_import=True, update_existing_imports=True,
        progress_callback=print_progress,
    )
    for path in files:
        print(path)


if __name__ == "__main__":
    main()
