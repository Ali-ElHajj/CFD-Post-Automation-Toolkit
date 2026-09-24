"""Create native-variable contours and a table in an already-open CFX case."""
from _bootstrap import add_project_src, print_progress

ROOT = add_project_src()

from cfxpost_toolkit import ProjectConfig, ToolkitConfig, VisualizationConfig
from cfxpost_toolkit.workflows import run_visualization_workflow

SURFACE = "Occupied Plane"  # Placeholder: replace with your CFX surface name.
OUTPUT_DIRECTORY = ROOT / "runs" / "figures-only"


def main():
    config = ToolkitConfig(
        project=ProjectConfig(
            OUTPUT_DIRECTORY, surfaces=[SURFACE], direct_visualization_output=True,
        ),
        visualization=VisualizationConfig(
            figure_variables=["Temperature, 18, 28, 21", "Velocity, 0, 1, 21"],
            create_average_table=True,
            table_surfaces=[SURFACE],
            table_variables=["Temperature", "Velocity"],
            require_explicit_plan_bounds=True,
            execute_print_session=False,
        ),
    )
    result = run_visualization_workflow(config, progress_callback=print_progress)
    print("Print session:", result["print_figures_session"])


if __name__ == "__main__":
    main()
