"""Internal adapter between public configuration objects and the validated engine.

The current package intentionally keeps the already-tested CFX session-generation
logic in one private engine module. Public APIs pass configuration explicitly and
this adapter applies it to the engine immediately before an operation. This keeps
v0.1 behavior aligned with the working monolithic script while allowing the public
API to remain modular and GUI-ready.
"""

from .config import CFXAutomationConfig, ThermalComfortConfig, VisualizationConfig


def apply_thermal_config(engine, cfg: ThermalComfortConfig) -> None:
    engine.met = cfg.met
    engine.clo = cfg.clo
    engine.minimum_velocity = cfg.minimum_velocity
    engine.pressure = cfg.pressure
    engine.emissivity = cfg.emissivity
    engine.MAX_CLEANING_DISTANCE = cfg.max_cleaning_distance

    engine.calculate_utci = cfg.calculate_utci
    engine.calculate_psychrometrics = cfg.calculate_psychrometrics
    engine.calculate_draft_rate = cfg.calculate_draft_rate
    engine.calculate_clothing_temperature = cfg.calculate_clothing_temperature
    engine.calculate_set = cfg.calculate_set
    engine.calculate_pmv_ppd = cfg.calculate_pmv_ppd
    engine.calculate_operative_temperature = cfg.calculate_operative_temperature


def apply_visualization_config(engine, cfg: VisualizationConfig) -> None:
    engine.DEFAULT_NUMBER_OF_CONTOURS = cfg.default_number_of_contours
    engine.DEFAULT_NUMBER_OF_HISTOGRAM_DIVISIONS = cfg.default_histogram_divisions
    engine.AVERAGE_TABLE_NAME = cfg.average_table_name
    engine.FIRST_FIGURE_NUMBER = cfg.first_figure_number
    engine.CAMERA_MARGIN = cfg.camera_margin
    engine.CAMERA_SCALE_FACTOR = cfg.camera_scale_factor
    engine.CLIP_PLANE_Z_OFFSET = cfg.clip_plane_z_offset
    engine.FIGURE_IMAGE_WIDTH = cfg.image_width
    engine.FIGURE_IMAGE_HEIGHT = cfg.image_height


def apply_automation_config(engine, cfg: CFXAutomationConfig) -> None:
    engine.COMMAND_EDITOR_TITLE = cfg.command_editor_title
    engine.PROCESS_BUTTON_X_RATIO = cfg.process_button_x_ratio
    engine.PROCESS_BUTTON_Y_FROM_BOTTOM_RATIO = cfg.process_button_y_from_bottom_ratio
    engine.EDITOR_FOCUS_X_RATIO = cfg.editor_focus_x_ratio
    engine.EDITOR_FOCUS_Y_RATIO = cfg.editor_focus_y_ratio
