# Release validation

[Back to README](../README.md)

## Checks performed during v1.0.0 preparation

- Python syntax: all 18 Python files compile.
- Core preservation: engine function/class syntax trees match the supplied source; other runtime modules are unchanged except version metadata.
- Metadata: package and module versions both read 1.0.0; configuration/workflow imports succeed.
- Examples: all five import without executing workflows, construct real configuration objects, and bind to the current API signatures using captured workflow calls. These are configuration checks, not executed CFX/calculation runs.
- Synthetic data: four numeric rows, required headers, Kelvin-unit recognition, percentage-humidity naming, and face indices checked. Numerical calculations and CFX import were not run.
- Documentation links, file layout, and tracked text were checked for broken local targets, control characters, and author-machine paths.

## Not validated here

The preparation environment has Python 3.10.10 but does not have NumPy, pandas, SciPy, pythermalcomfort, PsychroLib, or pywin32 installed. No dependency installation, numerical example execution, GUI launch, or live CFX run was performed. The setup helper was syntax-checked; its pip installation step was not executed. No wheel build was performed.

Before publishing a tested compatibility claim, install the package in the target Windows environment, run the CSV-only example, and exercise each mode against a small CFX case. Check numerical results independently, imported face connectivity, generated CFX objects, and printed images/tables. Record the exact Python and CFX versions and outcomes. Syntax/API checks alone cannot establish those results.
