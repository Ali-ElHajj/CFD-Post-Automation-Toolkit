# Installation and troubleshooting

[Back to README](../README.md)

## Standard installation

Use Windows with Python 3.10+ and Tkinter. From the extracted repository root:

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\python.exe CFX_Post_Toolkit_GUI.py
```

Using the environment's Python explicitly avoids activation-policy issues. `pip install -e .` installs the package from this source tree and its declared dependencies. Keep the checkout in place while using that editable installation.

For a dependency-only setup, `python -m pip install -r requirements.txt` installs the required libraries. The root launcher and examples add the local `src/` directory automatically, so they can then run directly from the checkout. Use one installation approach in the interpreter that will launch the toolkit.

## IDLE setup

1. Extract the complete repository; keep its directory structure intact.
2. Open `scripts/setup_environment.py` in IDLE and press F5.
3. The helper runs pip in that same Python installation and verifies engine/GUI imports in a fresh process. It requires access to the package index and permission to install into that environment.
4. Open `CFX_Post_Toolkit_GUI.py` in the same IDLE installation and press F5.

The helper no longer edits Python paths inside the engine. If you prefer an isolated environment, use the standard installation, then launch IDLE with `.\.venv\Scripts\python.exe -m idlelib`.

## Preparing CFX-Post

Open the correct result, create the surfaces/sections/volumes you intend to reference, and show the Command Editor. Names entered in the toolkit must match CFX location names. Save your CFX state before the first run and use a dedicated output folder. The workflow interacts with the current case and may create or update named objects.

## Troubleshooting

| Symptom | Check |
| --- | --- |
| Missing Python module | Install using the same interpreter that launches the GUI; verify its environment rather than adding machine-specific paths |
| `tkinter` unavailable | Use a Python installation that includes Tcl/Tk support |
| Command Editor not found | Open the Command Editor; the default title match is `Command Editor` |
| Commands paste but do not run | Keep the editor visible; check window scaling/focus and relative click coordinates in `CFXAutomationConfig` |
| Workflow waits for CFX completion | Inspect the Command Editor for errors and the generated session/marker paths |
| Missing input variable | Use the toolkit export or match the required Generic CSV schema exactly |
| A second thermal-only run fails on a cleaned CSV | Move `export_*_cleaned.csv` diagnostics out of the input folder; the directory glob also matches them |
| Duplicate imported surfaces | Full automation creates fresh Generic Data imports; thermal-only updates existing imported surfaces by name |
| Figures-only fails for `PMV` | Use full automation; built-in comfort variables require accompanying import CSVs |
| No PNG/table files | Figure creation and printing are separate; execute `print_figures_session.cse` or enable automatic printing |
| Table appears as one spreadsheet column | Import it using a tab delimiter despite its `.csv` extension |
| Histogram active-case error | Confirm the result is loaded and metadata contains the active CFX case name |

The current package imports Windows libraries even for CSV-only calculations. Linux/macOS operation is not supported by this release.
