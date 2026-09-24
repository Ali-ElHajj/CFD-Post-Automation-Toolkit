# User guide

[Back to README](../README.md)

## Full automation

1. Load your CFX result and show the Command Editor.
2. Select **Full automation**, choose a run folder, and add normal/top-view surface names.
3. Choose MET/clo presets or **Other** for manual values. Select the comfort calculations you need.
4. Optionally enable custom CEL-derived variables. Full mode exports them alongside required native fields.
5. Configure top-view contours (mandatory in the GUI), then any section contours, histograms, and average table.
6. Select variables independently in each visual panel. Enabling a calculation makes its variables available; it does not select them everywhere.
7. Set bounds/counts, camera and image settings, then choose whether to execute the print session automatically.
8. Run and review generated sessions, imported surfaces, figures, and logs.

The workflow creates `export/`, `import/`, and `figures/`. It executes export, comfort calculation, fresh Generic Data import, and figure creation in sequence. Printing is optional; the print session is generated even when automatic printing is off.

## Thermal comfort only

1. Select the directory containing original `export_*.csv` surface files and a separate destination for calculated imports.
2. Select thermal settings and calculations.
3. Leave automatic import off to calculate without an open CFX session.
4. If updating an existing CFX state, load that state, show the Command Editor, and enable import execution.

The GUI creates an update-in-place `import_session.cse`. It targets existing objects named `Imported Thermal Comfort Results <surface>` and updates their data-file references. It assumes these imported USER SURFACEs already exist; use full automation for first-time imports. Python callers needing fresh imports can use `create_import_session(..., update_existing=False)` explicitly.

This mode does not create new figures or rerun export. Directory processing matches `export_*.csv`, including `_cleaned.csv` diagnostics from an earlier repair. Keep only original compatible exports in the input directory; the cleaned diagnostic lacks the original unit-bearing headers and should not be fed back into this mode.

## Figures / table / histograms only

1. Load the intended CFX result and show the Command Editor.
2. Choose a dedicated output directory and at least one visual type.
3. Add only the normal surfaces, section surfaces, and volumes required by those visuals.
4. Select native variables, manually named available variables, or enabled CEL-derived variables.
5. Supply explicit lower and upper bounds for top-view and histogram variables. Counts may use defaults. Section bounds may inherit available normal bounds or use section statistics.
6. Run; enable automatic printing if you also want image/table files.

Temporary exports obtain geometry and metadata. Volumes used only for tables or explicit-bound histograms require metadata rather than full point-data exports. Output files go directly into the selected directory. Temporary files are removed after session generation, including on errors where cleanup is possible.

Do not select built-in calculated thermal-comfort names such as `PMV` in this workflow: it does not pass thermal import CSVs to visualization generation. A manual name is not a way to bypass that restriction. Use full automation for comfort contours and surface histograms.

## Locations and selections

- **Normal surfaces:** the shared registry for top views, surface histograms, and table surface selections.
- **Sections:** a separate list for section contours; each section gets its own geometry-derived camera and clip plane.
- **Volumes:** a shared name registry between volume histograms and the average table. Adding/removing a volume updates both panels.
- **Manual variable names:** one shared registry, with independent selections per panel. The variable must actually exist on the selected CFX location.
- **Calculated comfort variables:** surface-based; excluded from sections, volume histograms, and the table's volume block.

Names are also used in generated session text and file paths. Use simple names compatible with Windows filenames; avoid path separators, quotes, and CFX control syntax.

## Bounds and visuals

Python contour/histogram entries accept `Variable` or `Variable, lower, upper, count`. Blank numeric fields use automatic bounds/default counts where the mode allows them. For example:

```python
figure_variables=["Temperature, 18, 28, 21", "Velocity, 0, 1, 21"]
histogram_variables=["Temperature, 18, 28, 20"]
```

Automatic ranges use common 5th/95th-percentile statistics. Surface and volume histogram ranges/divisions are shared for a variable. Native Temperature and Radiation Temperature display in Celsius through the existing CEL conversion; custom variables retain their own units.

Section vector overlays use one vector object per section. Velocity streamlines are separate figures and have a global sample setting independent of vector samples. Choose Velocity in the corresponding panel when requesting its streamline figures.

The average table can contain **Surface Averages**, **Volume Averages**, or both. Surface calculations use `areaAve`, volume calculations use `volumeAve`. Relative Humidity uses the generated percentage variable internally. Thermal-comfort variables only contribute to the surface block.

## Custom CEL variables

Available in full and figures-only modes. Enter a unique variable name and a valid CEL expression, then enable it. The GUI supplies a distinct internal expression name. Python callers provide that name explicitly:

```python
CreatedVariableConfig(
    name="Temperature Difference",
    expression="Temperature - 293.15[K]",
    expression_name="Temperature Difference expression",
)
```

Select the new variable independently in any applicable visual panel. CFX evaluates the expression; units, field availability, and dimensional consistency are the user's responsibility. The Relative Humidity Percentage definition is locked and remains separate from user-defined expressions.

## Printing and reruns

The print session uses CFX hardcopy for figures, chart printing for histograms, and table save for the average table. To print manually, load `print_figures_session.cse` through CFX-Post after figure creation. Files use the configured directory and names recorded in that session.

Save outputs in a new folder when comparing settings. Rerunning a workflow can replace generated files and named CFX objects. Full-mode import uses fresh Generic Data imports and may duplicate imported objects in an already-populated state; use thermal-only's update behavior when recalculating those imports.
