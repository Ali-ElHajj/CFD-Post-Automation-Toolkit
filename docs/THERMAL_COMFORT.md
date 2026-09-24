# Thermal-comfort calculations

[Back to README](../README.md)

This describes the implementation in `src/cfxpost_toolkit/_engine.py`, not an independent validation of its numerical models.

## Input format

Use CFX Generic surface CSVs named `export_<surface>.csv`, containing `[Name]`, `[Data]`, unit-bearing column headers, and `[Faces]`. Original face lines are carried into the calculated import CSV.

| Required field | Expected meaning |
| --- | --- |
| `X`, `Y`, `Z` | Coordinates in metres; the header search explicitly looks for `X [ m ]` |
| `Temperature` | Air temperature with a recognized Kelvin or Celsius unit header |
| `Radiation Temperature` | Used as mean radiant temperature, with Kelvin/Celsius unit detection |
| `Relative Humidity Percentage` | Humidity in percent, created in CFX as `Relative Humidity*100` |
| `Velocity` | Speed in m/s |
| `Turbulence Kinetic Energy` | TKE in m²/s² |

All core fields are required by the loader even if a particular optional calculation is disabled. The toolkit export supplies these fields. The [synthetic CSV](../examples/data/export_Demo_Surface.csv) illustrates the layout; it is not a CFD result or validation dataset.

## Preprocessing

Kelvin air/radiant temperatures are converted to Celsius. Air speed is floored at `minimum_velocity` (default 0.05 m/s). Humidity is assumed to already be in percent, with no automatic fraction/percentage guessing.

Rows missing a core CFD value are repaired from the nearest fully valid spatial point using SciPy `cKDTree`. The complete core-field set is copied from that point. Repair fails if no valid point exists or the maximum distance exceeds `max_cleaning_distance` (default 1 m). A `_cleaned.csv` diagnostic is written beside the input; the original input is not rewritten. Remove diagnostics from directories scanned using `export_*.csv` before rerunning.

## Models and outputs

| Selection | Output columns / implementation |
| --- | --- |
| Always | `Relative_Air_Speed` from `v_relative`; `clo_dynamic_ashrae` supplies dynamic clothing insulation |
| PMV/PPD | `PMV`, `PPD` from `pmv_ppd_ashrae`, with relative air speed and dynamic clothing |
| SET | `SET` from `set_tmp`, with floored local velocity and dynamic clothing |
| UTCI | `UTCI` from `utci`, with floored local velocity directly |
| Draft rate | `Turbulence_Intensity`, `Draft_Rate` using the formulas below |
| Clothing model | `Clothing_Surface_Temperature`, `Convective_HTC`, `Radiative_HTC` from the internal iterative model |
| Operative temperature | `Operative_Temperature`; also invokes the clothing model to obtain heat-transfer coefficients |
| Psychrometrics | `Wet_Bulb_Temperature`, `Dew_Point_Temperature`, `Humidity_Ratio` using PsychroLib SI functions |

With air temperature `Ta`, mean radiant temperature `Tr`, floored velocity `v`, TKE `k`, and turbulence intensity `Tu` in percent:

```text
Tu = 100 * sqrt((2/3) * k) / v
Draft_Rate = clip((34 - Ta) * max(v - 0.05, 0)^0.62
                  * (0.37 * v * Tu + 3.14), 0, 100)
Operative_Temperature = (hr * Tr + hc * Ta) / (hr + hc)
```

Psychrometric calls convert percent humidity to a fraction. Pressure is used for wet-bulb temperature and humidity ratio. Temperatures in calculated CSV fields are in Celsius; speeds are in m/s, PPD/draft rate/turbulence intensity in percent, heat-transfer coefficients in W/(m²·K), and humidity ratio in kg water/kg dry air. PMV is dimensionless.

## Defaults

`ThermalComfortConfig` defaults to 1.7 met, 0.57 clo, minimum velocity 0.05 m/s, pressure 101325 Pa, emissivity 0.95, and maximum cleaning distance 1 m. PMV/PPD and operative temperature are enabled; other optional groups are disabled. MET/clo apply uniformly to all points in a run. The GUI exposes presets plus manual values; additional configuration is available through Python.

## Interpretation and limitations

- PMV/PPD, SET, and UTCI calls set `limit_inputs=False` and `round_output=False`. A returned number is not evidence that the inputs meet a model's applicability limits.
- UTCI receives local CFD velocity directly; no wind-height conversion is performed.
- Radiation Temperature is used as mean radiant temperature. Confirm that interpretation fits the simulation's radiation model and exported field.
- Nearest-neighbor repair changes missing data, and the minimum-speed floor changes low speeds. Review these settings and repaired-point diagnostics for the case.
- Operative temperature is heat-transfer weighted, not simply the arithmetic mean of air and radiant temperatures.
- The code may emit warnings or invalid values for unsuitable inputs. This release does not certify thermal comfort or compliance with any standard.
