# Examples

[Back to README](../README.md)

Run these from the repository root using the environment in which you installed the dependencies. Each script has a `main()` guard, so importing it does not start a workflow. `_bootstrap.py` makes the checkout's source importable without an editable install; dependencies must still be installed.

| Script | Open CFX needed? | Inputs to supply | Output folder under repository |
| --- | --- | --- | --- |
| [thermal_comfort_csvs_only.py](thermal_comfort_csvs_only.py) | No | None for the synthetic demonstration | `runs/csv-demo/` |
| [full_automation.py](full_automation.py) | Yes | Loaded case and exact `SURFACE` name | `runs/full-automation/` |
| [thermal_comfort_only.py](thermal_comfort_only.py) | Yes | Prior full-run exports and existing imported surface | Updates `runs/full-automation/import/` |
| [figures_only.py](figures_only.py) | Yes | Loaded case and exact `SURFACE` name | `runs/figures-only/` |
| [custom_cel_variable.py](custom_cel_variable.py) | Yes | Loaded case with Temperature and exact `SURFACE` name | `runs/custom-cel/` |

## Start with the CSV-only demonstration

```powershell
.\.venv\Scripts\python.exe examples/thermal_comfort_csvs_only.py
```

This reads the four-point synthetic surface in `data/`, calculates default comfort outputs, and writes `import_Demo_Surface.csv` and an unexecuted `import_session.cse`. It neither requires a CFX result file nor imports anything into CFX. The current engine still requires Windows and the installed dependencies. Review column presence and face preservation; no reference numerical answers or CFD validation claims are supplied.

## Use your own CFX case

Replace the `Occupied Plane` placeholder with the exact name of a surface that already exists in your loaded case. Adjust output locations, comfort settings, and illustrative plotting bounds. Then show the Command Editor and run the relevant script, for example:

```powershell
.\.venv\Scripts\python.exe examples/full_automation.py
.\.venv\Scripts\python.exe examples/figures_only.py
```

Run scripts separately. CFX-dependent examples actively control the current CFX session. Full automation imports fresh surfaces; the thermal-only update example expects those imported objects to exist already. No mesh, `.res`, or `.cst` demonstration case is bundled.

The full/figures/custom-CEL examples generate a print session but leave automatic printing off. Set `execute_print_session=True` to export PNGs and tables during the run, or load the generated print session in CFX afterward.

## IDLE

Open an example in IDLE, edit its configuration constants, and press F5. Use the same Python environment as installation and retain the complete repository layout.

## Data and output conventions

`data/` contains only documented synthetic input. `runs/` is generated and ignored by Git. Do not place real simulation results in the tracked example-data folder. See the [data README](data/README.md) and [user guide](../docs/USAGE.md) before adapting scripts.
