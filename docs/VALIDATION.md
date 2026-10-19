# Release validation

[Back to README](../README.md)

## v1.1.0 preparation — October 19, 2026

**Syntax/session-generation tested; not live-validated in CFX-Post.**

- During initial preparation under internal-version labeling, installed the package and its declared dependencies in an isolated Windows Python 3.10.10 environment. That editable packaging check succeeded at version 11.3.0; `pip check` reported no broken requirements.
- After relabeling the public release to 1.1.0, reran syntax and all seven regression checks against the Desktop source copy and checked package/module metadata consistency. No fresh installation was performed for the version-only relabel.
- Syntax-checked all 19 Python files in source, launcher, examples, setup helper, and regression tests.
- Seven offline regression tests passed using generated synthetic CSVs. They cover imported USER SURFACE creation, qualified contour/histogram/average variables, explicit ranges and counts, shared average columns and missing cells, all three average blocks, per-surface percentile fallback, common camera framing, and matching/differing GUI variable sets.
- Regression checks exposed and verified fixes for constant average-only fields and missing/shared imported contour legends. These are small corrections beyond the supplied ZIP, recorded in the changelog.
- Retained existing public examples, license, and screenshots. Screenshots are historical and do not establish validation of v1.1.0.
- Checked prepared text for personal paths, known private defaults, credential patterns, and broken relative documentation links. The original ZIP is not distributed because it contains machine/private project defaults; the release ZIP is built from the cleaned repository content.

Reproduce the session checks after installing the package:

```powershell
python -m unittest discover -s tests -v
python -m pip check
```

These tests inspect generated text and Python statistics. They do not execute CFX sessions, verify CCL/CEL acceptance, measure numerical accuracy, or validate rendered charts, tables, or camera views. No live GUI interaction or thermal numerical regression suite was performed during this preparation.

Before relying on v1.1.0, test one CSV, then two CSVs with shared and unique variables in CFX-Post. Confirm imported objects, variable qualification, `areaAve` on imported surfaces, contour/histogram ranges, blank table cells, camera framing, and printing. Record the exact CFX/Python versions and outcomes.

## Historical checks performed during v1.0.0 preparation

- Python syntax: all 18 Python files compile.
- Core preservation: engine function/class syntax trees match the supplied source; other runtime modules are unchanged except version metadata.
- Metadata: package and module versions both read 1.0.0; configuration/workflow imports succeed.
- Examples: all five import without executing workflows, construct real configuration objects, and bind to the current API signatures using captured workflow calls. These are configuration checks, not executed CFX/calculation runs.
- Synthetic data: four numeric rows, required headers, Kelvin-unit recognition, percentage-humidity naming, and face indices checked. Numerical calculations and CFX import were not run.
- Documentation links, file layout, and tracked text were checked for broken local targets, control characters, and author-machine paths.

## Historical v1.0.0 environment limitations

The preparation environment has Python 3.10.10 but does not have NumPy, pandas, SciPy, pythermalcomfort, PsychroLib, or pywin32 installed. No dependency installation, numerical example execution, GUI launch, or live CFX run was performed. The setup helper was syntax-checked; its pip installation step was not executed. No wheel build was performed.

Before publishing a tested compatibility claim, install the package in the target Windows environment, run the CSV-only example, and exercise each mode against a small CFX case. Check numerical results independently, imported face connectivity, generated CFX objects, and printed images/tables. Record the exact Python and CFX versions and outcomes. Syntax/API checks alone cannot establish those results.
