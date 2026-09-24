"""Export, calculate, import, and visualize one surface in an open CFX case.

Change SURFACE to an existing location in your case before running.
"""
from _bootstrap import add_project_src, print_progress

ROOT = add_project_src()

from cfxpost_toolkit import (
    ProjectConfig, ThermalComfortConfig, ToolkitConfig, VisualizationConfig,
)
from cfxpost_toolkit.workflows import run_full_workflow

SURFACE = "Occupied Plane"  # Placeholder: replace with an exact CFX surface name.
OUTPUT_DIRECTORY = ROOT / "runs" / "full-automation"


def main():
    config = ToolkitConfig(
        project=ProjectConfig(OUTPUT_DIRECTORY, surfaces=[SURFACE]),
        thermal_comfort=ThermalComfortConfig(met=1.7, clo=0.57),
        visualization=VisualizationConfig(
            figure_variables=["Temperature, 18, 28, 21", "PMV, -2, 2, 21"],
            create_surface_histograms=True,
            histogram_surfaces=[SURFACE],
            histogram_variables=["PMV, -2, 2, 20"],
            create_average_table=True,
            table_surfaces=[SURFACE],
            table_variables=["Temperature", "PMV", "PPD"],
            execute_print_session=False,  # Set True to also export PNGs/table.
        ),
    )
    result = run_full_workflow(config, progress_callback=print_progress)
    print("Print session:", result["print_figures_session"])


if __name__ == "__main__":
    main()
