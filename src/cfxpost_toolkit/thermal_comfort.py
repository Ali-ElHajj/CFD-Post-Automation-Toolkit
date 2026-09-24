from pathlib import Path
from typing import Iterable

from .config import ThermalComfortConfig
from .progress import ProgressCallback, emit


def process_file(
    input_file: Path | str,
    output_file: Path | str,
    settings: ThermalComfortConfig | None = None,
) -> Path:
    """Calculate thermal-comfort variables for one CFX Generic CSV."""
    from . import _engine as engine
    from ._runtime import apply_thermal_config

    settings = settings or ThermalComfortConfig()
    apply_thermal_config(engine, settings)

    input_file = Path(input_file)
    output_file = Path(output_file)
    output_file.parent.mkdir(parents=True, exist_ok=True)
    engine.process_file(input_file, output_file)
    return output_file


def process_files(
    input_files: Iterable[Path | str],
    output_directory: Path | str,
    settings: ThermalComfortConfig | None = None,
    progress_callback: ProgressCallback | None = None,
) -> list[Path]:
    """Process selected export CSVs and return the created import CSV paths."""
    input_files = [Path(p) for p in input_files]
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)

    outputs: list[Path] = []
    total = len(input_files)

    for index, input_file in enumerate(input_files, start=1):
        output_name = input_file.name
        if output_name.lower().startswith("export_"):
            output_name = "import_" + output_name[len("export_"):]
        else:
            output_name = "import_" + output_name

        emit(
            progress_callback,
            "thermal_comfort",
            f"Processing {input_file.name}",
            index,
            total,
        )
        outputs.append(
            process_file(input_file, output_directory / output_name, settings)
        )

    emit(progress_callback, "thermal_comfort", "Thermal-comfort calculations complete", total, total)
    return outputs


def process_directory(
    input_directory: Path | str,
    output_directory: Path | str,
    settings: ThermalComfortConfig | None = None,
    pattern: str = "export_*.csv",
    progress_callback: ProgressCallback | None = None,
) -> list[Path]:
    """Process matching CFX export files in a directory."""
    input_directory = Path(input_directory)
    files = sorted(input_directory.glob(pattern))
    if not files:
        raise FileNotFoundError(
            f"No files matching '{pattern}' were found in {input_directory}"
        )
    return process_files(files, output_directory, settings, progress_callback)
