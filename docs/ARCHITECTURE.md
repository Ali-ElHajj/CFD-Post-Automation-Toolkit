# Architecture

[Back to README](../README.md)

| File | Responsibility |
| --- | --- |
| `CFX_Post_Toolkit_GUI.py` | Adds local `src/` to the import path and launches the desktop wizard |
| `src/cfxpost_toolkit/gui.py` | Tkinter pages, selections, validation, worker thread, progress display |
| `src/cfxpost_toolkit/config.py` | Dataclasses for project, thermal, visualization, CEL, and automation settings |
| `src/cfxpost_toolkit/workflows.py` | Coordinates full, thermal-only, and visualization workflows and temporary cleanup |
| `src/cfxpost_toolkit/sessions.py` | Validates settings and builds CFX sessions/temporary metadata exports |
| `src/cfxpost_toolkit/thermal_comfort.py` | Single-file, file-list, and directory calculation wrappers |
| `src/cfxpost_toolkit/cfx.py` | Public wrappers for Command Editor discovery and session execution |
| `src/cfxpost_toolkit/_runtime.py` | Applies dataclass settings to the existing engine globals |
| `src/cfxpost_toolkit/_engine.py` | Calculation implementation, CSV parsing, CCL/Power Syntax generation, Windows automation |
| `src/cfxpost_toolkit/progress.py` | Progress event and callback support |
| `src/cfxpost_toolkit/__init__.py` | Public configuration exports and version |

## Entry points

- `run_full_workflow(config)`: exports from open CFX, calculates, imports, creates visuals, optionally prints.
- `run_thermal_comfort_directory_workflow(...)`: processes matching CSVs and creates an update-existing import session; execution defaults off.
- `run_thermal_comfort_workflow(config, ...)`: processes specific named surfaces; `update_existing_imports` controls import semantics.
- `run_visualization_workflow(config, ...)`: exports temporary geometry/metadata and creates visuals. Even `execute_creation=False` still requires CFX for temporary export; it is not an offline dry run.
- `process_file`, `process_files`, `process_directory`: calculate CSV outputs without executing CFX.

The GUI sends progress events through a queue. CFX execution uses visible window automation and completion markers rather than a headless solver or remote API. Generated session files remain available for inspection.

The engine uses shared module-level configuration, so concurrent workflows in one Python process are not supported. Its legacy standalone `main()` is retained internally but is not a documented user entry point; use the GUI or public wrappers. The old duplicate standalone script is omitted from this public layout.
