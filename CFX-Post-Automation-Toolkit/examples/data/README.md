# Synthetic surface input

`export_Demo_Surface.csv` is a manually constructed format demonstration: four coplanar points, one quadrilateral face, air temperature 24–25.5 °C, radiant temperature 25–26.5 °C, humidity 50%, speed 0.10–0.25 m/s, and TKE 0.001 m²/s². Temperatures are encoded in Kelvin to exercise the loader's unit conversion.

It is not a result from a CFD simulation, a validated thermal-comfort benchmark, or an Ansys-provided example. The face connectivity is zero-based, as used for the demonstration's CFX Generic-style layout. The offline script preserves these lines; a live CFX import of this synthetic file has not been validated.

Run `thermal_comfort_csvs_only.py` from the parent examples folder to process it. The sample has no missing values, so it does not exercise nearest-neighbor repair. Do not use its tiny geometry or illustrative values for engineering decisions.
