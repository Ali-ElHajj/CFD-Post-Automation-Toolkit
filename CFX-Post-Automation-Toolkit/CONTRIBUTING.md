# Contributing

Start with the [README](README.md) and [architecture guide](docs/ARCHITECTURE.md). The repository currently has no selected license; clarify contribution/reuse terms with the maintainer before contributing.

## Report a problem

Include the toolkit version, Windows/Python/CFX versions, operating mode, expected and actual behavior, progress/error text, and the smallest reproducible configuration. Attach the generated `.cse` file and an anonymized CSV if relevant and permitted. For automation problems, describe the Command Editor window layout and scaling.

## Propose a change

Open an issue describing the problem or workflow first for substantial changes. Keep pull requests focused and update the relevant guide/example whenever behavior changes. Use the public configuration/workflow interfaces in examples. Do not introduce machine-specific paths or commit generated simulation outputs.

## Validate a change

Install in a Windows environment with `python -m pip install -e .`. Check Python syntax and run the CSV-only example. For numerical changes, compare against independently established reference values and explain tolerances; the synthetic example is only a smoke demonstration. For CFX session or UI automation changes, test in a live case and record the CFX version, locations, session results, and output files. Never describe syntax checks as live CFX validation.

Review local documentation links, screenshot paths, version metadata, and whether examples run only under their main guard. Add meaningful regression checks when changing behavior. There was no automated test suite in the supplied package; current preparation checks are described in [VALIDATION.md](docs/VALIDATION.md).
