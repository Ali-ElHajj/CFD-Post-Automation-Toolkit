# Toolkit v1.1.0

This revision integrates `cfxpost_toolkit_project_with_gui_v11_3.zip` into the existing public package layout. The Git tag/release label is `v1.1.0`; Python distribution and module versions are `1.1.0`. The previous public version was `1.0.0` (internal GUI v11.1).

## Changes

- Corrected two packaging-time regression findings: constant average-only fields no longer require plot bounds, and every imported contour gets a legend tied to its own surface/range.
- Ready-made CSV surface contours, histograms, and averages with independent variable selection.
- One shared settings table when all imported CSVs have matching variable sets.
- Three average-table blocks: surfaces, volumes, and imported surfaces. Shared imported variables use one column, with blank cells for unavailable/unselected values.
- Averages controls placed last; table-name field aligned with its checkbox.
- Qualified imported variables, per-surface 5th/95th-percentile fallback, and common camera framing including imported geometry.
- A dedicated imported-CSV session runs before figure/table creation.

## Installation and upgrade

Extract the clean release ZIP into a new directory and follow [installation](INSTALLATION.md). Install this checkout using `py -m pip install -e .`, then launch `CFX_Post_Toolkit_GUI.py` using that interpreter. Keep run data outside the source directory. No saved-configuration migration is provided.

The release ZIP is an equivalent, sanitized source distribution, not a byte-for-byte copy of the input archive. It preserves public documentation, examples, and the safe setup helper; it excludes machine-specific paths, private project defaults, duplicate legacy code, and environment/build outputs. The original archive remains unchanged locally.

## Validation and limitations

v1.1.0 is syntax/session-generation tested, but **not live-validated in CFX-Post**. Generated sessions target 23.2. Review [validation details](VALIDATION.md), especially imported-variable qualification, imported-surface `areaAve`, and visual output behavior. No new numerical accuracy or standards-compliance claim is made.
