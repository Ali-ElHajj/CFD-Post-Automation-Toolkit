from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ProjectConfig:
    """Project folders and CFX surfaces used for normal/top views."""

    main_directory: Path
    surfaces: list[str] = field(default_factory=list)
    direct_visualization_output: bool = False

    @property
    def export_directory(self) -> Path:
        return self.main_directory / "export"

    @property
    def import_directory(self) -> Path:
        return self.main_directory / "import"

    @property
    def figures_directory(self) -> Path:
        return self.main_directory if self.direct_visualization_output else self.main_directory / "figures"

    def create_directories(self) -> None:
        # In figures-only mode the selected directory is used directly; do not
        # create export/import/figures subfolders.
        if self.direct_visualization_output:
            self.main_directory.mkdir(parents=True, exist_ok=True)
            return
        for directory in (self.export_directory, self.import_directory, self.figures_directory):
            directory.mkdir(parents=True, exist_ok=True)


@dataclass
class ThermalComfortConfig:
    """Thermal-comfort calculations and data-cleaning settings."""

    met: float = 1.7
    clo: float = 0.57
    minimum_velocity: float = 0.05
    pressure: float = 101325.0
    emissivity: float = 0.95
    max_cleaning_distance: float = 1.0

    calculate_utci: bool = False
    calculate_psychrometrics: bool = False
    calculate_draft_rate: bool = False
    calculate_clothing_temperature: bool = False
    calculate_set: bool = False
    calculate_pmv_ppd: bool = True
    calculate_operative_temperature: bool = True


@dataclass
class CreatedVariableConfig:
    """One optional CFX USER SCALAR VARIABLE created from a CEL expression."""

    name: str
    expression: str
    expression_name: str
    enabled: bool = True


@dataclass
class SectionVariableConfig:
    """One native CFX variable used for section-view contours."""

    name: str
    lower: float | None = None
    upper: float | None = None
    number_of_contours: int | None = None
    add_velocity_vectors: bool = False
    create_streamlines: bool = False


@dataclass
class VisualizationConfig:
    """Contour, section, histogram, streamline, table and hardcopy settings."""

    # Visual-type switches -------------------------------------------------
    create_plan_contours: bool = True
    create_section_contours: bool = False
    create_surface_histograms: bool = False
    create_volume_histograms: bool = False
    create_average_table: bool = True

    # Normal/top-view variables. Entries use "Variable" or
    # "Variable, lower, upper, count".
    figure_variables: list[str] = field(default_factory=list)
    create_plan_velocity_streamlines: bool = False

    # Surface histogram selections. Histogram entries use the same lower/upper
    # range as volumetric histograms for a given variable.
    histogram_surfaces: list[str] = field(default_factory=list)
    histogram_variables: list[str] = field(default_factory=list)

    # Average-table selections are independent from contour/histogram choices.
    # Surfaces must be selected from the master normal/top-view surface list.
    # Volumes share the master volume-name registry with volumetric histograms.
    table_surfaces: list[str] = field(default_factory=list)
    table_volumes: list[str] = field(default_factory=list)
    table_variables: list[str] = field(default_factory=list)

    # Optional native-like variables generated inside CFX-Post from CEL expressions.
    created_variables: list[CreatedVariableConfig] = field(default_factory=list)

    # Section views use only native CFX variables (+ manual native names).
    section_surfaces: list[str] = field(default_factory=list)
    section_variables: list[SectionVariableConfig] = field(default_factory=list)

    # Volumetric histograms use only native CFX variables (+ manual names).
    volume_histogram_volumes: list[str] = field(default_factory=list)
    volume_histogram_variables: list[str] = field(default_factory=list)

    default_number_of_contours: int = 21
    default_histogram_divisions: int = 20
    velocity_vector_samples: int = 100
    streamline_samples: int = 100

    average_table_name: str = "Average conditions"
    first_figure_number: int = 1

    camera_margin: float = 0.5
    camera_scale_factor: float = 1.0
    clip_plane_z_offset: float = 0.1

    image_width: int = 2400
    image_height: int = 1600
    execute_print_session: bool = False

    # Figures-only mode: non-section lower/upper limits must be explicitly
    # supplied. Contour and histogram counts can use defaults.
    require_explicit_plan_bounds: bool = False


@dataclass
class CFXAutomationConfig:
    """Settings for controlling the already-open CFX-Post Command Editor."""

    command_editor_title: str = "Command Editor"
    process_button_x_ratio: float = 0.145
    process_button_y_from_bottom_ratio: float = 0.05
    editor_focus_x_ratio: float = 0.50
    editor_focus_y_ratio: float = 0.50


@dataclass
class ToolkitConfig:
    project: ProjectConfig
    thermal_comfort: ThermalComfortConfig = field(default_factory=ThermalComfortConfig)
    visualization: VisualizationConfig = field(default_factory=VisualizationConfig)
    automation: CFXAutomationConfig = field(default_factory=CFXAutomationConfig)
