from __future__ import annotations

from pathlib import Path
import shutil

from .config import ToolkitConfig
from .cfx import execute_session, find_command_editor
from .progress import ProgressCallback, emit
from .sessions import (
    create_export_session,
    create_import_session,
    create_temporary_visualization_export_session,
    create_visualization_sessions,
)
from .thermal_comfort import process_directory, process_files


def run_thermal_comfort_directory_workflow(
    export_directory: Path | str,
    import_directory: Path | str,
    thermal_settings,
    execute_import: bool = False,
    automation=None,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    export_directory = Path(export_directory)
    import_directory = Path(import_directory)
    import_directory.mkdir(parents=True, exist_ok=True)
    emit(progress_callback, "thermal_comfort", "Starting thermal-comfort calculations")
    import_files = process_directory(
        export_directory,
        import_directory,
        thermal_settings,
        pattern="export_*.csv",
        progress_callback=progress_callback,
    )
    # Thermal-comfort-only mode assumes the .cst already contains the imported
    # USER SURFACEs. Re-point them to the recalculated files instead of importing
    # Generic Data again, which would create duplicate "... 1" objects.
    import_session = create_import_session(
        import_files, import_directory, update_existing=True
    )
    if execute_import:
        find_command_editor(automation)
        execute_session(
            import_session,
            completion_file=import_directory / "import_complete.txt",
            completion_text="Import is successful",
            description="CFX-Post import",
            automation=automation,
            progress_callback=progress_callback,
        )
    emit(progress_callback, "done", "Thermal-comfort workflow complete")
    return {"import_files": import_files, "import_session": import_session}


def run_thermal_comfort_workflow(
    config: ToolkitConfig,
    execute_import: bool = True,
    progress_callback: ProgressCallback | None = None,
    *,
    update_existing_imports: bool = False,
) -> list[Path]:
    project = config.project
    project.create_directories()
    if not project.surfaces:
        raise ValueError("Thermal-comfort workflow requires at least one normal surface.")
    export_files = [project.export_directory / f"export_{s}.csv" for s in project.surfaces]
    missing = [p for p in export_files if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing expected export files:\n" + "\n".join(map(str, missing)))
    emit(progress_callback, "thermal_comfort", "Starting thermal-comfort workflow")
    import_files = process_files(
        export_files,
        project.import_directory,
        config.thermal_comfort,
        progress_callback,
    )
    import_session = create_import_session(
        import_files, project.import_directory,
        update_existing=update_existing_imports,
    )
    if execute_import:
        find_command_editor(config.automation)
        execute_session(
            import_session,
            completion_file=project.import_directory / "import_complete.txt",
            completion_text="Import is successful",
            description="CFX-Post import",
            automation=config.automation,
            progress_callback=progress_callback,
        )
    return import_files


def _temporary_native_variables(config: ToolkitConfig) -> list[str]:
    from . import _engine as engine

    raw = []
    raw.extend(str(e).split(",", 1)[0].strip() for e in config.visualization.figure_variables)
    raw.extend(str(e).split(",", 1)[0].strip() for e in config.visualization.histogram_variables)
    raw.extend(str(e).split(",", 1)[0].strip() for e in config.visualization.table_variables)
    raw.extend(item.name for item in config.visualization.section_variables)
    raw.extend(str(e).split(",", 1)[0].strip() for e in config.visualization.volume_histogram_variables)
    out, seen = [], set()
    for name in raw:
        if not name or name in seen or name in engine.CALCULATED_FIGURE_VARIABLES:
            continue
        seen.add(name)
        out.append(name)
    return out


def _normalize_cfx_object_reference(value: str) -> str:
    """Normalize CFX object references returned by Power Syntax.

    getChildren/getChildrenByCategory can return object references such as
    ``PLANE:Section AA`` or ``VOLUME:Basement Volume`` without the leading
    slash that CCL object-valued parameters expect.  Raw mesh-region names
    such as ``b1_0p5m`` intentionally remain unchanged.
    """
    value = str(value or "").strip()
    if value and not value.startswith("/") and ":" in value:
        return "/" + value
    return value


def _normalize_case_name(value: str) -> str:
    value = str(value or "").strip()
    # DATA READER normally returns the display name directly.  Handle a full
    # CASE object reference too, so the chart receives only the displayed name.
    if value.startswith("/"):
        value = value[1:]
    if value.upper().startswith("CASE:"):
        value = value.split(":", 1)[1].strip()
    return value


def _parse_metadata(path: Path) -> tuple[str, dict[str, str], dict[str, str]]:
    case_name = ""
    surfaces: dict[str, str] = {}
    volumes: dict[str, str] = {}
    if not path.exists():
        return case_name, surfaces, volumes
    for raw in path.read_text(errors="replace").splitlines():
        parts = raw.strip().split("|", 2)
        if not parts:
            continue
        if parts[0] == "CASE" and len(parts) >= 2:
            case_name = _normalize_case_name(parts[1])
        elif parts[0] == "SURFACE" and len(parts) == 3:
            surfaces[parts[1].strip()] = _normalize_cfx_object_reference(parts[2])
        elif parts[0] == "VOLUME" and len(parts) == 3:
            volumes[parts[1].strip()] = _normalize_cfx_object_reference(parts[2])
    return case_name, surfaces, volumes


def _volume_histogram_data_required(vis) -> bool:
    """Return True only when volume point data is needed for automatic bounds."""
    if not vis.create_volume_histograms or not vis.volume_histogram_volumes:
        return False

    from . import _engine as engine

    surface_configs = engine.parse_variable_entries(
        vis.histogram_variables,
        "HISTOGRAM_VARIABLES",
        "divisions",
        vis.default_histogram_divisions,
        1,
    ) if vis.create_surface_histograms and vis.histogram_variables else []
    volume_configs = engine.parse_variable_entries(
        vis.volume_histogram_variables,
        "VOLUME_HISTOGRAM_VARIABLES",
        "divisions",
        vis.default_histogram_divisions,
        1,
    ) if vis.volume_histogram_variables else []

    surface_by_name = {cfg["name"]: cfg for cfg in surface_configs}
    for cfg in volume_configs:
        # Histogram ranges are shared. If the same variable is also selected
        # for a surface histogram, collect_plot_statistics gives that surface
        # configuration precedence.
        effective = surface_by_name.get(cfg["name"], cfg)
        if effective.get("lower") is None or effective.get("upper") is None:
            return True
    return False


def _execute_temporary_visualization_export(
    config: ToolkitConfig,
    target_surfaces: list[str],
    target_volumes: list[str],
    progress_callback: ProgressCallback | None,
    *,
    export_volumes: list[str] | None = None,
):
    project = config.project
    if project.direct_visualization_output:
        temp_dir = project.main_directory
        temp_dir.mkdir(parents=True, exist_ok=True)
    else:
        temp_dir = project.figures_directory / "_temp_visualization_data"
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        temp_dir.mkdir(parents=True, exist_ok=True)

    session, surface_map, volume_map, marker, metadata = create_temporary_visualization_export_session(
        temp_dir,
        target_surfaces,
        _temporary_native_variables(config),
        volumes=target_volumes,
        export_volumes=export_volumes or [],
        created_variables=config.visualization.created_variables,
    )
    emit(progress_callback, "geometry", "Exporting temporary visualization geometry/data")
    execute_session(
        session,
        completion_file=marker,
        completion_text="Visualization export is successful",
        description="CFX-Post temporary visualization export",
        automation=config.automation,
        progress_callback=progress_callback,
    )
    missing = [p for p in [*surface_map.values(), *volume_map.values()] if not p.exists()]
    if missing:
        raise FileNotFoundError(
            "CFX reported completion but temporary visualization files are missing:\n"
            + "\n".join(map(str, missing))
        )
    case_name, surface_locations, volume_locations = _parse_metadata(metadata)
    temp_files = [session, marker, metadata, *surface_map.values(), *volume_map.values()]
    return temp_dir, surface_map, volume_map, temp_files, case_name, surface_locations, volume_locations


def _cleanup_temporary_visualization_files(project, temp_dir, temp_files, progress_callback):
    if project.direct_visualization_output:
        for path in temp_files:
            try:
                p = Path(path)
                if p.exists():
                    p.unlink()
            except OSError:
                pass
    elif temp_dir is not None and Path(temp_dir).exists():
        shutil.rmtree(temp_dir, ignore_errors=True)
    emit(progress_callback, "geometry", "Temporary visualization data cleaned")


def run_visualization_workflow(
    config: ToolkitConfig,
    execute_creation: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    project = config.project
    project.main_directory.mkdir(parents=True, exist_ok=True)
    vis = config.visualization
    find_command_editor(config.automation)

    target_surfaces = list(dict.fromkeys([*project.surfaces, *vis.section_surfaces]))
    target_volumes = list(dict.fromkeys([*vis.volume_histogram_volumes, *vis.table_volumes]))
    # In figures-only mode histogram bounds are explicit, so volumes normally
    # require metadata resolution only. Keep the generic rule for programmatic
    # callers that disable that validation.
    export_volumes = (
        list(vis.volume_histogram_volumes)
        if _volume_histogram_data_required(vis)
        else []
    )
    temp_dir = None
    temp_files = []
    try:
        temp_dir, surface_map, volume_map, temp_files, case_name, surface_locations, volume_locations = (
            _execute_temporary_visualization_export(
                config, target_surfaces, target_volumes, progress_callback,
                export_volumes=export_volumes,
            )
        )
        plan_export_files = [surface_map[s] for s in project.surfaces]
        section_export_files = [surface_map[s] for s in vis.section_surfaces]
        volume_export_files = [volume_map[v] for v in export_volumes]
        emit(progress_callback, "figures", "Creating visualization sessions")
        create_session, print_session, statistics = create_visualization_sessions(
            project,
            [],
            vis,
            plan_export_files=plan_export_files,
            section_export_files=section_export_files,
            volume_export_files=volume_export_files,
            surface_locations=surface_locations,
            volume_locations=volume_locations,
            case_name=case_name,
        )
    finally:
        _cleanup_temporary_visualization_files(project, temp_dir, temp_files, progress_callback)

    if execute_creation:
        execute_session(
            create_session,
            completion_file=project.figures_directory / "figures_creation_complete.txt",
            completion_text="Figure creation is successful",
            description="CFX-Post figure creation",
            automation=config.automation,
            progress_callback=progress_callback,
        )
        if vis.execute_print_session:
            execute_session(
                print_session,
                completion_file=project.figures_directory / "figures_printing_complete.txt",
                completion_text="Figure printing is successful",
                description="CFX-Post figure/chart/table printing",
                automation=config.automation,
                progress_callback=progress_callback,
            )
    emit(progress_callback, "done", "Visualization workflow complete")
    return {
        "create_figures_session": create_session,
        "print_figures_session": print_session,
        "statistics": statistics,
    }


def run_full_workflow(
    config: ToolkitConfig,
    create_print_session: bool = True,
    progress_callback: ProgressCallback | None = None,
) -> dict:
    project = config.project
    project.create_directories()
    if not project.surfaces:
        raise ValueError("Full automation requires at least one normal surface for thermal comfort.")
    find_command_editor(config.automation)

    emit(progress_callback, "export", "Creating CFX export session")
    export_session = create_export_session(project, config.visualization)
    execute_session(
        export_session,
        completion_file=project.export_directory / "export_complete.txt",
        completion_text="Export is successful",
        description="CFX-Post export",
        automation=config.automation,
        progress_callback=progress_callback,
    )
    case_name, base_surface_locations, base_volume_locations = _parse_metadata(
        project.export_directory / "visualization_metadata.txt"
    )

    import_files = run_thermal_comfort_workflow(
        config, execute_import=True, progress_callback=progress_callback
    )

    temp_dir = None
    temp_files = []
    section_export_files = []
    volume_export_files = []
    surface_locations = dict(base_surface_locations)
    volume_locations = dict(base_volume_locations)
    try:
        targets = list(config.visualization.section_surfaces)
        # Full export_session.cse already resolves metadata for all table/histogram
        # volumes. A temporary volumetric CSV is required only when Python must
        # calculate automatic histogram bounds from the volume distribution.
        export_volumes = (
            list(config.visualization.volume_histogram_volumes)
            if _volume_histogram_data_required(config.visualization)
            else []
        )
        volumes = list(export_volumes)
        if targets or volumes:
            temp_dir, surface_map, volume_map, temp_files, temp_case, temp_surface_locations, temp_volume_locations = (
                _execute_temporary_visualization_export(
                    config, targets, volumes, progress_callback,
                    export_volumes=export_volumes,
                )
            )
            section_export_files = [surface_map[s] for s in targets]
            volume_export_files = [volume_map[v] for v in export_volumes]
            surface_locations.update(temp_surface_locations)
            volume_locations.update(temp_volume_locations)
            if temp_case:
                case_name = temp_case

        create_session, print_session, statistics = create_visualization_sessions(
            project,
            import_files,
            config.visualization,
            section_export_files=section_export_files,
            volume_export_files=volume_export_files,
            surface_locations=surface_locations,
            volume_locations=volume_locations,
            case_name=case_name,
        )
    finally:
        _cleanup_temporary_visualization_files(project, temp_dir, temp_files, progress_callback)

    execute_session(
        create_session,
        completion_file=project.figures_directory / "figures_creation_complete.txt",
        completion_text="Figure creation is successful",
        description="CFX-Post figure creation",
        automation=config.automation,
        progress_callback=progress_callback,
    )
    if config.visualization.execute_print_session and create_print_session:
        execute_session(
            print_session,
            completion_file=project.figures_directory / "figures_printing_complete.txt",
            completion_text="Figure printing is successful",
            description="CFX-Post figure/chart/table printing",
            automation=config.automation,
            progress_callback=progress_callback,
        )
    emit(progress_callback, "done", "Full workflow complete")
    return {
        "export_session": export_session,
        "import_files": import_files,
        "create_figures_session": create_session,
        "print_figures_session": print_session if create_print_session else None,
        "statistics": statistics,
    }
