# Changelog

## 1.0.0 — first public release preparation

This public release starts at v1.0.0. It is based on the supplied internal GUI v11.1 package, whose Python metadata previously used 0.7.1. Those internal labels do not represent prior public releases.

- Organized source, detailed documentation, screenshot placeholders, setup helper, and small examples around one root README.
- Standardized Python distribution and module versions to 1.0.0.
- Removed author-machine Python search paths and private project defaults from the active engine.
- Replaced the source-rewriting setup helper with `scripts/setup_environment.py`, which installs this checkout into the selected interpreter.
- Replaced large case-specific examples with guarded examples for all three modes and custom CEL variables; added a clearly synthetic surface CSV demonstration.
- Allowed documentation PNGs to be committed while ignoring generated run outputs.
- Omitted the duplicate legacy standalone script from the public layout; the original supplied archive is unchanged.
- Documented existing limitations, import semantics, tab-separated table exports, and compatibility/validation status.

The underlying thermal calculations and CFX session generation algorithms are retained. This preparation is not a claim of live CFX-Post validation. License, author/profile fields, and screenshots remain for the maintainer to supply.
