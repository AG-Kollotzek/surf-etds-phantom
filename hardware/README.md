# Hardware

## The machine

The SURF Test Unit is a low-cost motion phantom with three stepper-driven
degrees of freedom:

- **H**, a horizontal slide, −45…+25 mm;
- **V**, a vertical slide, −35…+50 mm;
- **R**, a rotation stage on a nominal 1:2 bevel gear, −30…+120°.

The ranges are the firmware limits. H and V run at 800 steps/mm and R at
16.156 steps/°. Each axis has a CL57T closed-loop driver, and all three are
controlled by one Arduino Nano. A second Nano regulates two heating pads to a
skin-like surface temperature, using one DS18B20 sensor per pad and MOSFET
switching. A PC terminal runs scripted trajectories while the phantom sits on
the treatment couch. The rig was built to validate a surface-guidance system
in a radiotherapy treatment room.

H and V each have one normally closed homing switch, at the positive end. R
has **no endstop** and is zeroed wherever it stands. There is **no hardware
emergency stop**. Read [`../docs/safety.md`](../docs/safety.md) before
powering anything on.

**No CAD model, drawing, schematic, wiring diagram or photograph exists in this
repository.** Everything documented here was reconstructed from the firmware,
the terminal, the calibration files and a lab notebook.

## Contents

| File | What it is |
|---|---|
| [`pinout.md`](pinout.md) | Pin assignment of both Nanos (the only pinout record), with the comment/code contradictions found in the firmware |
| [`bom.csv`](bom.csv) | Bill of materials. **Every supplier, part-number and price cell is empty** |
| [`assembly.md`](assembly.md) | Assembly and commissioning: established facts, homing sequence, working-zero convention, backlash data, first power-on checks |
| [`calibration/heating-pad-calibration.csv`](calibration/heating-pad-calibration.csv) | Raw thermal calibration, 12 points. `;`-separated, German decimal commas, CRLF line endings in the working copy |
| [`calibration/heating-pad-calibration.xlsx`](calibration/heating-pad-calibration.xlsx) | The same 12 rows as a spreadsheet. It contains no fit: its drawing part is empty |
| [`calibration/heating-pad-calibration.png`](calibration/heating-pad-calibration.png) | Plot of internal (DS18B20), external (Testo 925) and setpoint temperature against setpoint, with the internal-minus-external gradient. No regression line |
| [`../docs/calibration/backlash-measurement-raw.txt`](../docs/calibration/backlash-measurement-raw.txt) | Raw lab notebook (German) of the H and R backlash sessions, 09-10.03.26. Translated and interpreted in [`assembly.md`](assembly.md) §3.3 and §4.2 |
| [`../docs/calibration/reference-geometry.md`](../docs/calibration/reference-geometry.md) | Geometry missing from the kinematic model (tilt-axis yaw ≈ 2.1°, rotation-axis offset ≈ 1.3 mm) and the lever-arm sensitivity of kV cross-validation at each imaging position |
| [`../docs/safety.md`](../docs/safety.md) | Hazards, existing protections and their gaps, pre-use checklist |

## Thermal calibration provenance

### What the software does

The terminal converts between the temperature the operator asks for (the pad
*surface*, "outer") and the temperature the heating firmware regulates (the
DS18B20 reading, "inner") with a linear model:

```
T_inner = 1.170 · T_outer − 3.500          (software/surf_terminal/terminal.py:55-56)
```

Setpoints go through `target_to_internal()` before they are sent
(`terminal.py:58-60`, `:596-598`). Readings go through `internal_to_outer()`
before they are displayed and logged (`terminal.py:62-64`, `:566-567`). **The
same constants are applied to both pads**, A and B.

### Where the model comes from

- **Source file.** The comment above the constants reads "Linear regression
  from 'Kalibration HP vorne 19.csv'" (`terminal.py:53`). That file is today's
  [`calibration/heating-pad-calibration.csv`](calibration/heating-pad-calibration.csv),
  renamed during release preparation. Its original path, and that of its
  companion `Kalibration HP vorne 19.01.xlsx`, are in git history under
  `hardware/phantom/` at commit `1d19cc7`.
- **Front pad only.** "HP vorne" means "heating pad, front". Which of the
  firmware's pads A and B is the front pad is not recorded anywhere, so it is
  not known which pad the model was fitted to.
- **A single session**, as far as the record shows: one sheet and one date
  label, "19.01" in the original spreadsheet name (presumably 19 January; year
  and time not recorded).
- **12 points.** Setpoints from 25 to 52 °C. Columns: `Soll` (setpoint),
  `Ist (DS18B20)` (reading of the pad's own sensor), and `Ist (Testo925)`
  (reading of a Testo 925 reference thermometer).
- **Not recorded:**
  - how long each point was allowed to settle;
  - the probe type and where it touched the surface;
  - the ambient temperature;
  - the Testo's calibration status.
- **No other record of the fit.** Neither the spreadsheet nor the plot contains
  the regression. The two constants in `terminal.py` are the only record of it.

### Independent refit

The fit was repeated for this document: ordinary least squares, with DS18B20 as
the dependent variable and Testo 925 as the independent one, all 12 points.

| | Slope `CALIB_M` | Intercept `CALIB_B` (°C) | R² |
|---|---|---|---|
| Shipped (`terminal.py:55-56`) | 1.170 | −3.500 | — |
| Refit | 1.1698 | −3.504 | 0.9929 |

The shipped constants are this regression, rounded. They are not a fit against
the setpoint column, which gives 1.2085 and −4.607.

**Residuals of the shipped constants:**

| Domain | RMS | Max \|residual\| | At surface temperature |
|---|---|---|---|
| Sensor, °C (the domain of the fit) | 0.70 | 1.25 | 46.2 °C |
| Surface, °C (what the terminal displays and logs) | 0.60 | 1.07 | 46.2 °C |

The refitted constants give the same RMS (0.70 °C) and a maximum of 1.24 °C.

**The residuals are structured, not random.** In order of increasing
temperature their signs run − − − − + + + + + − − +, so a straight line is an
approximation. The top of the range is least linear: between setpoints 50 and
52 °C the DS18B20 reading rose by 2.0 °C but the surface by only 0.4 °C.

### How well the working point is covered

The blueprints heat the pads to 32 °C surface, which is 33.94 °C at the sensor.

- **Two** calibration points lie within ±1 °C of 32 °C: surface 31.2 and
  32.6 °C.
- **Three** lie within ±2.5 °C, adding 34.1 °C.
- Their surface-domain residuals are +0.43, −0.31 and −0.86 °C.

The accuracy of the displayed surface temperature at the working point
therefore rests on two or three points, from one session, on one pad.

### Calibrated range

- **Surface (Testo 925):** 24.6-46.6 °C.
- **Sensor (DS18B20):** 25.0-51.3 °C.

The model is supported **only inside that range**. The terminal accepts
surface setpoints of 10-50 °C (`terminal.py:1139`, `:1258`). Anything below
24.6 °C or above 46.6 °C is extrapolation. A 50 °C request maps to 55.0 °C at
the sensor, above every calibration point. Blueprint heat steps are not
range-checked at all ([`../docs/safety.md`](../docs/safety.md) G8). **No claim
about pad surface temperature outside 24.6-46.6 °C is supported by this
data.**

### Two further cautions

- **Control shortfall adds to the model error.** From a 37.5 °C setpoint
  upwards, the DS18B20 settled 0.1-0.7 °C below its setpoint. The regression
  uses the measured DS18B20 value, so it models sensor versus surface. In
  operation, though, the terminal commands a *setpoint*, and any shortfall adds
  to the model error. At the two setpoints that bracket the working point,
  32.5 and 35.0 °C, the sensor matched its setpoint exactly.
- **"STABIL" does not mean the surface is on target.** The status shows
  "STABIL" when the last 120 displayed readings all lie within ±0.2 °C of the
  setpoint (`terminal.py:354-355`, `:576-578`). At the firmware's 1 Hz rate
  (`SURF_nanoHeating_v4.ino:116`) that is 120 s, not the "20 s" the comment at
  `terminal.py:353` claims. The band is tighter than the model's own error
  (surface RMS 0.60 °C), so "STABIL" means the sensor is steady. It does not
  mean the surface is within 0.2 °C of the requested temperature.
