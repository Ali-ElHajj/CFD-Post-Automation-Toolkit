from __future__ import annotations

from pathlib import Path

from .config import CreatedVariableConfig, ProjectConfig, SectionVariableConfig, VisualizationConfig




def _created_field(item, field, default=""):
    if isinstance(item, dict):
        return item.get(field, default)
    return getattr(item, field, default)


def _validate_created_variables(items) -> None:
    """Validate optional expression-derived CFX variables for programmatic callers too."""
    variable_names = {"relative humidity percentage"}
    expression_names = {"relative humidity percentage"}
    for item in items or []:
        name = str(_created_field(item, "name")).strip()
        expression = str(_created_field(item, "expression")).strip()
        expression_name = str(_created_field(item, "expression_name")).strip()
        enabled = bool(_created_field(item, "enabled", True))
        if not name:
            raise ValueError("Created-variable name cannot be blank.")
        if any(ch in name for ch in "\r\n,"):
            raise ValueError(f"Created-variable name contains unsupported punctuation: {name!r}")
        key = name.casefold()
        expr_key = expression_name.casefold()
        if key in variable_names or key in expression_names:
            raise ValueError(f"Duplicate/conflicting created-variable name: {name}")
        if not expression_name:
            raise ValueError(f"Created variable '{name}' requires a distinct internal expression name.")
        if expr_key == key or expr_key in variable_names or expr_key in expression_names:
            raise ValueError(
                f"Created variable '{name}' has an internal expression name that conflicts case-insensitively: "
                f"'{expression_name}'."
            )
        if enabled and not expression:
            raise ValueError(f"Enabled created variable '{name}' requires a CEL expression.")
        variable_names.add(key)
        expression_names.add(expr_key)

def _variable_name(entry: str) -> str:
    return str(entry).split(",", 1)[0].strip()


def _extra_native_variables(settings: VisualizationConfig | None) -> list[str]:
    """Return user-added/native CFX variables required by exports."""
    if settings is None:
        return []
    from . import _engine as engine

    names: list[str] = []
    seen: set[str] = set()
    raw: list[str] = []
    raw.extend(_variable_name(entry) for entry in settings.figure_variables)
    raw.extend(_variable_name(entry) for entry in settings.histogram_variables)
    raw.extend(_variable_name(entry) for entry in settings.table_variables)
    raw.extend(item.name for item in settings.section_variables)
    raw.extend(_variable_name(entry) for entry in settings.volume_histogram_variables)

    for name in raw:
        if not name or name in seen:
            continue
        seen.add(name)
        if name in engine.CALCULATED_FIGURE_VARIABLES:
            continue
        if name in engine.ORIGINAL_FIGURE_VARIABLES:
            continue
        names.append(name)
    return names


def create_export_session(
    project: ProjectConfig,
    visualization: VisualizationConfig | None = None,
) -> Path:
    """Create the full-workflow surface export session."""
    from . import _engine as engine

    project.create_directories()
    if visualization is not None:
        _validate_created_variables(visualization.created_variables)
    volume_names = [] if visualization is None else list(dict.fromkeys([
        *visualization.volume_histogram_volumes,
        *visualization.table_volumes,
    ]))
    return engine.create_export_session_file(
        project.export_directory,
        project.surfaces,
        extra_variables=_extra_native_variables(visualization),
        metadata_volume_names=volume_names,
        created_variables=[] if visualization is None else visualization.created_variables,
    )


def create_import_session(
    import_files: list[Path | str],
    output_directory: Path | str,
    *,
    update_existing: bool = False,
) -> Path:
    from . import _engine as engine

    factory = (
        engine.create_update_import_session_file
        if update_existing
        else engine.create_import_session_file
    )
    return factory(
        Path(output_directory),
        [Path(p) for p in import_files],
    )


def _native_cfx_variable_name(name: str) -> str | None:
    from . import _engine as engine

    if name in engine.CALCULATED_FIGURE_VARIABLES:
        return None
    if name in engine.ORIGINAL_FIGURE_VARIABLES:
        return engine.ORIGINAL_FIGURE_VARIABLES[name]["cfx_variable"]
    return name


def create_temporary_visualization_export_session(
    output_directory: Path | str,
    surfaces: list[str],
    native_variable_names: list[str] | None = None,
    *,
    volumes: list[str] | None = None,
    export_volumes: list[str] | None = None,
    created_variables: list[CreatedVariableConfig] | None = None,
) -> tuple[Path, dict[str, Path], dict[str, Path], Path, Path]:
    """Create temporary data exports plus metadata for figures-only/sections.

    Metadata contains the current case name and the resolved CFX object path for
    each surface and volume. ``volumes`` are metadata-only unless also listed in
    ``export_volumes``. This avoids exporting huge volumetric point data when a
    volume is needed only for a table or for a histogram with explicit bounds.
    User-created volume objects are written as /VOLUME:<name>; mesh/case
    locations retain the raw user-entered name.
    """
    _validate_created_variables(created_variables or [])
    output_directory = Path(output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    session_file = output_directory / "visualization_geometry_export.cse"
    completion_file = output_directory / "visualization_export_complete.txt"
    metadata_file = output_directory / "visualization_metadata.txt"

    def unique(items):
        out, seen = [], set()
        for item in items or []:
            item = str(item).strip()
            if item and item not in seen:
                seen.add(item)
                out.append(item)
        return out

    unique_surfaces = unique(surfaces)
    unique_volumes = unique(volumes)
    unique_export_volumes = unique(export_volumes)
    unknown_export_volumes = [v for v in unique_export_volumes if v not in unique_volumes]
    if unknown_export_volumes:
        raise ValueError(
            "Volume data exports must also be present in the metadata volume list: "
            + ", ".join(unknown_export_volumes)
        )
    if not unique_surfaces and not unique_volumes:
        raise ValueError("No surfaces or volumes were supplied for temporary visualization export.")

    variables, seen_vars = [], set()
    for name in native_variable_names or []:
        cfx_name = _native_cfx_variable_name(str(name).strip())
        if cfx_name and cfx_name not in seen_vars:
            seen_vars.add(cfx_name)
            variables.append(cfx_name)
    if not variables:
        variables = ["Pressure"]

    surface_file_map = {
        surface: output_directory / f"visualization_surface_{i:03d}.csv"
        for i, surface in enumerate(unique_surfaces, start=1)
    }
    volume_file_map = {
        volume: output_directory / f"visualization_volume_{i:03d}.csv"
        for i, volume in enumerate(unique_export_volumes, start=1)
    }
    file_path = output_directory.as_posix()

    with open(session_file, "w", newline="") as f:
        f.write("# ================================================================\n")
        f.write("# TEMPORARY VISUALIZATION GEOMETRY / DATA EXPORT\n")
        f.write("# CFX-Post 23.2\n")
        f.write("# ================================================================\n\n")
        f.write("COMMAND FILE:\n  CFX Post Version = 23.2\nEND\n\n")

        from . import _engine as engine
        engine.write_created_variable_definitions(f, created_variables, include_relative_humidity=True)

        f.write(f'!$file_path = "{file_path}";\n')
        f.write(f'!$metadata_file = "{metadata_file.as_posix()}";\n')
        f.write(f'!$variables = "{", ".join(variables)}";\n\n')

        # Discover case name and object paths once, and write a durable metadata
        # sidecar because the normal completion marker is deleted by the GUI
        # executor after success.
        f.write('!open(META, ">$metadata_file") or die "Cannot create visualization metadata: $!";\n')
        # DATA READER exposes the active case name directly and is more
        # reliable than looking for a CASE object under the root tree.
        f.write('!$case_name = getValue("DATA READER", "Active Case Name");\n')
        f.write('!print META "CASE|$case_name\\n";\n\n')

        f.write('!$all_surface_objects = getChildrenByCategory("/", "surface");\n')
        f.write('!@surface_objects = split(",", $all_surface_objects);\n')
        f.write('!$all_volume_objects = getChildren("/", "VOLUME");\n')
        f.write('!@volume_objects = split(",", $all_volume_objects);\n\n')

        f.write(f"!$no_surfaces = {len(unique_surfaces)};\n")
        for i, surface in enumerate(unique_surfaces, start=1):
            f.write(f'!$surface[{i}] = "{surface}";\n')
            f.write(f'!$surface_filename[{i}] = "{surface_file_map[surface].name}";\n')
        f.write("\n")
        f.write("!for($i=1;$i<=$no_surfaces;$i++){\n")
        f.write('  !$location = "";\n')
        f.write("  !for($j=0;$j<scalar(@surface_objects);$j++){\n")
        f.write("    !$object = $surface_objects[$j];\n")
        f.write("    !$object_name = getObjectName($object);\n")
        f.write("    !if($object_name eq $surface[$i]){\n")
        f.write("      !$location = $object;\n")
        f.write("    !}\n")
        f.write("  !}\n")
        f.write('  !if($location eq \"\"){\n')
        f.write('    !die \"Visualization surface not found: $surface[$i]\\n\";\n')
        f.write('  !}\n')
        f.write('  !print META "SURFACE|$surface[$i]|$location\\n";\n')
        f.write("  EXPORT:\n")
        f.write("    CSV Type = CSV\n    Export Connectivity = Off\n    Export Coord Frame = Global\n")
        f.write("    Export File = $file_path/$surface_filename[$i]\n")
        f.write("    Export Geometry = On\n    Export Node Numbers = Off\n    Export Null Data = On\n")
        f.write("    Export Type = Generic\n    Include File Information = Off\n    Include Header = On\n")
        f.write("    Location List = $surface[$i]\n    Null Token = null\n    Overwrite = On\n    Precision = 8\n")
        f.write('    Separator = ", "\n    Spatial Variables = X,Y,Z\n')
        f.write("    Variable List = $variables\n    Vector Brackets = ()\n    Vector Display = Scalar\n")
        f.write("  END\n  >export\n")
        f.write("!}\n\n")

        # Resolve every requested volume for metadata, but export point data
        # only for volumes that actually need Python-side distribution statistics.
        f.write(f"!$no_volumes = {len(unique_volumes)};\n")
        for i, volume in enumerate(unique_volumes, start=1):
            f.write(f'!$volume[{i}] = "{volume}";\n')
        f.write("\n")
        f.write("!for($i=1;$i<=$no_volumes;$i++){\n")
        f.write("  !$location = $volume[$i];\n")
        f.write("  !for($j=0;$j<scalar(@volume_objects);$j++){\n")
        f.write("    !$object = $volume_objects[$j];\n")
        f.write("    !$object_name = getObjectName($object);\n")
        f.write("    !if($object_name eq $volume[$i]){\n")
        f.write("      !$location = $object;\n")
        f.write("    !}\n")
        f.write("  !}\n")
        f.write('  !print META "VOLUME|$volume[$i]|$location\\n";\n')
        f.write("!}\n\n")

        f.write(f"!$no_export_volumes = {len(unique_export_volumes)};\n")
        for i, volume in enumerate(unique_export_volumes, start=1):
            f.write(f'!$export_volume[{i}] = "{volume}";\n')
            f.write(f'!$export_volume_filename[{i}] = "{volume_file_map[volume].name}";\n')
        f.write("\n")
        f.write("!for($i=1;$i<=$no_export_volumes;$i++){\n")
        f.write("  EXPORT:\n")
        f.write("    CSV Type = CSV\n    Export Connectivity = Off\n    Export Coord Frame = Global\n")
        f.write("    Export File = $file_path/$export_volume_filename[$i]\n")
        f.write("    Export Geometry = On\n    Export Node Numbers = Off\n    Export Null Data = On\n")
        f.write("    Export Type = Generic\n    Include File Information = Off\n    Include Header = On\n")
        f.write("    Location List = $export_volume[$i]\n    Null Token = null\n    Overwrite = On\n    Precision = 8\n")
        f.write('    Separator = ", "\n    Spatial Variables = X,Y,Z\n')
        f.write("    Variable List = $variables\n    Vector Brackets = ()\n    Vector Display = Scalar\n")
        f.write("  END\n  >export\n")
        f.write("!}\n\n")
        f.write("!close(META);\n\n")

        f.write(
            f'!open(MARKER, ">{completion_file.as_posix()}") '
            'or die "Cannot create visualization export completion marker: $!";\n'
        )
        f.write('!print MARKER "Visualization export is successful\\n";\n')
        f.write("!close(MARKER);\n")

    return session_file, surface_file_map, volume_file_map, completion_file, metadata_file


def _section_config_dict(item: SectionVariableConfig) -> dict:
    return {
        "name": item.name,
        "lower": item.lower,
        "upper": item.upper,
        "number_of_contours": item.number_of_contours,
        "add_velocity_vectors": item.add_velocity_vectors,
        "create_streamlines": item.create_streamlines,
    }


def create_visualization_sessions(
    project: ProjectConfig,
    import_files: list[Path | str],
    settings: VisualizationConfig,
    *,
    plan_export_files: list[Path | str] | None = None,
    section_export_files: list[Path | str] | None = None,
    volume_export_files: list[Path | str] | None = None,
    surface_locations: dict[str, str] | None = None,
    volume_locations: dict[str, str] | None = None,
    case_name: str = "",
) -> tuple[Path, Path, dict]:
    """Create contour/section/surface+volume histogram sessions."""
    from . import _engine as engine
    from ._runtime import apply_visualization_config

    _validate_created_variables(settings.created_variables)
    apply_visualization_config(engine, settings)
    project.figures_directory.mkdir(parents=True, exist_ok=True)

    figure_configs = engine.parse_variable_entries(
        settings.figure_variables,
        "FIGURE_VARIABLES",
        "number_of_contours",
        settings.default_number_of_contours,
        2,
    ) if settings.figure_variables else []
    histogram_configs = engine.parse_variable_entries(
        settings.histogram_variables,
        "HISTOGRAM_VARIABLES",
        "divisions",
        settings.default_histogram_divisions,
        1,
    ) if settings.histogram_variables else []
    volume_histogram_configs = engine.parse_variable_entries(
        settings.volume_histogram_variables,
        "VOLUME_HISTOGRAM_VARIABLES",
        "divisions",
        settings.default_histogram_divisions,
        1,
    ) if settings.volume_histogram_variables else []
    section_configs = [_section_config_dict(item) for item in settings.section_variables]

    figure_variables = [item["name"] for item in figure_configs]
    histogram_variables = [item["name"] for item in histogram_configs]
    volume_histogram_variables = [item["name"] for item in volume_histogram_configs]
    table_variables = [str(name).strip() for name in settings.table_variables if str(name).strip()]
    table_surfaces = list(settings.table_surfaces)
    table_volumes = list(settings.table_volumes)
    # Backward compatibility for programmatic users: when the new table-specific
    # selections are omitted, preserve the old behavior (all normal surfaces and
    # the top-view variables). The GUI always supplies explicit selections.
    if settings.create_average_table and not table_surfaces and not table_volumes:
        table_surfaces = list(project.surfaces)
    if settings.create_average_table and not table_variables:
        table_variables = list(figure_variables)
    section_variables = [item["name"] for item in section_configs]

    if settings.create_plan_contours and (not project.surfaces or not figure_variables):
        raise ValueError("Top-view contours require at least one normal surface and one variable.")
    if settings.create_section_contours and (not settings.section_surfaces or not section_variables):
        raise ValueError("Section contours require at least one section and one native variable.")
    if settings.create_surface_histograms and (
        not settings.histogram_surfaces or not histogram_variables
    ):
        raise ValueError("Surface histograms require selected surfaces and variables.")
    if settings.create_volume_histograms and (
        not settings.volume_histogram_volumes or not volume_histogram_variables
    ):
        raise ValueError("Volumetric histograms require selected volumes and native variables.")
    if (settings.create_surface_histograms or settings.create_volume_histograms) and not str(case_name).strip():
        raise RuntimeError(
            "Could not determine the active CFD-Post case name required by histogram charts. "
            "The temporary/full export metadata did not contain DATA READER -> Active Case Name."
        )
    if settings.create_average_table:
        if (not table_surfaces and not table_volumes) or not table_variables:
            raise ValueError("The average table requires at least one selected surface or volume and one variable.")
        unknown_table_surfaces = [s for s in table_surfaces if s not in project.surfaces]
        if unknown_table_surfaces:
            raise ValueError(
                "Average-table surfaces must come from the master normal/top-view surface list:\n"
                + "\n".join(f"  - {s}" for s in unknown_table_surfaces)
            )
        if table_volumes:
            usable_volume_table_variables = [
                name for name in table_variables
                if name not in engine.CALCULATED_FIGURE_VARIABLES
            ]
            if not table_surfaces and not usable_volume_table_variables:
                raise ValueError(
                    "The table has only volume locations selected, but all selected variables are "
                    "thermal-comfort calculated variables. Select at least one native/created variable."
                )

    for name in [*section_variables, *volume_histogram_variables]:
        if name in engine.CALCULATED_FIGURE_VARIABLES:
            raise ValueError(f"'{name}' is calculated/imported and cannot be used for section/volume visuals.")

    # Figures-only: any non-section variable involved in normal contours or
    # either histogram type must have explicit lower/upper bounds.
    if settings.require_explicit_plan_bounds:
        by_name: dict[str, dict] = {}
        for cfg in [*figure_configs, *histogram_configs, *volume_histogram_configs]:
            by_name.setdefault(cfg["name"], cfg)
            if cfg["lower"] is None or cfg["upper"] is None:
                raise ValueError(
                    f"Figures-only mode requires lower and upper bounds for '{cfg['name']}'."
                )

    if plan_export_files is None:
        plan_export_files = [project.export_directory / f"export_{s}.csv" for s in project.surfaces]
    plan_export_files = [Path(p) for p in plan_export_files]
    if len(plan_export_files) != len(project.surfaces):
        raise ValueError("Plan export-file count does not match normal surfaces.")
    missing = [p for p in plan_export_files if not p.exists()]
    if missing:
        raise FileNotFoundError("Missing normal visualization export files:\n" + "\n".join(map(str, missing)))

    selected_plan_names = set(figure_variables) | set(histogram_variables) | (set(table_variables) if table_surfaces else set())
    needs_import_data = any(name in engine.CALCULATED_FIGURE_VARIABLES for name in selected_plan_names)
    if needs_import_data:
        import_files = [Path(p) for p in import_files]
        if len(import_files) != len(project.surfaces):
            raise ValueError("Import-file count does not match normal surfaces.")
        missing = [p for p in import_files if not p.exists()]
        if missing:
            raise FileNotFoundError("Missing import CSVs for calculated variables:\n" + "\n".join(map(str, missing)))
    else:
        import_files = [None] * len(project.surfaces)

    section_export_files = [Path(p) for p in (section_export_files or [])]
    if len(section_export_files) != len(settings.section_surfaces):
        if settings.section_surfaces:
            raise ValueError("Section geometry/data exports were not supplied for every section.")

    # Volumetric point-data CSVs are needed only when at least one shared
    # histogram range requires automatic 5th/95th-percentile bounds. With fully
    # explicit bounds, volume metadata alone is sufficient to create the chart.
    surface_hist_by_name = ({cfg["name"]: cfg for cfg in histogram_configs} if settings.create_surface_histograms else {})
    volume_data_required = any(
        (surface_hist_by_name.get(cfg["name"], cfg).get("lower") is None)
        or (surface_hist_by_name.get(cfg["name"], cfg).get("upper") is None)
        for cfg in volume_histogram_configs
    ) if settings.create_volume_histograms else False

    volume_export_files = [Path(p) for p in (volume_export_files or [])]
    if volume_data_required and len(volume_export_files) != len(settings.volume_histogram_volumes):
        raise ValueError(
            "Volume data exports are required for every histogram volume when "
            "automatic histogram bounds are used."
        )
    if not volume_data_required:
        volume_export_files = []

    statistics = engine.collect_plot_statistics(
        project.surfaces,
        plan_export_files,
        import_files,
        figure_configs,
        settings.histogram_surfaces if settings.create_surface_histograms else [],
        histogram_configs if settings.create_surface_histograms else [],
        settings.section_surfaces if settings.create_section_contours else [],
        section_export_files if settings.create_section_contours else [],
        section_configs if settings.create_section_contours else [],
        volume_histogram_volumes=settings.volume_histogram_volumes if settings.create_volume_histograms else [],
        volume_export_files=volume_export_files if settings.create_volume_histograms else [],
        volume_histogram_configs=volume_histogram_configs if settings.create_volume_histograms else [],
    )

    create_session = engine.create_figures_session_file(
        project.figures_directory,
        project.surfaces,
        figure_variables,
        settings.histogram_surfaces if settings.create_surface_histograms else [],
        histogram_variables if settings.create_surface_histograms else [],
        statistics,
        section_surfaces=settings.section_surfaces if settings.create_section_contours else [],
        section_variables=section_configs if settings.create_section_contours else [],
        create_average_table=settings.create_average_table,
        table_surfaces=table_surfaces if settings.create_average_table else [],
        table_volumes=table_volumes if settings.create_average_table else [],
        table_variables=table_variables if settings.create_average_table else [],
        average_table_name=settings.average_table_name,
        created_variables=settings.created_variables,
        create_plan_contours=settings.create_plan_contours,
        create_plan_streamlines=settings.create_plan_velocity_streamlines,
        vector_samples=settings.velocity_vector_samples,
        streamline_samples=settings.streamline_samples,
        volume_histogram_volumes=settings.volume_histogram_volumes if settings.create_volume_histograms else [],
        volume_histogram_variables=volume_histogram_variables if settings.create_volume_histograms else [],
        surface_locations=surface_locations or {},
        volume_locations=volume_locations or {},
        case_name=case_name,
    )
    print_session = engine.create_print_figures_session_file(
        project.figures_directory,
        project.surfaces if settings.create_plan_contours else [],
        figure_variables if settings.create_plan_contours else [],
        settings.histogram_surfaces if settings.create_surface_histograms else [],
        histogram_variables if settings.create_surface_histograms else [],
        section_surfaces=settings.section_surfaces if settings.create_section_contours else [],
        section_variables=section_configs if settings.create_section_contours else [],
        create_plan_streamlines=settings.create_plan_velocity_streamlines,
        volume_histogram_volumes=settings.volume_histogram_volumes if settings.create_volume_histograms else [],
        volume_histogram_variables=volume_histogram_variables if settings.create_volume_histograms else [],
        create_average_table=settings.create_average_table,
        average_table_name=settings.average_table_name,
    )
    return create_session, print_session, statistics
