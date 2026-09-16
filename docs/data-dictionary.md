# Data dictionary

This is the schema reference for the measurement data in [`data/`](../data/). It
covers every column of every file family in `data/raw/`, plus the two companion
tables. Every statement was checked against the archived files and against the
code that wrote them:

- the measurement terminal, [`software/surf_terminal/terminal.py`](../software/surf_terminal/terminal.py);
- the controller firmware, [`firmware/axis/SURF_nanoAxis_v5/`](../firmware/axis/SURF_nanoAxis_v5/SURF_nanoAxis_v5.ino)
  and [`firmware/heating/SURF_nanoHeating_v4/`](../firmware/heating/SURF_nanoHeating_v4/SURF_nanoHeating_v4.ino);
- for older formats, the writer versions in git history (commit hashes are given).

Where the archive cannot answer a question, the text says **not determinable
from the archive**.

For an overview of the campaigns, start with [`data/README.md`](../data/README.md).

## Contents

1. [Conventions shared by all files](#1-conventions-shared-by-all-files)
2. [How the files relate](#2-how-the-files-relate)
3. [Family A: raw telemetry CSV](#3-family-a-raw-telemetry-csv)
4. [Family B: `_QA.csv` sphere-detection points](#4-family-b-_qacsv-sphere-detection-points)
5. [Family C: `_log.json` / `_log.txt` measurement protocols](#5-family-c-_logjson--_logtxt-measurement-protocols)
6. [Family D: legacy pilot CSV](#6-family-d-legacy-pilot-csv)
7. [Companion tables](#7-companion-tables)
8. [Format-drift timeline](#8-format-drift-timeline)
9. [Caveats for reuse](#9-caveats-for-reuse)

---

## 1. Conventions shared by all files

| Aspect | Convention |
|---|---|
| Encoding | UTF-8, no byte-order mark. Non-ASCII characters occur only in protocol files (German text, `°`). |
| Line endings | LF in this repository. The terminal writes CRLF (the default of Python's `csv` module); line endings were normalised during release preparation (see `.gitattributes`). Parsers should accept both. |
| Numbers | Decimal point `.`, no thousands separator, no quoting. Floats are written as Python's shortest round-trip representation (`25.0`, `4.951720722951226`), so **the number of digits says nothing about measurement precision**. |
| Missing values | An empty field. There is no `NaN` or `NA` token. |
| Times in file names | Local wall-clock time of the terminal PC (Austria, CET/CEST) when the file was opened, truncated to whole seconds. No file stores a time-zone designator. |
| Folders | `data/raw/<YYYY-MM-DD>/` holds one recording day. `data/raw/<YYYY-MM>-pilot/` collects development data from several days (`2026-02-pilot` spans 2026-02-10 to 2026-02-19). |
| Truncation | There are no footers or end-of-run markers. The last row is the last one written before logging stopped. All 151 measurement CSV files in `data/raw/` have complete rows. |

### File-name grammar

| Pattern | Written when | Family |
|---|---|---|
| `<prefix>_<YYYYMMDD>_<HHMMSS>.csv` | logging starts | A |
| `<prefix>_<YYYYMMDD>_<HHMMSS>_QA.csv` | logging is started by a blueprint (same instant, same stem) | B |
| `<blueprint-stem>_<YYYYMMDD>_<HHMMSS>_log.json` and `.txt` | a blueprint is loaded | C |
| `qa_log_<YYYYMMDD>_<HHMMSS>.csv`, `manual_*.csv` | the retired command-line logger starts | D |

- `<prefix>` is the `prefix` of the blueprint's `logging` step. `messung` is used
  for a manual start (the GUI button or the console command `start measurement`)
  and is also the default when a `logging` step has no `prefix`.
- The `<HHMMSS>` of a raw CSV is the `surf_timestamp` used by the linkage tables.

---

## 2. How the files relate

```
blueprint loaded ──► <blueprint-stem>_<T0>_log.json ─── field csv_file ───┐
                                                                          ▼
                     logging started ──► <prefix>_<T1>.csv   (T1 later than T0)
                                                 │  same stem; join on Time_Sec
                                                 ▼
                                         <prefix>_<T1>_QA.csv

data/etds_qa_2026_config.json   surf_timestamp = HHMMSS of T1
                                etds_timestamp = HHMMSS of the ExacTrac export
data/raw/2026-03-10/runs.csv    csv_file, etd_file
```

| From | To | Key | Remarks |
|---|---|---|---|
| raw CSV | `_QA.csv` | identical stem, then `Time_Sec` | Both use the same `time.perf_counter()` origin. Use a nearest-sample or as-of join, not an exact match. |
| protocol | raw CSV | `csv_file` inside the JSON | The file stems differ (§9.2). |
| config entry | raw CSV | `surf_timestamp` = `HHMMSS` of the raw file name | The key has no date. Resolve it against file names; all 9 values are unique in this archive. |
| config entry | ExacTrac export | `etds_timestamp` = `HHMMSS` in `TrackingResult_<date>_HH-MM-SS.json` | The exports are **not in this repository**. The 20 referenced here are held in the project's separate clinical-QA repository, which is not public yet. |
| `runs.csv` row | raw CSV, ExacTrac export | `csv_file`, `etd_file` | 2026-03-10 only. |

---

## 3. Family A: raw telemetry CSV

- **Files:** 118 files in 10 folders (`2026-02-pilot` to `2026-08-21`), 201,912 rows in total.
- **Writer:** `LoggerThread.run()` in `terminal.py`.
- **Format:** delimiter `;`, one header line, 10 columns.

```
Time_Sec;Pos_H;Pos_V;Pos_R;Temp_A;Temp_B;Set_A;Set_B;Stable_A;Stable_B
43.403;0.0;8.92;0.0;23.076923076923077;23.179487179487182;25.0;25.0;0;0
```
<sub>Row 401 of `2026-03-10/ETD_QA_PoP_SingleCouchOrientation_20260310_160448.csv`: vertical axis in motion, pads unheated.</sub>

**One row** is a snapshot of the terminal's shared state at the moment the logger
thread assembles it. It is *not* a synchronised sample of the controllers. The
axis controller reports its position every 50 ms and the heating controller its
temperatures every 1 s, and each row repeats the most recent values received
(sample-and-hold). At about 9.3 rows per second, at most one row in nine can
carry a new temperature. In the 2026-03-10 files the median run of identical
temperature pairs is 9–19 rows per file.

| Column | Type | Unit | Definition | Sign, range, special values |
|---|---|---|---|---|
| `Time_Sec` | float, ≤ 3 decimals | s | `time.perf_counter()` when the row is assembled, minus the reference taken when logging started, rounded to 1 ms. | **Monotonic elapsed time, not wall-clock time.** Strictly increasing in every file; the first row is at 0.001–0.033 s. The file name gives the start to the second (§9.10). Join key to `_QA.csv`. |
| `Pos_H` | float | mm | Horizontal slide: step counter of the axis controller (`AccelStepper::currentPosition()`) ÷ 800 steps/mm. | Controller-native sign (positive = positive step direction). 0 = working zero set by homing (endstop minus a fixed offset) or by `set h zero`. Multiples of 0.00125 mm. Limits in firmware v5: −45 to +25 mm. Four `2026-02-pilot` files, written under earlier firmware, exceed them (H ±30 mm; `…_170846.csv` up to +40.9 mm). |
| `Pos_V` | float | mm | Vertical slide, defined as `Pos_H`. | 0 = homed zero or `set v zero`. Limits in firmware v5: −35 to +50 mm (`2026-02-pilot/…_170846.csv` reaches +62.5 mm). |
| `Pos_R` | float | ° | Rotation stage: step counter ÷ 16.156 steps/°. | 0 = wherever the stage stood at `h r` or `set r zero`; there is no endstop. Commands are truncated to whole steps, so a commanded ±5° is logged as ±4.951720722951226°, 30° as 29.958°, 90° as 89.998°. Multiples of 1/16.156°. Limits in firmware v5: −30 to +120°. |
| `Temp_A` | float | °C | Pad A surface temperature: DS18B20 reading from the heating controller, converted by the terminal as `(T_sensor + 3.5) / 1.17`. | Updated at 1 Hz, in steps of about 0.05 °C. **`-105.55555555555556` means a sensor read failure** (the sensor library returns −127 °C; see §9.7). The initial value 0.0 before the first packet does not occur in the archive. The three `2026-02-pilot/messung_20260210_*` files hold uncalibrated sensor values. |
| `Temp_B` | float | °C | Pad B, defined as `Temp_A`. | As `Temp_A`. |
| `Set_A` | float | °C | Pad A setpoint as last **sent by the terminal**: GUI "Setzen" button, console `t a <T>`, or a blueprint `heat` step. | **`25.0` is the terminal's start-up default and is never transmitted** (the heating firmware boots with setpoint 0.0 °C, heater off), so on its own it is not a real setpoint. However, clicking "Setzen" with the default fields sends a genuine 25 °C command, and the log looks identical. Any other value proves a command was sent. The value persists across measurements within one terminal session. |
| `Set_B` | float | °C | Pad B, defined as `Set_A`. | As `Set_A`. |
| `Stable_A` | int, 0 or 1 | — | 1 if each of the 120 most recent pad-A temperature samples lies within 0.2 °C of the current `Set_A`; otherwise 0, including while fewer than 120 samples exist. Evaluated whenever a heating packet arrives. | At 1 Hz the window is about **120 s**. It measures deviation from the setpoint, not fluctuation, so unheated pads at room temperature (about 23 °C) against the default 25.0 give 0 throughout. The no-controller fallback forces 1 (§9.6). The window was 20 samples in the 2026-02-10 terminal. |
| `Stable_B` | int, 0 or 1 | — | Pad B, defined as `Stable_A`. | As `Stable_A`. |

The terminal also converts the setpoint to the sensor scale before sending it
(`T_sensor = 1.17·T − 3.5`), so `Set_*` and `Temp_*` are on the same calibrated
scale. The coefficients (`CALIB_M = 1.170`, `CALIB_B = −3.500`) are hard-coded in
`terminal.py`; calibration measurements are in `hardware/calibration/`.

### Sampling rate: measured ≈9.3 Hz, not 10 Hz

The logger does not run on a clock schedule. Each loop iteration assembles a row,
writes and flushes it, and *then* sleeps a fixed `interval = 0.1` s. Every
interval is therefore 0.1 s **plus** the write/flush time and the operating
system's sleep overshoot, and never shorter: the minimum interval is 0.100 s in
every campaign.

Across the 103 files logged at this setting (192,642 intervals):

- median interval 0.107 s (**9.35 Hz**);
- mean interval 0.1079 s (**9.27 Hz**);
- 95 % of intervals in each campaign at most 0.110–0.120 s;
- isolated gaps up to 1.94 s.

Per-campaign values are in §8. Medians are quantised to 1 ms because `Time_Sec`
has three decimals.

**Consequence:** row index × 0.1 s is not a time base. One minute of logging
yields about 556 rows, not 600. Always use `Time_Sec`. The `2026-02-pilot` files
were written with `interval = 0.5` s (median 0.505 s, ≈2.0 Hz).

### What the position columns are, and are not

`Pos_*` is the controller's **commanded step count**, i.e. the steps it issued to
the motor driver. The CL57T drivers are closed-loop against their motor encoders,
so a lost step is corrected or raises a driver alarm; but the alarm state is not
logged (see [KI-05](known-issues.md#ki-05)), and nothing downstream of the motor
shaft (lead screw, coupling, gear lash, linkage geometry) is measured.

- Missed steps, gear backlash and elasticity do not appear in the log.
- Backlash compensation (firmware v5, rotation axis only, 4 steps when switched
  on with `backlash on`) moves the motor and then restores the counter, so it is
  invisible in the log.
- A move the firmware rejects (target outside the limits, or rotation axis not
  yet zeroed) leaves the position unchanged, but the controller still reports the
  command as done and the terminal proceeds.

The log therefore records what the controller executed, not what the blueprint
requested.

### Sign conventions

All position columns are stored in the controller's native sign. Their mapping to
patient or room coordinates (lateral/longitudinal/vertical, pitch/roll/yaw)
depends on the phantom set-up and couch angle. It is defined by the kinematic
model of the analysis pipeline (`kinematics_werror_v2.py` in
[surf-etds-analysis](https://github.com/AG-Kollotzek/surf-etds-analysis)), not by this
dataset. Downstream tools flip signs differently: the MATLAB viewer
`matlab/ETDCombinedJSONCSVViewerApp.m` negates `Pos_H` on load, and the analysis
pipeline's legacy mode negates `Pos_R`. Never infer a room-coordinate sign from
the column alone.

Which physical pad is A and which is B is **not determinable from the archive**.

---

## 4. Family B: `_QA.csv` sphere-detection points

- **Files:** 21 files (`2026-05-12` to `2026-08-21`), 83 data rows in total; 4 files are header-only.
- **Writer:** `MainWindow.handle_blueprint_logging()` writes the header when a blueprint starts logging; `MainWindow.handle_qa_input()` appends one row per accepted `qa_input` dialog.
- **Format:** delimiter `;`, 15 columns.

```
Time_Sec;Point_ID;Mode;H_pos;V_pos;R_pos;Sphere_X;Sphere_Y;Sphere_Z;Surf_X;Surf_Y;Surf_Z;Pitch;Yaw;Roll
238.582;1_endposition_d1;sphere_detection;-10.0;20.0;0.9903441445902452;0.6;-17.2;-0.5;;;;;;
```
<sub>From `2026-08-06/ETsurface_easyQA_20260806_163851_QA.csv`.</sub>

**One row** is one sphere-detection point. The phantom dwells at a position, the
operator runs the ExacTrac sphere detection and types the displayed values into
the terminal's dialog.

The header is written for *every* blueprint-started logging run, whether or not
the blueprint has `qa_input` steps. A header-only file therefore means "no
sphere-detection step". All four header-only files in the archive carry prefixes
of blueprints that have no `qa_input` step.

| Column | Type | Unit | Definition |
|---|---|---|---|
| `Time_Sec` | float, ≤ 3 decimals | s | `time.perf_counter()` when the dialog was accepted, minus the same reference as the raw CSV started together with this file. Join key. In the archive every row lies within 0.09 s of a raw sample. The final point of a run can fall up to one sample interval after the raw file's last row (observed maximum 0.083 s), because logging stops right after the last dialog. |
| `Point_ID` | string | — | `point_id` of the blueprint step, `<n>_<name>[_couch<angle>]`. Names in the archive: `Referenz`/`referenz` and `zeroposition`; `minVerschub` and `MaxVerschub` (up to 2026-07-29); `endposition_d1` and `endposition_d2` (2026-08-06). The suffix `_couch-90` marks points at couch angle −90°. `minVerschub` = `endposition_d1` = deflection 1; `MaxVerschub` = `endposition_d2` = deflection 2. |
| `Mode` | string | — | `mode` of the `qa_input` step: `sphere_detection`, `surface_tracking` or `both`. **All 83 rows are `sphere_detection`.** |
| `H_pos` | float | mm | `Pos_H` at the moment of acceptance: same source and conventions as Family A. It equals the nearest raw sample in all 83 rows. |
| `V_pos` | float | mm | `Pos_V`, as above. |
| `R_pos` | float | ° | `Pos_R`, as above. |
| `Sphere_X` | float or empty | mm | First value typed into the dialog. At `0_Referenz` the blueprint asks for the initial isocentre (Winston-Lutz pointer); at every other point it asks for the shifts reported by sphere detection. Empty if left blank or not a number (1 of 83 rows). |
| `Sphere_Y` | float or empty | mm | Second value (blank in 5 rows). |
| `Sphere_Z` | float or empty | mm | Third value (blank in 6 rows). |
| `Surf_X`, `Surf_Y`, `Surf_Z` | float or empty | mm | Copies of X/Y/Z, written only in mode `surface_tracking`. **Empty in all 83 rows.** |
| `Pitch`, `Yaw`, `Roll` | float or empty | ° | Written in modes `surface_tracking` and `both`. **Empty in all 83 rows.** The `sphere_detection` dialog has no angle fields. |

The six `Surf_*`/angle columns are empty throughout because no row in the archive
was recorded in mode `surface_tracking` or `both`. Among the current blueprints,
`surface_tracking` occurs only in the two drafts
`blueprints/qa/ETsurface_easyQA_draft*.json`.

**Axis order of `Sphere_X/Y/Z`.** The dialog labels the fields only "X", "Y",
"Z", and the terminal records no axis convention. The data are *consistent with*
lateral / longitudinal / vertical: at couch 0° the large shift appears in
`Sphere_Y`, and at couch −90° it moves to `Sphere_X`. For example, in
`2026-07-15/ETsurface_easyQA_wcouch_T32_20260715_165141_QA.csv` point
`1_minVerschub` reads Y = −17.8 and point `6_minVerschub_couch-90` reads
X = −19.2. This is an inference, not a recorded fact.

---

## 5. Family C: `_log.json` / `_log.txt` measurement protocols

- **Files:** 8 JSON/TXT pairs: 7 in `2026-08-06`, 1 in `2026-08-21`.
- **Writer:** class `MeasurementLog` in `terminal.py`.

The protocol is created when a blueprint is loaded (in both modes) and is
rewritten completely after every change. An interrupted session therefore leaves
a valid file that describes the state up to the interruption. `_log.txt` is a
German rendering of the same content for printing; **the JSON is authoritative**.

### Top-level object

All keys are always present, in this order.

| Key | Type | Meaning |
|---|---|---|
| `datum` | string `YYYY-MM-DD` | Local date the blueprint was loaded. |
| `start_messung` | string `HH-MM` | Local time the blueprint was loaded. Note the hyphen. |
| `ende_messung` | string `HH-MM` or null | Time the blueprint finished **or was aborted**; null only if that point was never reached. |
| `modus` | string | `"QA (Config wird beschrieben)"`: a config file was selected and is appended to. `"alter Modus (ohne Config)"`: legacy mode; the config dialog was cancelled, so no session form and no config writes. |
| `config_file` | string or null | Base name of the file selected as config file. The terminal does not validate the choice: in 2026-08-21 a blueprint file (`ETD_QA_BasicPoP.json`) was selected. |
| `blueprint_file` | string | Base name of the loaded blueprint. |
| `blueprint_name` | string or null | The blueprint's free-text `name` field. Not a unique identifier (§9.1). |
| `linac` | string or null | Linac label entered by the operator (QA mode only). Values in the archive: `3`, `4`, `5`, `X`. |
| `personal` | string or null | Operators present, pseudonymised as role codes (`QMP1`, `Student1` to `Student3`). Comma-separated free text with the spacing as typed. |
| `messzweck` | string or null | Purpose, free text (`QA`, `QA 2026`, `QA_2026`, `Test`). |
| `meas_couch_type` | string | `single angle` or `multi angle`. Derived from the blueprint (more than one distinct couch angle among its `qa_input` points gives `multi angle`), overridable by a top-level blueprint field or by the operator. |
| `heatingpads` | string | `OFF` or a temperature such as `32`. Derived from the blueprint: explicit top-level field, else the first `heat` step, else `_T<nn>` in the file name, else `OFF`; editable by the operator in QA mode. **Session metadata, not a measurement** (§9.8). |
| `csv_file` | string or null | File name of the raw CSV started by this blueprint (join key); null if logging never started. |
| `surf_timestamp` | string `HHMMSS` or null | `HHMMSS` of `csv_file`. |
| `bedingungen` | object | Conditions recorded by `log_checkpoint` steps: key → boolean (yes/no dialog) or string (free-text dialog). Keys in the archive: `raumlicht_aus` (room light off, boolean) and `tracking_qualitaet` (tracking quality, string). |
| `config_entries` | array of objects | Entries successfully appended to the config file: the seven fields of §7.1 plus `config_key` (string). |
| `events` | array of objects | Chronological event log, described below. |

### `events[]`: a union discriminated on `type`

Every event has `zeit` (string `HH:MM:SS`, local time) and `type`. The remaining
fields depend on `type`:

| `type` | Written when | Additional fields | In archive |
|---|---|---|---|
| `checkpoint` | The operator answers a `checkpoint` dialog. | `msg`: string, the German prompt. `antwort`: boolean; `false` aborts the blueprint. | 31 |
| `log_checkpoint` | A `log_checkpoint` step records a value. | `key`: string. `wert`: boolean or string. `msg`: string. | 10 |
| `logging` | Blueprint logging starts or stops. | `action`: `start` or `stop`. `datei`: string. On start, the raw CSV file name; on stop, the path of the `_QA.csv` as the terminal wrote it, relative to its working directory (e.g. `data/2026-08-06/…_QA.csv`, or `data\2026-08-06\…_QA.csv` on Windows, stored JSON-escaped as `\\`); empty string if none. | 12 |
| `qa_input` | A sphere-detection dialog closes. | `point_id`: string. `mode`: string. `werte`: an object `{x, y, z}` (plus `pitch`, `yaw`, `roll` in modes `surface_tracking`/`both`) whose values are numbers or `""` for blank fields, **or** the string `"ABGEBROCHEN"` if the dialog was cancelled, which aborts the blueprint. | 25 (none cancelled) |
| `etds_timestamp` | QA mode only, before each end-position point: the operator enters the time of the ExacTrac export. | `point_id`: string. `deflection`: integer, 1 or 2. `couch_angle`: integer, degrees. `etds_timestamp`: string of exactly six digits, `HHMMSS` (§9.3). `config_key`: string, **or null if the append to the config file failed**. | 10 |

The code also stores an event without a type as `type: "event"`; this does not
occur in the archive.

### `_log.txt` labels

| TXT label | JSON source |
|---|---|
| `Datum der Messung` | `datum` |
| `gemessen : LINAC …` | `linac` |
| `Messteam` | `personal` |
| `Messzweck` | `messzweck` |
| `Modus`, `Config-Datei` | `modus`, `config_file` (`- (nicht beschrieben)` if null) |
| `Blueprint`, `Blueprint-Name` | `blueprint_file`, `blueprint_name` |
| `Messart`, `Heatingpads` | `meas_couch_type`, `heatingpads` |
| `Start Messung`, `Ende Messung` | `start_messung`, `ende_messung` (`- (laeuft noch / abgebrochen)` if null) |
| `CSV Datei`, `surf_timestamp` | `csv_file`, `surf_timestamp` |
| `--- BEDINGUNGEN` | `bedingungen` |
| `--- CONFIG-EINTRAEGE` | `config_entries` |
| `--- ABLAUF`: `CHECKPOINT … -> JA/NEIN`, `NOTIZ`, `LOGGING`, `SPHERE DET.`, `ETDS` | events of type `checkpoint`, `log_checkpoint`, `logging`, `qa_input`, `etds_timestamp` |

The TXT prints Python representations of values (`True`, `None`,
`{'x': 0.5, …}`). Parse the JSON, not the TXT.

---

## 6. Family D: legacy pilot CSV

- **Files:** 12. `2025-12-pilot` holds 5 files recorded on 2025-12-04; `2026-01-pilot` holds 7 files recorded on 2026-01-26. 66,638 rows in total.
- **Writer:** the retired command-line logger `control_terminal.py`. It is not in the current tree; see git history, first version `65ed3d4` (2025-12-10) and revision `d7c168f` (2026-01-26).
- **Format:** delimiter `,`, header `PC_Time,Arduino_Time,Pos_H_Steps,Pos_V_Steps,Pos_R_Steps,Status_Bits`. No temperature columns.

```
PC_Time,Arduino_Time,Pos_H_Steps,Pos_V_Steps,Pos_R_Steps,Status_Bits
1764862415.1550012,50,0,0,0,0
```
<sub>First data row of `2025-12-pilot/qa_log_20251204_163333.csv`.</sub>

**One row** is one status packet from the axis controller, written as soon as the
PC receives it. The controller sends a packet every 50 ms, so the rate is about
20 Hz; there is no sleep-based sampling as in Family A.

| Column | Type | Unit | Definition |
|---|---|---|---|
| `PC_Time` | float | s since 1970-01-01T00:00:00Z | `time.time()` on reception: **Unix epoch, wall clock**. In Austrian local time, the first row follows the time in the file name by 2.1–3.0 s (the name is fixed when the script starts). It records reception time, and packets read in bursts can be 1.3 ms apart, so prefer `Arduino_Time` for intervals. |
| `Arduino_Time` | int | ms | Controller `millis()`, i.e. time since the controller started. It is 50 in the first row of all 12 files, consistent with the controller restarting when the logger opened the serial port. |
| `Pos_H_Steps` | int | steps | Raw step counter of the horizontal axis. **mm = steps ÷ 800** (`STEPS_PER_MM`). |
| `Pos_V_Steps` | int | steps | Raw step counter of the vertical axis. **mm = steps ÷ 800**. |
| `Pos_R_Steps` | int | steps | Raw step counter of the rotation axis. **Degrees = steps ÷ 16.156** (`STEPS_PER_DEG`, the calibration introduced on 2025-12-17 in `1f6ab9a`). See the warning below. |
| `Status_Bits` | int | bit field | Status byte from the controller; see below. |

**Rotation constant in the December files.** The 2025-12-04 files were
*commanded* with the earlier constant 16.515 steps/°. Their nominal angles are
therefore steps ÷ 16.515, while steps ÷ 16.156 gives the physical angle under the
later calibration. Example: `manual_rotation_plus10.csv` peaks at 165 steps =
int(10 × 16.515), which is the commanded +10°, but corresponds to 10.21° under
16.156. The same pattern holds for the other December rotation targets (−82
steps = −5°, ±1486 steps = ±90°). The January files use 16.156 (484 steps = 30°,
−727 steps = −45°).

**`Status_Bits` is undocumented, and it is not always 0.**

- Nothing in the data files, and nothing the writer prints, defines this byte.
- Across the 12 files it takes only the values 0 and 1.
- It is 1 in 10 of the 12 files: 8,085 rows in 18 contiguous blocks of 14.4–45.2 s.
- Every block coincides with a homing run. H or V travels far out (up to 86,094
  steps on H and 50,576 on V), or through a long negative search (to −31,103
  steps), and then returns to 0.

This matches bit 0 = "homing in progress" in the axis firmware of that period in
git history (v1.1 and v1.2: bit 0 homing, bit 1 H driver alarm, bit 2 V driver
alarm, bit 3 alarm state). The writer itself treated bits 1–3 as alarms. Bits 1–3
are never set in the archive. Which firmware build actually ran is **not
determinable from the archive**. Because homing resets the step counter,
positions before and after a homing block are not in the same reference frame.

**Timing.** The median `Arduino_Time` increment is 50 ms in every file; the median
`PC_Time` increment is 0.0500–0.0503 s. Gaps of up to 7.7 s occur, and they also
appear in `Arduino_Time`, so they are pauses in the controller's reporting rather
than PC-side losses.

**Renamed files.** During release preparation the three `manual_*.csv` files
were renamed from free-text German names. The content is unchanged, and the
original names are in git history.

| Current name | Original name | Gloss |
|---|---|---|
| `manual_03_sweep_0-20-0.csv` | `3. messung 0-20-0.csv` | "3rd measurement 0-20-0" |
| `manual_final_h_0-10.csv` | `letzte mesung ende h 0-10.csv` | "last measurement, end, h 0-10" |
| `manual_rotation_plus10.csv` | `dreh +10 messung.csv` | "rotation +10 measurement" |

---

## 7. Companion tables

### 7.1 `data/etds_qa_2026_config.json`: run ↔ ExacTrac linkage

A JSON object keyed by the strings `"1"` to `"20"`. Each value has the fields
below, which are also the fields of a protocol's `config_entries[]`.

| Field | Type | Meaning |
|---|---|---|
| `Linac` | string | Linac label as entered (`0`, `1`, `3`, `4`). |
| `deflection` | int | 1 = first end position (`endposition_d1`, formerly `minVerschub`); 2 = second (`endposition_d2`, formerly `MaxVerschub`). |
| `meas_couch_type` | string | `single angle` or `multi angle`. |
| `heatingpads` | string | `OFF` or `32` (session metadata; see §9.8). |
| `etds_timestamp` | string `HHMMSS` | Time in the name of the ExacTrac export `TrackingResult_<date>_HH-MM-SS.json`. The exports are not in this repository; all 20 are in the project's clinical-QA repository (not public yet), under `data/raw/L<linac>/etds_scans/`. |
| `surf_timestamp` | string `HHMMSS` | `HHMMSS` of the raw CSV. |
| `couch_angle` | int | Couch angle in degrees (0 or −90). |

Each entry is one end position, i.e. one ExacTrac export. The 20 entries resolve
to 9 raw CSVs:

| Entries | Linac | Raw CSVs |
|---|---|---|
| 1–8 | 1 | 3 CSVs in `2026-07-15` (`multi angle` entries 5–8 at couch 0° and −90°) |
| 9–12 | 0 | 2 CSVs in `2026-07-29` |
| 13–16 | 3 | 2 CSVs in `2026-08-06` |
| 17–20 | 4 | 2 CSVs in `2026-08-06` |

Entries 13–20 agree with the `etds_timestamp` events of the corresponding
2026-08-06 protocols. In those protocols the automatic append had failed
(`config_key: null`, empty `config_entries`).

### 7.2 `data/raw/2026-03-10/runs.csv`: condition index of the paper campaign

Comma-separated, one header line, one row per raw CSV of the campaign (40 rows,
32 of them used in the analysis), ASCII only. It materialises the dict
`MEASUREMENT_10032026` from `DataConverter.py` in surf-etds-analysis. The dict was
previously the only record of which file belongs to which condition.

| Column | Meaning |
|---|---|
| `run_id` | Key in `MEASUREMENT_10032026`. This is also the run number ("Messung") in the measurement protocol of the campaign: all 32 CSV/ETD number pairs agree with it. The analysis labels runs `meas_<NN>`. Empty for files not in the dict. Numbers 13, 20, 23 and 36 are protocol runs outside the evaluated set. |
| `csv_file` | File name of the raw telemetry CSV in this folder. |
| `etd_file` | ExacTrac tracking export for the run, resolved from the dict's `ETD` code exactly as the pipeline does. The file lives in `paper_data/full_raw/01_json/` of surf-etds-analysis, not here. Empty for unused files. |
| `group` | The dict's `Gruppe`, verbatim, because it is a grouping key in the pipeline. Values: `All axes` (H, then V, then R, sequentially), `Horizontal`, `Vertical`, `Rotation`, `Variable_Geschwindigkeit` (variable rotation speed), `Vertical_Slide` (H motion with V at +50 mm, which tilts the phantom). |
| `roi_area` | The dict's `ROI_Area`, verbatim: `PhantomWithBuffer`, `Fitting`, `OnlyFrontSurface`, `Fiting`. The last is spelled as in the source dict (run 19), and the protocol describes it differently from run 17's `Fitting`. Empty for `Vertical_Slide`, which has no ROI entry in the dict. |
| `heatingpads` | The dict's `Heatingpads`: `OFF` or `32` (°C). Consistent with the telemetry: `OFF` runs have `Set` 25.0 and `Temp` 22.97–23.23 °C; `32` runs have `Set` 32.0 and `Temp` 31.94–32.05 °C. |
| `title` | The dict's `title`, the plot title (`H, V, R`, `H`, `V`, `R`). Empty where the dict has none. |
| `used_in_analysis` | `true` for the 32 dict entries, `false` otherwise. |
| `note` | For unused files, the reason for exclusion **where the repositories establish one**. For run 34, a verified structural caveat. An empty `note` means no reason is recorded; it does not mean the file is valid. |
| `blueprint` | Blueprint file named for the run's series in the protocol, checked against the file's logging prefix and dwell sequence. Empty where the protocol names none or where the check fails (run 23). Five of the six names also exist in `blueprints/pop/` (with a 32 °C `heat` step) as well as in `blueprints/heating-off/`; which copy was loaded is **not determinable from the archive**. The move and delay steps of both copies are identical to the repository state of 2026-03-10. |
| `protocol_remark` | Run-specific remarks from the measurement protocol (German, `Messung_Protokoll_10_03_2026.pdf` in surf-etds-analysis), translated. Text in square brackets marks where the protocol conflicts with the files. |

---

## 8. Format-drift timeline

| Campaign folders | Recorded | Families | Writer, with corroborating commit | Logging cadence | Temperature and stability |
|---|---|---|---|---|---|
| `2025-12-pilot` | 2025-12-04 | D | `control_terminal.py` (`65ed3d4`) | One row per controller packet (50 ms). Median ΔPC_Time 0.0503 s (19.9 Hz). | None. Rotation commanded with 16.515 steps/°. |
| `2026-01-pilot` | 2026-01-26 | D | `control_terminal.py` (`d7c168f`); 16.156 steps/° since `1f6ab9a` (2025-12-17) | As above. Median 0.0500–0.0503 s (20.0 Hz). | None. |
| `2026-02-pilot`, the three `messung_20260210_*` files | 2026-02-10 | A | GUI terminal `SURF_Terminal.py` (first added 2026-01-28; version committed that day, `46073dd`) | `interval = 0.5` s. Median 0.502–0.505 s (≈2.0 Hz). | **Uncalibrated** sensor values (2 decimals). `Stable` window of 20 samples. No no-controller fallback in that code. |
| `2026-02-pilot`, the other 12 files | 2026-02-16 to 02-19 | A | Fallback and 120-sample window (`dee82f5`); calibration (`79f7e33`) | `interval = 0.5` s. Median 0.504–0.505 s (≈2.0 Hz). | Calibrated, `(T + 3.5)/1.17`. |
| `2026-02-24` to `2026-04-08` | | A | `interval = 0.1` s (`e45b574`, 2026-02-24) | Measured values in the table below. | Calibrated. |
| `2026-05-12` to `2026-07-29` | | A + B | `qa_input` and `_QA.csv` (`f798e2f`, 2026-05-12) | As above. | Point IDs `minVerschub`/`MaxVerschub`. |
| `2026-08-06`, `2026-08-21` | | A + B + C | Protocols, config linkage, `log_checkpoint` (`baf97ac`, 2026-08-06) | As above. | Point IDs `endposition_d1`/`_d2`. |

The commit dates are corroborating evidence, not proof of the exact build that
wrote a file. The first files in a new format can predate the commit by minutes
(the 2026-05-12 `_QA.csv` and the first 2026-08-06 protocol both do). The
features listed per row (cadence, temperature encoding, file families) are
verified directly in the data.

**Measured interval between consecutive telemetry rows (Family A)**

| Campaign | Files | Rows | Median Δt | Mean Δt | Rate (from median) | Rate (from mean) |
|---|---:|---:|---:|---:|---:|---:|
| `2026-02-pilot` | 15 | 9,167 | 0.505 s | 0.5067 s | 1.98 Hz | 1.97 Hz |
| `2026-02-24` | 11 | 12,528 | 0.107 s | 0.1076 s | 9.35 Hz | 9.29 Hz |
| `2026-03-10` | 40 | 50,424 | 0.107 s | 0.1079 s | 9.35 Hz | 9.26 Hz |
| `2026-03-25` | 10 | 27,173 | 0.107 s | 0.1080 s | 9.35 Hz | 9.26 Hz |
| `2026-04-08` | 22 | 6,665 | 0.108 s | 0.1085 s | 9.26 Hz | 9.22 Hz |
| `2026-05-13` | 4 | 12,363 | 0.107 s | 0.1081 s | 9.35 Hz | 9.25 Hz |
| `2026-07-15` | 8 | 57,275 | 0.108 s | 0.1076 s | 9.26 Hz | 9.29 Hz |
| `2026-07-29` | 2 | 8,549 | 0.108 s | 0.1083 s | 9.26 Hz | 9.24 Hz |
| `2026-08-06` | 5 | 17,260 | 0.108 s | 0.1083 s | 9.26 Hz | 9.24 Hz |
| `2026-08-21` | 1 | 508 | 0.103 s | 0.1045 s | 9.71 Hz | 9.57 Hz |
| **All 0.1 s campaigns** | **103** | **192,745** | **0.107 s** | **0.1079 s** | **9.35 Hz** | **9.27 Hz** |

The nominal rate is 10 Hz; the reason for the shortfall is explained in §3. The
single 53 s file of `2026-08-21` is the fastest; it is one of the runs with the
no-controller signature (§9.6).

---

## 9. Caveats for reuse

### 9.1 The file name does not identify the motion profile

Sixteen blueprint files in `blueprints/` all write the logging prefix
`ETD_QA_PoP_SingleCouchOrientation`. Between them they have 10 distinct file
names and 9 distinct move sequences. Note that the prefix says *Orientation*,
while the blueprints are named `…SingleCouchRotation…`. 62 raw CSVs carry this
prefix: 10 in `2026-02-24`, 39 in `2026-03-10`, 10 in `2026-03-25`, 2 in
`2026-07-15` and 1 in `2026-08-21`.

The blueprint's `name` field does not help either: `…_OnlyR.json`, for example,
is named "…Statistics for one Movement V".

- For **2026-03-10**, use [`runs.csv`](../data/raw/2026-03-10/runs.csv).
- For `2026-08-21`, the protocol's `blueprint_file` identifies the blueprint.
- For the other campaigns, the motion profile can only be recovered from the
  telemetry itself (the sequence of dwell positions); there is no record of which
  blueprint was loaded.

### 9.2 Protocol stem ≠ CSV stem

A protocol is named after the blueprint *file* and the time the blueprint was
*loaded*. The raw CSV is named after the `logging` *prefix* and the time logging
*started*, seconds to minutes later. For example,
`2026-08-21/ETD_QA_PoP_SingleCouchRotation_20260821_093044_log.json` belongs to
`ETD_QA_PoP_SingleCouchOrientation_20260821_093058.csv`. Always join through the
`csv_file` field inside the JSON.

### 9.3 `999999` means "not yet known", not a time

The ExacTrac timestamp dialog accepts only exactly six digits, so `999999` was
typed where no export time was available. It occurs for both end positions of
protocol `2026-08-06/ETsurface_easyQA_new_20260806_151955_log.json` (linac label
`5`, CSV `…_152005.csv`). Those two entries are not part of
`etds_qa_2026_config.json`. Treat any `999999` as missing.

### 9.4 A protocol's `config_key` does not index the published table

`config_key` is the key the terminal assigned in whichever config file was
selected at the time. The only successful appends in the archive (keys `9` and
`10`, the `999999` entries above) are not in `data/etds_qa_2026_config.json`,
whose keys `9` and `10` are Linac 0 entries. The four Linac 3/4 protocols of
2026-08-06 wrote to `etds_qa_2026_config_copy.json`, and every append failed
there (`config_key: null`). Link through `surf_timestamp` and `etds_timestamp`,
never through key numbers.

### 9.5 Orphans, aborted runs and header-only files

- **`2026-05-12`** holds a single `_QA.csv`
  (`ETsurface_easyQA_20260512_161137_QA.csv`, one `0_Referenz` row) and no raw
  CSV. Why the raw file is missing is not determinable from the archive.
- **`2026-08-06`** holds two protocols with `csv_file: null`:
  `ETsurface_easyQA_new_20260806_162753_log.*` and `…_172422_log.*`. In both
  the config dialog was cancelled (legacy mode, so no linac or operators were
  recorded) and the first checkpoint was answered No, which aborts the blueprint
  before logging starts.
- **Four `_QA.csv` files are header-only:**
  `2026-08-21/ETD_QA_PoP_SingleCouchOrientation_20260821_093058_QA.csv` and,
  in `2026-07-15`, `ETD_QA_BasicPoP_20260715_141909_QA.csv`,
  `ETD_QA_PoP_SingleCouchOrientation_20260715_142333_QA.csv` and
  `…_142924_QA.csv`. All four come from blueprint families without
  sphere-detection steps (§4).

### 9.6 Runs in which the axes never moved, and the silent no-controller fallback

If the terminal cannot open a controller's serial port, it silently falls back
to simulation. The only notice is a line in the GUI console; nothing is written
to any data file.

- **Axis controller absent:** `Pos_H`, `Pos_V` and `Pos_R` stay at 0.0 for the
  whole session, and every move "completes" after 0.5 s.
- **Heating controller absent:** every cycle sets `Temp_A = Set_A`,
  `Temp_B = Set_B` and `Stable_A = Stable_B = 1`.

A run recorded without hardware therefore looks like a valid run with a
perfectly still phantom at exactly its setpoint.

In **11 raw CSVs all three axes are constant for the whole run**, at 0 in every
case. Five of them also have constant temperatures (marked **bold**), and three
show the exact fallback signature: positions 0, `Temp` = `Set` = 25.0, `Stable`
= 1 throughout.

| File | Rows | Duration | Temperature constant | Exact fallback signature |
|---|---:|---:|---|---|
| `2026-02-pilot/ETD_QA_BasicPoP_20260217_172515.csv` | 190 | 95.5 s | no | no |
| `2026-02-pilot/ETD_QA_BasicPoP_20260217_173052.csv` | 33 | 16.2 s | no | no |
| `2026-02-pilot/ETD_QA_BasicPoP_20260219_172643.csv` | 522 | 263.7 s | no | no |
| **`2026-02-pilot/messung_20260210_174807.csv`** | 6 | 2.5 s | **yes** | no: `Temp` ≠ `Set`; this terminal version had no fallback |
| **`2026-02-pilot/messung_20260210_184114.csv`** | 12 | 5.6 s | **yes** | no: pad A 38.62 °C vs `Set_A` 40; pad B equals its `Set_B` 25.0 with `Stable_B` = 1 |
| `2026-02-pilot/messung_20260216_175530.csv` | 32 | 15.7 s | no | no |
| `2026-02-pilot/messung_20260217_162406.csv` | 1,456 | 737.4 s | no | no |
| **`2026-03-10/ETD_QA_PoP_SingleCouchOrientation_20260310_152831.csv`** | 169 | 17.4 s | **yes** | **yes** |
| `2026-05-13/ETsurface_easyQA_20260513_144731.csv` | 456 | 47.8 s | no | no |
| **`2026-08-06/ETsurface_easyQA_20260806_152005.csv`** | 1,072 | 113.1 s | **yes** | **yes** |
| **`2026-08-21/ETD_QA_PoP_SingleCouchOrientation_20260821_093058.csv`** | 508 | 53.0 s | **yes** | **yes** |

The three signature runs **cannot be distinguished from a run with disconnected
controllers**. Treat them as non-measurements. There is one circumstantial hint,
which is not proof. The protocols of the two 2026-08 signature runs record the
`_QA.csv` path with `/` separators, i.e. a POSIX host. The other four 2026-08-06
protocols use `\`, i.e. Windows, and `terminal.py` configures its Windows serial
ports as those of the measurement laptop.

The two 2026-02-10 files are too short to judge. In the remaining six files the
temperatures vary, so the heating controller was connected; whether the axis
controller was absent or simply not commanded is **not determinable from the
archive**.

### 9.7 Temperature sentinel

`-105.55555555555556` is the calibration applied to the sensor library's error
value of −127 °C: (−127 + 3.5)/1.17. It appears in 48 rows of 5 files:
`2026-02-pilot/ETD_QA_BasicPoP_20260217_170846.csv` and all four raw CSVs of
`2026-05-13`. It also forces `Stable` to 0 for the following 120 samples. Mask it
before computing any temperature statistic.

### 9.8 `heatingpads: OFF` does not mean room temperature

`heatingpads` is session metadata typed or derived at the start. Use
`Temp_A/B` (and `Set_A/B`) for the actual thermal state:

- A pad can still be warm from earlier heating.
  `2026-07-15/ETsurface_easyQA_wcouch_20260715_153326.csv` was recorded with
  the unheated blueprint variant (prefix without `_T32`), after heated runs
  earlier that day. It logs `Set` 25.0, yet `Temp` reads 27.2–27.6 °C.
- An "off" run can carry a real setpoint.
  `2026-08-06/ETsurface_easyQA_20260806_180321.csv` is `OFF` in its protocol
  and in config entries 19–20, yet logs `Set_A = Set_B = 24.0` with `Temp`
  23.6–24.0 °C.

### 9.9 Sphere values are operator-typed

`Sphere_X/Y/Z` are whatever was typed into the dialog. Several files contain
entries that are not plausible readouts:

- all-zero or blank values at deflected points (`2026-07-15/…_134010_QA.csv`
  and `…wcouch_20260715_153326_QA.csv`);
- patterned values such as `1.0;1.0;1.0`, `1.0;2.0;3.0`, `2.0;2.0;2.0` or
  `0.0;10.0;-10.0` (`2026-05-13/…_145147_QA.csv`, `…_150617_QA.csv`,
  `…_151302_QA.csv`);
- `1.0;1.0;1.0` in `2026-08-06/…_152005_QA.csv`, whose raw CSV has the
  no-controller signature (§9.6).

Check every point for plausibility against its `H_pos/V_pos/R_pos` before use.

### 9.10 Absolute time and synchronisation

Family A stores only elapsed time; the start is known to the second from the
file name, in PC local time. The PC clock is not synchronised with the ExacTrac
clock. Fifteen of the 16 blueprints that write the `SingleCouchOrientation`
prefix bracket their sequence with a 5 mm H excursion (0 → 5 → 0 mm);
`…_OnlyH_Clin.json` uses 3 mm. The analysis pipeline uses these excursions as
sync pulses to align the two logs.

The terminal log of 2026-03-10 run 34 contains three such pulses; see the `note`
column of `runs.csv`.

### 9.11 Pilot data need their own conversions

Family D stores raw steps and wall-clock epoch time, and has no temperatures.
The December 2025 files were commanded with 16.515 steps/° (§6), and
`Status_Bits` = 1 marks homing, not an error. Family A files in `2026-02-pilot`
are logged at about 2 Hz, and the 2026-02-10 files hold uncalibrated
temperatures. Several `2026-02-pilot` files were renamed during release
preparation: free-text prefixes became the suffixes `_firsttry`, `_pop1`,
`_pop1_first_half` and `_pop3_repeat`. The original names are in git history.
