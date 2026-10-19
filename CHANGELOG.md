# Changelog

## v1.1.0 — imported CSV visualization and averages

Based on internal GUI revision v11.3; the Python package version is 1.1.0.

- Integrated the supplied GUI v11.3 source while retaining the public repository layout, examples, installation helper, license, and prior history.
- Corrected two packaging-time regression findings: constant average-only fields no longer require plot bounds, and every imported contour gets a legend tied to its own surface/range.
- Added ready-made CSV surface imports with independent contour, histogram, and average selections.
- Consolidated matching imported variable sets into one GUI configuration table.
- Added an imported-surface averages block with one column per shared variable and blank cells for missing selections.
- Moved averages controls to the end and aligned the table-name input.
- Added qualified imported variables, numeric/per-surface percentile bounds, and imported geometry in common camera framing.
- Runs the dedicated CSV import session before visual creation.
- Retained portable defaults; excluded personal paths, private project defaults, duplicate legacy code, and the old source-rewriting setup helper from the release package.
- Updated usage, validation, release notes, and version metadata.

Public v1.1.0 follows v1.0.0. Internal revision labels identify the source packages and are not public release numbers. Syntax and generated-session checks do not establish live CFX-Post compatibility. See [release notes](docs/RELEASE_NOTES_v1.1.0.md).

## 1.0.0 — first public release preparation

This public release starts at v1.0.0 released on September 24th, 2026. It is based on the supplied internal GUI v11.1 package, whose Python metadata previously used 0.7.1. Those internal labels do not represent prior public releases.

- Organized source, detailed documentation, screenshot placeholders, setup helper, and small examples around one root README.
- Standardized Python distribution and module versions to 1.0.0.
- Removed author-machine Python search paths and private project defaults from the active engine.
- Replaced the source-rewriting setup helper with `scripts/setup_environment.py`, which installs this checkout into the selected interpreter.
- Replaced large case-specific examples with guarded examples for all three modes and custom CEL variables; added a clearly synthetic surface CSV demonstration.
- Allowed documentation PNGs to be committed while ignoring generated run outputs.
- Omitted the duplicate legacy standalone script from the public layout; the original supplied archive is unchanged.
- Documented existing limitations, import semantics, tab-separated table exports, and compatibility/validation status.

The underlying thermal calculations and CFX session generation algorithms are retained. This preparation is not a claim of live CFX-Post validation. License, author/profile fields, and screenshots remain for the maintainer to supply.
