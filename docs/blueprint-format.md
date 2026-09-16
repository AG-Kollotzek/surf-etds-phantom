# Blueprint format: the measurement-sequence DSL

A *blueprint* is a JSON file that scripts one measurement: axis moves, pauses,
heating-pad setpoints, operator prompts, telemetry logging and the manual entry
of tracking-system readings. The measurement terminal executes it step by step.
This document specifies the format and what the terminal actually does with
each construct, including behaviour that is surprising or defective.

The normative reference is the interpreter in `terminal.py`, not the schema.
[`blueprints/schema/blueprint.schema.json`](../blueprints/schema/blueprint.schema.json)
(JSON Schema draft 2020-12) encodes the rules below and is deliberately stricter
in places; the differences are listed in [§6](#6-schema-strictness). All 29
committed blueprints validate against it, and CI checks this on every push
(`.github/workflows/validate.yml`). **The terminal itself does not validate a
blueprint before running it.**

| Short name used below | File |
|---|---|
| `terminal.py` | `software/surf_terminal/terminal.py` |
| `SURF_nanoAxis_v5.ino` | `firmware/axis/SURF_nanoAxis_v5/SURF_nanoAxis_v5.ino` |

`file:line` references point into these files. A bare `:NNN` refers to the file
cited most recently before it.

Operator prompts in blueprints are in German on purpose, because clinical staff
read them at the console ([`CONTRIBUTING.md`](../CONTRIBUTING.md)). Related
documents: [`serial-protocol.md`](serial-protocol.md) covers what the steps put
on the wire, [`data-dictionary.md`](data-dictionary.md) the output files, and
[`known-issues.md`](known-issues.md) the defects.

## Contents

1. [Execution model](#1-execution-model)
2. [Top-level object](#2-top-level-object)
3. [Step reference](#3-step-reference)
4. [Metadata carried in `point_id`](#4-metadata-carried-in-point_id)
5. [Worked example](#5-worked-example)
6. [Schema strictness](#6-schema-strictness)
7. [Known pitfalls](#7-known-pitfalls)

---

## 1. Execution model

### 1.1 Loading and mode selection

1. **BLUEPRINT LADEN (JSON)** opens a file dialog and parses the chosen file with
   `json.load` (`terminal.py:1303-1312`). A parse error is reported on the
   console and nothing runs. No schema validation takes place.
2. The terminal derives the run-wide annotations `heatingpads` and
   `meas_couch_type` (`scan_blueprint_meta`, `terminal.py:1322`; see
   [§2.2](#22-derivation-of-heatingpads) and
   [§2.3](#23-derivation-of-meas_couch_type)).
3. A second file dialog asks for the evaluation config file
   (`terminal.py:1323-1327`). The operator's choice selects the mode:

   | | QA mode | Legacy mode ("alter Modus") |
   |---|---|---|
   | Selected by | choosing a JSON file | cancelling the dialog |
   | Session dialog | shown. Linac and Personal are mandatory; Messzweck defaults to "QA"; Heatingpads and Messart are pre-filled from step 2 and editable. Cancel aborts the start (`terminal.py:1329-1338`, `:895-942`) | not shown; the step-2 values are used unchanged (`terminal.py:1339-1341`) |
   | ExacTrac timestamp prompt at deflection points | yes ([§4.2](#42-when-an-exactrac-timestamp-is-requested)) | no (`terminal.py:665`) |
   | Entries appended to the config file | yes ([§4.3](#43-config-entry)) | no |
   | Measurement log (`_log.json`, `_log.txt`) | yes | yes; `linac`, `personal` and `messzweck` are `null` |

   The config dialog accepts **any** JSON file; nothing checks that it is an
   evaluation config. On 2026-08-21 a file named `ETD_QA_BasicPoP.json`, which is
   the name of a blueprint, was selected as config file
   (`data/raw/2026-08-21/ETD_QA_PoP_SingleCouchRotation_20260821_093044_log.json`,
   field `config_file`). That run had no deflection points, so nothing was
   written. Had it had any, and had the file been the blueprint, the entries
   would have been appended to the blueprint file.
4. The measurement log is created (`terminal.py:1344-1362`) and the interpreter
   thread starts (`terminal.py:1365-1379`).

### 1.2 Step dispatch

`InterpreterThread.run` (`terminal.py:646-833`) iterates over `sequence` once,
in array order, in a single worker thread. Each step runs to completion before
the next begins. At no time are two steps, or two axes, active together.

- Before each step the thread checks the `running` flag and stops if it has
  been cleared (`:651-652`).
- The step's `type` selects the handler (`:654`): `qa_input` in an `if` block
  (`:657-699`), the other six types in an `if`/`elif` chain (`:702-830`) that
  has no `else`. **A step whose `type` is unknown or missing is skipped
  silently**, without a console message or a log entry.
- Handlers read only the keys they know, using `dict.get` with defaults.
  **Unknown keys are ignored**, so a misspelt key silently falls back to its
  default: `"Speed"` leaves the speed at 20.0, and a lowercase `"h"` produces no
  motion at all.
- A missing `sequence` runs nothing (`:650`). A missing `name` is shown on the
  console as "Unbekannte Messreihe" (`:647`).

### 1.3 Aborting and errors

A run ends early on any of these events:

| Trigger | Source |
|---|---|
| **No** at a `checkpoint` | `terminal.py:714-717` |
| **Cancel** in the ExacTrac timestamp dialog or the value dialog of a `qa_input` | `:679-682`, `:694-697` |
| **No** at a `log_checkpoint` with `abort_on_no: true` (mode `yesno`) | `:827-830`, `:1419-1420` |
| **No** at the temperature-timeout prompt of a `heat` step | `:782-785` |
| Console command `exit bp` | `:1281-1287` |

An abort only ends the step loop (`:832-833`). Nothing is undone or stopped:

- An axis command that has already been sent is completed by the controller.
  `exit bp` merely stops the interpreter from waiting for it (`:731-747`).
- Telemetry logging, if it was started, **keeps running**. There is no implicit
  `logging stop`.
- The heating pads keep their setpoints.

`run()` has no exception handling. A value that a handler cannot convert raises
inside the thread and ends it at that step, bypassing the end-of-run path at
`:832-833`; again nothing is cleaned up. Examples are `"H": "ten"`, or
`"speed": "20"`, which fails at `int(speed * factor)`. Numeric strings are
accepted wherever the handler calls `float()`: axis targets, `time`, `a` and
`b`.

### 1.4 Output artefacts

All paths are relative to the terminal's working directory.

| Artefact | Path | Written | Mode |
|---|---|---|---|
| Measurement log | `data/<YYYY-MM-DD>/<blueprint file stem>_<YYYYmmdd_HHMMSS>_log.json` and `…_log.txt` | created at load, rewritten on every event (`terminal.py:1344-1362`, `:262-270`) | both |
| Telemetry CSV | `data/<YYYY-MM-DD>/<prefix>_<YYYYmmdd_HHMMSS>.csv` | from `logging` start to stop (`:1482-1511`, `:393-431`) | both |
| QA CSV | `data/<YYYY-MM-DD>/<prefix>_<YYYYmmdd_HHMMSS>_QA.csv` | header at `logging` start (`:1492-1502`); one row per accepted `qa_input` (`:1538-1555`) | both |
| Temperature plot | `data/plot_<YYYYmmdd_HHMMSS>.png` (not in the date folder) | at `logging` stop (`:1179-1187`) | both |
| Config entries | the file chosen at load | one per `qa_input` at a deflection point (`:1431-1470`) | QA mode only |

---

## 2. Top-level object

### 2.1 Keys

| Key | Type | Interpreter | Schema | Effect |
|---|---|---|---|---|
| `name` | string | optional | required, non-empty | Console banner (`terminal.py:647-648`), session dialog (`:1330`), `blueprint_name` in the measurement log (`:1352`). Not used in any file name. |
| `sequence` | array of step objects | optional; default `[]` | required, ≥ 1 step | The steps ([§3](#3-step-reference)). |
| `heatingpads` | string | optional; derived if absent ([§2.2](#22-derivation-of-heatingpads)) | `"OFF"` or a number written as a string | **Annotation only.** Pre-fills the session dialog; written to the measurement log and to every config entry. It does **not** set any temperature. |
| `meas_couch_type` | string | optional; derived if absent ([§2.3](#23-derivation-of-meas_couch_type)) | `"single angle"` or `"multi angle"` | **Annotation only**, same data path as `heatingpads`. It does not move anything. |

Blueprints have no version, author or description field, and the schema forbids
further top-level keys.

### 2.2 Derivation of `heatingpads`

`scan_blueprint_meta` (`terminal.py:121-153`) applies the first matching rule:

| # | Condition | Result | Source |
|---|---|---|---|
| 1 | top-level key `heatingpads` present | `str(value)` | `:150-151` |
| 2 | the blueprint contains a `heat` step | from the **first** `heat` step: its `a` value, or `b` if it has no `a`; formatted `f"{v:g}"` if > 0, otherwise `"OFF"` | `:138-141` |
| 3 | the blueprint's file name matches `_T(\d+)` (case-insensitive) | the digits, e.g. `ETsurface_easyQA_T32.json` → `"32"` | `:100`, `:142-145` |
| 4 | none of the above | `"OFF"` | `:137` |

- Rule 2 pre-empts rule 3. A blueprint that contains any `heat` step never looks
  at its file name, even when that step's value is 0.
- Only the first `heat` step counts. A later setpoint change is not reflected.
- Rule 3 describes the file name, not the blueprint's behaviour.
  `qa/ETsurface_easyQA_T32.json` has no `heat` step at all; it relies on the
  operator having set 32 °C by hand, which its second checkpoint asks about.
- In QA mode the operator can overwrite the result in the session dialog
  (`:914`, `:940`). The edited value is what goes into the config file.

### 2.3 Derivation of `meas_couch_type`

| # | Condition | Result | Source |
|---|---|---|---|
| 1 | top-level key `meas_couch_type` present | `str(value)` | `:148-149` |
| 2 | otherwise | one couch angle per `qa_input` step (explicit `couch_angle`, else parsed from `point_id`, else 0); more than one distinct angle gives `"multi angle"`, otherwise `"single angle"` | `:130-135` |

- Every `qa_input` step contributes, including reference and zero-position
  points without a deflection. A point without a couch suffix contributes 0.
- A blueprint without `qa_input` steps is always `"single angle"`, even when
  its checkpoints tell the operator to rotate the couch. Example:
  `pop/ETD_QA_BasicPoP.json` asks "Couch auf 90° rotieren …".
- The operator can edit the value in the session dialog in QA mode (`:915`,
  `:941`).

### 2.4 Values for the committed blueprints

These values were obtained by running `scan_blueprint_meta`, extracted from
`terminal.py`, over the files:

| Blueprint | Explicit keys | `heatingpads` | `meas_couch_type` | Decided by |
|---|---|---|---|---|
| `heating-off/*` (11 files) | — | `OFF` | `single angle` | rule 4; no `qa_input` |
| `pop/ETD_QA_BasicPoP.json` | — | `36` | `single angle` | first `heat` step |
| `pop/ETD_QA_PoP_SingleCouchRotation*.json` (6 files) | — | `32` | `single angle` | first `heat` step |
| `pop/test_reihe.json` | — | `35` | `single angle` | first `heat` step (`a` only) |
| `qa/ETsurface_easyQA.json`, `qa/ETsurface_easyQA_draft.json` | — | `OFF` | `single angle` | rule 4; all points at couch 0 |
| `qa/ETsurface_easyQA_T32.json` | — | `32` | `single angle` | file name `_T32` (no `heat` step) |
| `qa/ETsurface_easyQA_wcouch.json` | — | `OFF` | `multi angle` | rule 4; angles {0, −90} |
| `qa/ETsurface_easyQA_wcouch_T32.json` | — | `32` | `multi angle` | first `heat` step; angles {0, −90} |
| `qa/*_new.json` (5 files) | both | as declared | as declared | explicit keys, identical to what derivation would give |

---

## 3. Step reference

Every step is a JSON object with a `type` string. Overview:

| `type` | Blocks until | Operator interaction | Can abort the run | Controller traffic |
|---|---|---|---|---|
| `move` | every listed axis is acknowledged | none | no | one `MOVE_AXIS` per listed axis |
| `delay` | the time has elapsed | none | no | none |
| `heat` | returns at once; with `wait_steady`, until stable or 120 s | Yes/No prompt on timeout | **No** at the timeout prompt | `SET_A` and/or `SET_B` |
| `checkpoint` | the operator answers | Yes/No dialog | **No** | none |
| `log_checkpoint` | the operator answers | Yes/No or text dialog | only with `abort_on_no` | none |
| `logging` | fixed 0.5 s | none (after `stop`, an information box that the run does not wait for) | no | none |
| `qa_input` | the operator accepts the dialog(s) | ExacTrac timestamp dialog (QA mode, deflection points), then value dialog | **Cancel** | none |

`exit bp` ends any step the next time that step checks the `running` flag
([§1.3](#13-aborting-and-errors)).

### 3.1 `move`

```json
{ "type": "move", "H": -10.0, "V": 20.0, "speed": 20.0 }
```

| Field | Type | Unit | Default | Meaning |
|---|---|---|---|---|
| `H` | number | mm | absent: axis not moved | absolute target of the horizontal slide |
| `V` | number | mm | absent: axis not moved | absolute target of the vertical slide |
| `R` | number | degrees | absent: axis not moved | absolute target of the rotation stage |
| `speed` | number | mm/s for H and V, °/s for R | `20.0` | maximum speed; one value for every axis in the step |

Runtime semantics (`terminal.py:722-747`):

1. **Fixed axis order, strictly sequential.** The handler loops over
   `['H', 'V', 'R']` (`:724`). It handles each axis present in the step to
   completion before the next: wait until the axis link is free, enqueue, wait
   for pickup, wait for `COMMAND_DONE` (`:730-747`). JSON key order is
   irrelevant: `{"R": 1, "H": -10}` moves H first, then R. **A multi-axis step
   is never a simultaneous or interpolated motion.** It is shorthand for
   consecutive single-axis steps with no pause in between.
2. **Absolute targets**, relative to the axis zero set by homing or
   `set <axis> zero`. Not increments.
3. **Truncation to whole steps.** Target and speed are sent as
   `int(value × scale)` with 800 steps/mm and 16.156 steps/° (`:739`, `:68-69`).
   `int()` truncates toward zero. For H and V this is invisible: one step is
   1.25 µm, and every linear target in the committed blueprints is an exact
   multiple. For R one step is 0.0619°, and the error approaches a full step:

   | Commanded R | Steps sent | Position reached and logged |
   |---|---|---|
   | 1° | 16 | 0.9903° |
   | 5° | 80 | 4.9517° |
   | 6° | 96 | 5.9421° |
   | 12° | 193 | 11.9460° |
   | 30° | 484 | 29.9579° |
   | 90° | 1454 | 89.9975° |
   | 95° | 1534 | 94.9492° |

   Truncation always reduces the magnitude, so a symmetric ±5° oscillation is
   executed as ±4.9517°. The archived telemetry shows exactly these values,
   e.g. `Pos_R` = ±4.952, 84.984 and 94.949 in `data/raw/2026-02-24/`. R speeds
   are truncated the same way: 0.5 °/s becomes 8 steps/s = 0.4952 °/s, and
   5 °/s becomes 4.9517 °/s.
4. **No limit check on the PC.** Blueprint targets reach the controller
   unchecked; only the console `m` command checks `LIMITS` (`:1216-1219`). The
   firmware rejects targets outside H −45…+25 mm, V −35…+50 mm and
   R −30…+120°, and **acknowledges a rejected move exactly like an executed
   one** (`SURF_nanoAxis_v5.ino:143-156`, `:377`). The interpreter proceeds and
   nothing is logged. It never compares the reported position with the target,
   so the only evidence is a position that did not change in the telemetry CSV.
5. **R must be zeroed first.** Until `h r`, `h all` or `set r zero` has been
   issued since the controller was last powered or reset
   (`SURF_nanoAxis_v5.ino:99`, `:152`, `:392-396`, `:420-423`), **every R move
   is silently skipped** and acknowledged as done. No step type can zero R. The
   first checkpoint of the committed blueprints ("Sind alle Achsen gehomed …")
   is the only safeguard. The archive contains a run that matches this pattern:
   `data/raw/2026-02-24/ETD_QA_PoP_SingleCouchOrientation_20260224_164807.csv`
   has ±10 mm excursions on H and V but `Pos_R` = 0 throughout. The runs
   directly before and after it with the same prefix (`…_162704`, `…_170818`)
   reach ±4.952°.
6. **Speed is an upper bound, and in practice H/V do not exceed about 5 mm/s.** The
   firmware clamps to 50 mm/s (H, V) and 90 °/s (R) and accelerates at a fixed
   80 mm/s² or 40 °/s² (`SURF_nanoAxis_v5.ino:42-43`, `:86-87`). In practice,
   step generation on the Nano tops out at about 4 000 steps/s, consistent with
   the limit AccelStepper documents for 16 MHz boards
   ([serial protocol §4.3](serial-protocol.md#move_axis-1-10-bytes)). At
   800 steps/mm that is about 5 mm/s. The table gives the median cruise speed,
   taken over the central half of every monotonic move segment in the archived
   telemetry (`data/raw/`):

   | Axis, move length | Segments | Median cruise speed |
   |---|---|---|
   | H, 5 mm | 403 | 5.03 mm/s |
   | H, 10 mm | 331 | 5.09 mm/s |
   | H, 20 mm | 107 | 5.09 mm/s |
   | V, 10 mm | 98 | 5.15 mm/s |
   | V, 20 mm | 74 | 5.14 mm/s |

   The PoP profiles command their `H: 5.0` moves at 50 mm/s and their other
   linear moves at 20 mm/s, yet both run at the same speed. In
   `data/raw/2026-03-10/ETD_QA_PoP_SingleCouchOrientation_20260310_182011.csv`
   the 0 → 5 mm moves take about 1.2 s and the 10 → −10 mm moves about 4.2 s.
   R speeds are at most 1 454 steps/s and are realised as commanded, apart from
   truncation.
7. **Waiting and the watchdog.** The step ends when the interpreter sees the
   axis link free again (polled every 50 ms, `:746-747`). That is at least one
   telemetry frame after the controller has finished
   ([serial protocol §6.2](serial-protocol.md#62-read-gating-and-the-delayed-command_done)).
   If one axis move takes longer than 60 s, the PC watchdog releases the
   interpreter early, and every later acknowledgement is credited to the wrong
   command
   ([serial protocol §4.6](serial-protocol.md#46-commandacknowledge-handshake)).
   An example is R from +30° to −30° at 1 °/s: 968 steps at 16 steps/s, i.e.
   60.5 s. The longest single move in the committed blueprints takes about 20 s
   (R ±5° at 0.5 °/s).
8. **Hidden R backlash state.** Whether R backlash compensation is active
   depends on the console command `backlash on|off` issued since the
   controller's last reset (default off). A blueprint cannot set it, and no
   output file records it (`SURF_nanoAxis_v5.ino:45`, `terminal.py:1290-1295`).
9. **Shared link, no emergency stop.** Console commands typed during a run use
   the same queue and ready flag, and the interpreter cannot tell whose
   acknowledgement it received. Neither `exit bp` nor the STOP ALL button
   interrupts a move in progress
   ([serial protocol §4.3](serial-protocol.md#stop_all-3-1-byte)).

### 3.2 `delay`

```json
{ "type": "delay", "time": 2.0 }
```

| Field | Type | Unit | Default | Meaning |
|---|---|---|---|---|
| `time` | number | s | `2.0` | pause duration |

Runtime semantics (`terminal.py:793-801`):

- The handler sleeps in 0.1 s slices and adds 0.1 to a float counter after each
  slice until the counter reaches `time`. It checks `running` after every
  slice, so `exit bp` ends the pause within 0.1 s.
- The number of slices is `time` rounded up to a multiple of 0.1 s, plus one
  wherever floating-point accumulation falls short. `time: 1.0` runs **11** slices
  (1.1 s), because ten additions of 0.1 give 0.9999999999999999. `2.0` and
  `4.0` run 20 and 40 slices, `10.0` runs 101, and `0` does not sleep at all.
  Each `time.sleep(0.1)` may also overrun, so the realised pause is at least the
  slice total.
- The pause starts when the previous step has ended. After a `move` that means
  after the acknowledgement has been processed, not when the axis physically
  stopped.

### 3.3 `heat`

```json
{ "type": "heat", "a": 32.0, "b": 32.0, "wait_steady": true }
```

| Field | Type | Unit | Default | Meaning |
|---|---|---|---|---|
| `a` | number | °C, pad **surface** temperature | absent: pad A unchanged | setpoint of pad A |
| `b` | number | °C, pad surface temperature | absent: pad B unchanged | setpoint of pad B |
| `wait_steady` | boolean | — | `false` | wait for the named pads to become stable |

Runtime semantics (`terminal.py:750-790`):

1. **Setpoints.** Each given value is queued for the heater thread (`:751-754`),
   converted to the pad-internal sensor temperature and sent without any
   acknowledgement
   ([serial protocol §5.2](serial-protocol.md#52-set_a--set_b-1--2-5-bytes)).
   The PC applies **no range check** to blueprint steps; the GUI and the
   console accept only 10–50 °C (`:1139`, `:1258`). The firmware clamps the
   internal setpoint to 0–65 °C, so a value of 0 in effect switches a pad off.
2. **Without `wait_steady`**, the step returns immediately.
3. **With `wait_steady`**, the handler checks once per second, for up to 120
   checks, whether every pad named in the step is flagged stable (`:756-770`).
   A pad is flagged stable when its last 120 telemetry samples all lie within
   ±0.2 °C of its current setpoint. At about 1 Hz that is about 120 s
   ([serial protocol §5.3](serial-protocol.md#53-log_data-heater-10-13-bytes)).
   This has three consequences:
   - **A real temperature change cannot complete inside the window.** Stability
     needs about 120 s of in-band samples, which is the entire 120 s window. The
     step therefore times out unless the pads had already been within ±0.2 °C
     of the new setpoint for most of the preceding two minutes.
   - **A stale flag passes immediately.** The first check runs right after the
     setpoints are queued, before the heater thread has processed a frame
     against them. The flag is recomputed only when a frame arrives (`:574-580`)
     and is not reset when the setpoint changes (`:590-592`). If the pads were
     flagged stable at the *previous* setpoint, the step reports "Temperatur
     stabil!" at once and the run continues without waiting.
   - **Without a heater port it passes immediately**, because the simulation
     fallback flags both pads stable (`:602-609`).
4. **Timeout.** The operator is asked "Die Temperatur ist nach 120 Sekunden noch
   nicht stabil. Für Simulationszwecke ignorieren und Blueprint fortsetzen?"
   (`:772-788`). **Yes** continues, **No** aborts the run. The answer is not
   recorded in the measurement log.

The first `heat` step also determines the derived `heatingpads` annotation
([§2.2](#22-derivation-of-heatingpads)).

### 3.4 `checkpoint`

```json
{ "type": "checkpoint", "msg": "Ist die Couch Rotation auf 0°?" }
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `msg` | string | `"Checkpoint erreichen und bestätigen."` | prompt text |

Runtime semantics (`terminal.py:702-719`; dialog `:1472-1480`):

- Shows a modal Yes/No box titled "Checkpoint", with Yes as the default button.
- Records the answer in the measurement log in both modes, as the event
  `{"type": "checkpoint", "msg": …, "antwort": true|false}` (`:712`,
  `:1396-1404`).
- **No aborts the run** (`:714-717`); Yes continues. The committed blueprints
  also use checkpoints as plain instructions ("Surface Tracking aktivieren."),
  where answering No aborts as well.

### 3.5 `log_checkpoint`

```json
{ "type": "log_checkpoint", "key": "raumlicht_aus", "mode": "yesno",
  "msg": "Raumlicht im Behandlungsraum aus?" }
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `key` | string | `"notiz"` | name under which the answer is stored |
| `mode` | string | `"yesno"` | lower-cased before use; `"text"` = free text, **any other value** = Yes/No |
| `msg` | string | `"Bitte bestaetigen."` | prompt text |
| `abort_on_no` | boolean | `false` | Yes/No mode only: answering No aborts the run |

Runtime semantics (`terminal.py:815-830`; handler `:1406-1429`):

| Mode | Dialog | Recorded value | Run continues? |
|---|---|---|---|
| `yesno` | Yes/No box "Protokoll-Eintrag", default Yes | `true` or `false` | yes, except for No when `abort_on_no` is true |
| `text` | text input "Notiz fuer das Messprotokoll" | OK: the stripped text (possibly empty); Cancel: nothing | always; `abort_on_no` is ignored |

- The value is stored in the `bedingungen` map of the measurement log under
  `key`, and a repeated key overwrites the earlier value. It is also logged as
  the event `{"type": "log_checkpoint", "key", "wert", "msg"}` (`:1422-1424`).
- **Unlike `checkpoint`, No does not abort** unless `abort_on_no` is set.
- The value appears only in the measurement log, not in any CSV or config
  entry. If recording fails, the run still continues (`:1426-1429`).

### 3.6 `logging`

```json
{ "type": "logging", "action": "start", "prefix": "ETsurface_easyQA" }
{ "type": "logging", "action": "stop" }
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `action` | string | `"start"` | `"start"` or `"stop"`; any other value does nothing |
| `prefix` | string | `"messung"` | file-name stem; used by `start` only; not sanitised |

Runtime semantics (`terminal.py:803-808`; GUI side `:1482-1529`): the
interpreter signals the GUI thread and sleeps a fixed 0.5 s. It does not wait
for the GUI to act.

`start` (`:1483-1523`):

- **If telemetry logging is already running**, for example started with the
  START MESSUNG button, **nothing happens** (`:1484`): no files are created, the
  prefix is ignored and `surf_timestamp` is not set.
- Otherwise it:
  1. fixes a timestamp `YYYYmmdd_HHMMSS` and a time zero (`:1487-1488`);
  2. writes the header of `data/<date>/<prefix>_<ts>_QA.csv` (`:1493-1502`);
  3. starts the telemetry logger on `data/<date>/<prefix>_<ts>.csv`, with a
     0.1 s sampling interval that gives ≈ 9.3 Hz in practice (`:1504-1507`,
     `:378-431`);
  4. sets `surf_timestamp` to the `HHMMSS` part of the timestamp (`:1514`).
- In QA mode, config entries already written by this run with an empty
  `surf_timestamp` are patched now (`:1519-1523`, `:194-207`).
- Both CSVs share the time zero, so `Time_Sec` in the QA CSV is on the same
  clock as in the telemetry CSV (`:1539`).

`stop` (`:1525-1529`, `:1168-1187`):

- Stops the telemetry logger, saves the temperature plot as
  `data/plot_<ts>.png` and opens an information box ("Messung und Plot
  gespeichert."). The interpreter does not wait for that box.
- If logging is not running, nothing happens except a log event.
- The QA CSV path is **not** cleared ([§3.7](#37-qa_input)).

The prefix is the only identification of the motion profile in the data file
names, and the committed blueprints reuse prefixes heavily
([§7](#7-known-pitfalls), item 1).

### 3.7 `qa_input`

```json
{ "type": "qa_input", "mode": "sphere_detection", "point_id": "1_endposition_d1",
  "msg": "Bitte Sphere Detection durchführen und Verschübe eingeben." }
```

| Field | Type | Default | Meaning |
|---|---|---|---|
| `mode` | string | `"surface_tracking"` | selects the input fields and the CSV columns |
| `point_id` | string | `"Unknown"` | label written to the QA CSV; carries metadata ([§4](#4-metadata-carried-in-point_id)) |
| `msg` | string | `"Bitte QA-Werte eintragen."` | text above the input fields |
| `deflection` | integer | parsed from `point_id` | overrides parsing ([§4.2](#42-when-an-exactrac-timestamp-is-requested)) |
| `couch_angle` | integer, degrees | parsed from `point_id`, else 0 | overrides parsing |
| `etds_msg` | string | `"Zeitstempel (HHMMSS) des ExacTrac Tracking Files eingeben."` | prompt of the timestamp dialog |

Runtime semantics (`terminal.py:657-699`; dialogs `:841-884`, `:945-986`;
handlers `:1431-1470`, `:1531-1573`):

1. **ExacTrac timestamp**, only in QA mode and only when a deflection index can
   be determined ([§4.2](#42-when-an-exactrac-timestamp-is-requested)). A
   dialog asks for the time stamp of the ExacTrac tracking file. After all
   non-digits are stripped, any input with exactly six digits is accepted
   ("16:29:19" → "162919"); nothing else is checked (`:975-983`). **Cancel
   aborts the run.** On OK a config entry is appended at once
   ([§4.3](#43-config-entry)), before any values have been entered.
2. **Value dialog.** It has fields X, Y and Z; modes `surface_tracking` and
   `both` add Pitch, Yaw and Roll (`:855-857`). A comma is accepted as decimal
   separator. An empty or unparsable field is stored as an empty string
   (`:875-884`). **Cancel aborts the run.** A config entry written in step 1
   remains.
3. **QA CSV row**, written when OK is pressed and only if a QA CSV path exists
   (`:1538-1555`):

   | Column | Value |
   |---|---|
   | `Time_Sec` | seconds since the current logging start |
   | `Point_ID`, `Mode` | as given in the step |
   | `H_pos`, `V_pos`, `R_pos` | the latest telemetry positions at the moment OK is pressed (commanded step counts) |
   | `Sphere_X`, `Sphere_Y`, `Sphere_Z` | X, Y, Z, **for every mode** |
   | `Surf_X`, `Surf_Y`, `Surf_Z` | X, Y, Z again, **only** for `mode` = `surface_tracking`; empty otherwise |
   | `Pitch`, `Yaw`, `Roll` | the entered values if the mode has these fields, else empty |

   Mode `both` therefore does not collect separate sphere and surface
   translations. It behaves like `sphere_detection` plus rotations, while
   `surface_tracking` duplicates its translations into both column groups. Any
   other `mode` string behaves like `sphere_detection`.
4. The entered values are also logged as a `qa_input` event in the measurement
   log (`:1557-1562`). A cancelled dialog is logged as
   `"werte": "ABGEBROCHEN"` (`:1567-1571`).

The QA CSV path is set by `logging start` and **never cleared**: it is
initialised once (`:1021`), set at `:1494`, and not reset when a blueprint is
loaded (`:1317-1320`). This has two consequences:

- A `qa_input` before the first `logging start` of a run appends its row to the
  QA CSV of the previous logging session in the same terminal session, with
  `Time_Sec` measured from that session's start. If there was no earlier
  session, the row is written to no CSV at all.
- A `qa_input` after `logging stop` still appends to the stopped session's QA
  CSV.

---

## 4. Metadata carried in `point_id`

For each ExacTrac data set the evaluation needs the deflection index and the
couch angle. Blueprints carry both **inside the `point_id` string**, where
regular expressions recognise them (`terminal.py:93-118`), unless the step
states them explicitly.

### 4.1 Patterns

All patterns are Python `re.search`, case-insensitive:

| Pattern | Extracts | If no match | Source |
|---|---|---|---|
| `endposition_d(\d+)` | deflection index *n* | try the legacy pattern | `:94`, `:105-108` |
| `(min\|max)verschub` (legacy names from before the rename) | `min` → 1, `max` → 2 | no deflection (`None`) | `:98`, `:109-112` |
| `couch_?(-?\d+)` | couch angle in degrees | **0, silently** | `:96`, `:115-118` |

- Matching is a substring search, and the first match wins. The leading number
  (`1_`, `6_`) and any other text are ignored.
- The couch pattern accepts `couch-90`, `couch_-90`, `couch90` and `Couch_90`.
  It does **not** accept a `+` sign (`couch_+90` → 0) or whitespace
  (`couch 90` → 0).
- The deflection index is not range-checked: `endposition_d3` yields 3. The
  timestamp dialog labels 1 "min", 2 "max" and any other value "?" (`:959`).
- What deflections 1 and 2 are physically is defined only by the sequence
  before the point. In the final `qa/` blueprints d1 follows H −10 mm, V +20 mm,
  R +1° and d2 follows H −30 mm, V +50 mm, R +2°. At the couch −90 points of the
  `wcouch` files the same excursions are driven about R = 90°, i.e. to R +91°
  and +92°. The two `_draft` variants use H +12.65 mm, V +9.41 mm, R +1° and
  H −37.97 mm, V −31.23 mm, R +2°.

### 4.2 When an ExacTrac timestamp is requested

In QA mode (`:665`), each `qa_input` step evaluates (`:666-668`):

```text
deflection = step["deflection"] if present, else parse_deflection(point_id)
if deflection is not None:
    couch_angle = step["couch_angle"] if present, else parse_couch_angle(point_id)   # 0 if absent
    -> ExacTrac timestamp dialog -> config entry
```

Consequences:

- A `point_id` that matches neither `endposition_d<n>` nor
  `(min|max)verschub` produces **no timestamp prompt and no config entry**, and
  there is no warning. Typos fall into this case, e.g. `endpositon_d1`,
  `end_position_d1` or `endposition-d1`.
- The legacy names (`1_minVerschub`, `8_MaxVerschub_couch-90`) still trigger a
  prompt and an entry.
- An explicit `deflection` forces the prompt for any `point_id`.
- A missing couch suffix yields `couch_angle` 0 without a warning.

### 4.3 Config entry

One entry is appended per accepted timestamp dialog (`terminal.py:1439-1459`,
`:184-192`), for example:

```json
"7": {
  "Linac": "1",
  "deflection": 1,
  "meas_couch_type": "multi angle",
  "heatingpads": "32",
  "etds_timestamp": "162919",
  "surf_timestamp": "162500",
  "couch_angle": -90
}
```

| Field | Source |
|---|---|
| key | the largest numeric key in the file plus one, as a string (`"1"` for an empty file) |
| `Linac` | session dialog |
| `deflection`, `couch_angle` | [§4.2](#42-when-an-exactrac-timestamp-is-requested) |
| `meas_couch_type`, `heatingpads` | session dialog, pre-filled per [§2.2](#22-derivation-of-heatingpads) and [§2.3](#23-derivation-of-meas_couch_type) |
| `etds_timestamp` | the six digits entered |
| `surf_timestamp` | `HHMMSS` of the current telemetry CSV. If logging has not started yet it is `""` (the dialog and the console point this out, `:961`, `:1455-1456`) and is patched at the next `logging start` of the same run (`:194-207`, `:1519-1523`) |

- The file is re-read and completely rewritten for every entry (`:172-182`).
  Other keys are preserved.
- If writing fails, the error is reported on the console and **the run
  continues** without the entry (`:1457-1459`).
- The entry has no date. `surf_timestamp` is six digits of wall-clock time and
  identifies the telemetry CSV only together with the date and the prefix.

### 4.4 Examples

All values below come from running `parse_deflection` and `parse_couch_angle`,
extracted from `terminal.py`:

| `point_id` | Deflection | Couch angle | Timestamp prompt (QA mode) |
|---|---|---|---|
| `0_Referenz` | — | 0 | no |
| `1_endposition_d1` | 1 | 0 | yes |
| `3_endposition_d2` | 2 | 0 | yes |
| `1_minVerschub` | 1 | 0 | yes (legacy) |
| `3_MaxVerschub` | 2 | 0 | yes (legacy) |
| `5_referenz_couch-90` | — | −90 | no, but the angle counts for `meas_couch_type` |
| `6_endposition_d1_couch-90` | 1 | −90 | yes |
| `8_MaxVerschub_couch-90` | 2 | −90 | yes (legacy) |
| `x_couch-90_endposition_d1` | 1 | −90 | yes; order does not matter |
| `endposition_d3` | 3 | 0 | yes; the dialog shows "?" |
| `p_couch_+90` | — | **0** | no |
| `endposition-d1` | — | 0 | **no** |

---

## 5. Worked example

The blueprint below is not part of the repository. It validates against the
schema and exercises the common constructs.

```json
{
  "name": "Worked example - one deflection at couch 0",
  "sequence": [
    { "type": "checkpoint", "msg": "Sind alle Achsen gehomed und das Phantom korrekt montiert?" },
    { "type": "heat", "a": 32.0, "b": 32.0, "wait_steady": true },
    { "type": "log_checkpoint", "key": "raumlicht_aus", "mode": "yesno", "msg": "Raumlicht im Behandlungsraum aus?" },
    { "type": "logging", "action": "start", "prefix": "worked_example" },
    { "type": "qa_input", "mode": "sphere_detection", "point_id": "0_Referenz", "msg": "Bitte Sphere Detection durchführen und Isozentrum eingeben." },
    { "type": "move", "R": 1.0, "H": -10.0, "speed": 5.0 },
    { "type": "delay", "time": 2.0 },
    { "type": "qa_input", "mode": "sphere_detection", "point_id": "1_endposition_d1", "msg": "Bitte Sphere Detection durchführen und Verschübe eingeben." },
    { "type": "move", "H": 0.0, "R": 0.0, "speed": 5.0 },
    { "type": "logging", "action": "stop" },
    { "type": "checkpoint", "msg": "Messung wurde beendet." }
  ]
}
```

Assumptions: the file is saved as `worked_example.json`; H and V are homed and
R is zeroed; the blueprint is loaded on 2026-09-15 at 16:20:00 in QA mode, with
an empty config file (`{}`); the operator enters Linac `1` and Personal
`QMP1`. All times are illustrative, and entered values are shown as
placeholders.

**At load.** `scan_blueprint_meta` returns `heatingpads` = `"32"` (first `heat`
step, rule 2) and `meas_couch_type` = `"single angle"` (both `qa_input` points
at couch 0). The session dialog is pre-filled with these values. The files
`data/2026-09-15/worked_example_20260915_162000_log.json` and `….txt` are
created.

| # | Step | What happens | Bytes on the wire |
|---|---|---|---|
| 0 | `checkpoint` | Yes/No box; the answer is logged. No ends the run here. | — |
| 1 | `heat` a, b = 32 | Both setpoints are queued: 32 °C surface = 33.94 °C internal = 3394. The step then waits up to 120 s for both pads. It passes at once if both were already flagged stable, at any previous setpoint ([§3.3](#33-heat)). If the pads still have to heat, it ends in the timeout prompt: Yes continues, No aborts. | heater: `01 42 0D 00 00`, `02 42 0D 00 00` |
| 2 | `log_checkpoint` | Yes/No box; the answer is stored as `bedingungen.raumlicht_aus`. No does **not** abort. | — |
| 3 | `logging` start | At 16:21:05 the files `data/2026-09-15/worked_example_20260915_162105.csv` (telemetry) and `…_162105_QA.csv` (header only) are created, and `surf_timestamp` becomes `"162105"`. The interpreter continues after 0.5 s. | — |
| 4 | `qa_input` `0_Referenz` | No deflection, so no timestamp dialog. X/Y/Z dialog (Cancel would abort); a row is appended to the QA CSV. | — |
| 5 | `move` R 1, H −10 | **H first**, despite the key order: H to −8000 steps at 4000 steps/s (5 mm/s), then wait for `COMMAND_DONE`. **Then** R to 16 steps = 0.9903° at 80 steps/s = 4.95 °/s, then wait for `COMMAND_DONE`. | axis: `01 00 C0 E0 FF FF A0 0F 00 00`, then `01 02 10 00 00 00 50 00 00 00` |
| 6 | `delay` 2.0 | 20 slices of 0.1 s. | — |
| 7 | `qa_input` `1_endposition_d1` | Deflection 1, couch 0, so the timestamp dialog appears. The operator types `16:23:40`, stored as `"162340"`, and config entry `"1"` is written **now**. Then the X/Y/Z dialog; the QA CSV row gets `H_pos` −10.0 and `R_pos` 0.9903…. | — |
| 8 | `move` H 0, R 0 | H to 0, then R to 0. | axis: `01 00 00 00 00 00 A0 0F 00 00`, then `01 02 00 00 00 00 50 00 00 00` |
| 9 | `logging` stop | The telemetry logger stops, `data/plot_20260915_162105.png` is saved and an information box opens. | — |
| 10 | `checkpoint` | Yes/No box. No would be logged as `antwort: false`, and the run ends either way. | — |

Resulting config file:

```json
{
  "1": {
    "Linac": "1",
    "deflection": 1,
    "meas_couch_type": "single angle",
    "heatingpads": "32",
    "etds_timestamp": "162340",
    "surf_timestamp": "162105",
    "couch_angle": 0
  }
}
```

Resulting QA CSV, with `<t>` and `<X>`/`<Y>`/`<Z>` standing for the actual
times and entered values:

```text
Time_Sec;Point_ID;Mode;H_pos;V_pos;R_pos;Sphere_X;Sphere_Y;Sphere_Z;Surf_X;Surf_Y;Surf_Z;Pitch;Yaw;Roll
<t>;0_Referenz;sphere_detection;0.0;0.0;0.0;<X>;<Y>;<Z>;;;;;;
<t>;1_endposition_d1;sphere_detection;-10.0;0.0;0.9903441445902452;<X>;<Y>;<Z>;;;;;;
```

The measurement log contains `modus` "QA (Config wird beschrieben)",
`blueprint_file` "worked_example.json", `heatingpads` "32", `meas_couch_type`
"single angle", `csv_file` "worked_example_20260915_162105.csv",
`surf_timestamp` "162105", `bedingungen` `{"raumlicht_aus": true}`, one item
under `config_entries`, and these events in order: `checkpoint`,
`log_checkpoint`, `logging` (start), `qa_input`, `etds_timestamp`, `qa_input`,
`logging` (stop), `checkpoint`.

The outputs do **not** reveal the following:

- whether the `heat` wait succeeded, timed out, or passed on a stale flag;
- whether R was zeroed. If it was not, step 5's R move was skipped silently,
  `R_pos` reads 0.0 and no error appears anywhere;
- whether R backlash compensation was on.

---

## 6. Schema strictness

The schema rejects some blueprints that the interpreter would run. This is
deliberate: each difference removes a way to write a blueprint that runs but
does something other than intended.

| Construct | Interpreter | Schema |
|---|---|---|
| Top-level keys other than the four in [§2.1](#21-keys) | ignored | rejected |
| `name` | optional | required, non-empty string |
| `sequence` | optional; may be empty | required; at least one step |
| `heatingpads` | any value, converted with `str()` | `"OFF"` or digits with optional decimals, as a string |
| `meas_couch_type` | any value, converted with `str()` | `"single angle"` or `"multi angle"` |
| Step `type` missing or unknown | step skipped | rejected |
| Keys a step type does not use | ignored | rejected |
| `move` without `H`, `V` or `R` | no-op | rejected |
| `move.speed` | optional (20.0); any number | required; ≥ 0.062; ≤ 50 if H or V is present, ≤ 90 for R-only steps. The lower bound exists because any R speed below 1/16.156 °/s truncates to 0 steps/s, which the controller's move loop never finishes ([serial protocol §4.3](serial-protocol.md#move_axis-1-10-bytes)) |
| `move` targets | any number, unchecked | H −45 … 25, V −35 … 50, R −30 … 120 (the firmware limits) |
| Numeric strings such as `"5"` | accepted where the handler calls `float()` (targets, `time`, `a`, `b`) | rejected |
| `delay.time` | optional (2.0); negative values do not sleep | required, ≥ 0 |
| `heat` without `a` and `b` | allowed (only waits, if `wait_steady`) | rejected |
| `heat.a`, `heat.b` | any number | 0 … 50 |
| `heat.wait_steady`, `log_checkpoint.abort_on_no` | any truthy value | boolean |
| `checkpoint.msg`, `log_checkpoint.msg` | optional | required, non-empty |
| `log_checkpoint.key` | optional (`"notiz"`); any string | required; `^[A-Za-z0-9_]+$` |
| `log_checkpoint.mode` | case-insensitive; anything other than `text` means Yes/No | exactly `"yesno"` or `"text"` |
| `abort_on_no` with `mode: "text"` | ignored | must be `false` or absent |
| `logging.action` | optional (`"start"`); unknown values do nothing | required; `"start"` or `"stop"` |
| `logging.prefix` | optional (`"messung"`); ignored on `stop`; not sanitised | required on `start`, forbidden on `stop`; `^[A-Za-z0-9][A-Za-z0-9_.-]*$` |
| `qa_input.mode` | optional (`"surface_tracking"`); unknown values behave like `sphere_detection` | required; `"sphere_detection"`, `"surface_tracking"` or `"both"` |
| `qa_input.point_id` | optional (`"Unknown"`) | required, non-empty |
| `qa_input.deflection` | anything `int()` accepts; even 0 triggers the prompt | integer ≥ 1 |
| `qa_input.couch_angle` | anything `int()` accepts | integer, −360 … 360 |

Checks the schema cannot express:

- that a `point_id` intended as a deflection point actually matches
  [§4.1](#41-patterns);
- that `logging start` comes before the first `qa_input`, and that logging
  prefixes are unique;
- that R has been zeroed and backlash compensation is in the intended state;
- that every move finishes within the 60 s watchdog;
- that `wait_steady` can succeed. For example, `a: 0` with `wait_steady: true`
  can never become stable and always ends in the timeout prompt;
- that `name` describes the sequence.

---

## 7. Known pitfalls

### Identifying what was measured

1. **One logging prefix for 16 blueprint files.**
   `ETD_QA_PoP_SingleCouchOrientation` is the `prefix` of every
   `ETD_QA_PoP_SingleCouchRotation*.json`: 10 files in `heating-off/` and 6 in
   `pop/`. These 16 files have 10 distinct file names and 9 distinct move/delay
   sequences:
   - ±10 mm H and V plus ±5° R;
   - the same about R = 90°;
   - H only;
   - V only;
   - R only;
   - ±3 mm H, partly with 1 s pauses;
   - an R amplitude sweep;
   - the same sweep with three repetitions per amplitude;
   - an R speed sweep.

   The `OnlyH` and `VerticalSlide` files share one sequence. **The telemetry and
   QA CSV file names therefore do not identify the motion profile.** The same
   happens on a smaller scale in `qa/`. `ETsurface_easyQA` is the prefix of
   four files with two different motion profiles: `ETsurface_easyQA.json` and
   `_new.json` versus `_draft.json` and `_draft_new.json`. The prefixes
   `ETsurface_easyQA_T32`, `ETsurface_easyQA_wcouch` and
   `ETsurface_easyQA_wcouch_T32` are each shared by a file and its `_new`
   variant.
2. **The measurement log helps only partly.** It records `blueprint_file`, but
   only as a base name (`terminal.py:1351`), and `pop/` and `heating-off/`
   contain six identical base names. The heated and unheated variants can then
   be told apart only by the `heatingpads` annotation (which the operator can
   edit in QA mode) or by the checkpoint texts recorded in the events. Archived
   `_log.json` files exist only from 2026-08-06 onward.
3. **Wrong `name` fields.** Checked against the sequences:

   | File | `name` says | The sequence actually moves |
   |---|---|---|
   | `heating-off/ETD_QA_PoP_SingleCouchRotation_OnlyR.json` | "ETD QA Basic Proof of Principle - Statistics for one Movement V" | R only (±5°), plus the H marker moves at start and end |
   | `pop/ETD_QA_PoP_SingleCouchRotation_OnlyR.json` | same | same |
   | `heating-off/ETD_QA_PoP_SingleCouchRotation_RvarySpeed.json` | "ETD QA Basic Proof of Principle - Statistics for one Movement V" | R ±5° at 15, 10, 5, 2, 1 and 0.5 °/s |
   | `heating-off/ETD_QA_PoP_SingleCouchRotation_RvaryAmp.json` | "ETD QA PoP - Rotation with increasing Amplitude (3 times each Amp)" | each amplitude (1, 2, 3, 4, 5, 6, 8, 10 … 30°) **once**. The three-fold sweep is `…_RvaryAmpX3.json`, which carries the same name |

   Other names are not wrong but fail to distinguish files:
   - "ETD QA Basic Proof of Principle" is used by `pop/ETD_QA_BasicPoP.json`
     and by both copies of `…SingleCouchRotation.json` and
     `…SingleCouchRotation90Deg.json`, which are three different profiles.
   - "… Statistics for one Movement Axis H" is used by `OnlyH` (±10 mm) and
     `OnlyH_Clin` (±3 mm).
   - The ten `qa/` files share two names between them, regardless of draft or
     final motion and of temperature.
4. **Blueprints changed during the campaigns without being versioned.** Data
   file names carry the prefix but no blueprint revision, and the committed
   history of the blueprints starts on 2026-03-09. Example: four of the
   `data/raw/2026-02-pilot/ETD_QA_BasicPoP_20260217_*.csv` files contain ±30 mm
   excursions, whereas the earliest committed `ETD_QA_BasicPoP.json` (commit
   `d7f39ed`, 2026-03-09) moves ±10 mm and ±5°. Do not assume that a data file
   was produced by the blueprint that is in the repository today.

### Motion

5. **Multi-axis `move` steps run one axis after another, in the order H, V, R**,
   never simultaneously ([§3.1](#31-move), item 1).
6. **Rejected moves look like executed moves.** Blueprint moves get no PC-side
   limit check. The firmware acknowledges out-of-range targets, and every R
   target before R is zeroed, as if they had been executed
   ([§3.1](#31-move), items 4–5). Take the positions actually reached from the
   telemetry CSV, not from the blueprint.
7. **R targets and speeds are truncated to whole steps.** In the committed
   blueprints this reduces magnitudes by up to 0.058° ([§3.1](#31-move),
   item 3).
8. **Commanded H/V speeds above about 5 mm/s are not realised**
   ([§3.1](#31-move), item 6). Profiles that differ only in linear speed are,
   in practice, the same profile.
9. **R backlash compensation is hidden state.** No output records it
   ([§3.1](#31-move), item 8).
10. **Neither `exit bp` nor STOP ALL stops a move in progress**
    ([§1.3](#13-aborting-and-errors); [serial protocol §4.3](serial-protocol.md#stop_all-3-1-byte)).

### Metadata

11. **`point_id` typos fail silently**, with no timestamp prompt and no config
    entry ([§4.2](#42-when-an-exactrac-timestamp-is-requested)). A missing or
    `+`-signed couch suffix yields couch angle 0 ([§4.1](#41-patterns)).
12. **`meas_couch_type` is derived from `qa_input` steps only.** It counts
    reference points too, and couch rotations requested in checkpoint text are
    invisible to it ([§2.3](#23-derivation-of-meas_couch_type)).
13. **`heatingpads` is an annotation, not a command.** It can come from the file
    name of a blueprint that never heats ([§2.2](#22-derivation-of-heatingpads)).
14. **A config entry is written before the values are entered.** Cancelling the
    value dialog aborts the run but leaves the entry behind ([§3.7](#37-qa_input)).
15. **The config file dialog accepts any JSON file**, including a blueprint
    ([§1.1](#11-loading-and-mode-selection)).

### Heating

16. **`wait_steady` rarely does what its name says.** After a setpoint change it
    passes at once on a stale flag. Otherwise it cannot complete a real
    temperature change within its 120 s window. The operator's answer to the
    timeout prompt is not logged ([§3.3](#33-heat)).

### Operator flow and files

17. **`logging start` while logging is already running does nothing.** No files
    with the blueprint's prefix are created, and `surf_timestamp` stays empty
    in every config entry of the run ([§3.6](#36-logging)).
18. **`qa_input` rows can land in the wrong QA CSV.** Before the first
    `logging start` of a run they go into the previous session's file, or
    nowhere ([§3.7](#37-qa_input)).
19. **An abort leaves logging running and the heaters on**
    ([§1.3](#13-aborting-and-errors)).
20. **A `delay` of 1.0 s lasts 1.1 s** ([§3.2](#32-delay)).
    `heating-off/ETD_QA_PoP_SingleCouchRotation_OnlyH_Clin.json` contains
    eight of them.
21. **Unknown step types and misspelt keys are ignored without a message**
    ([§1.2](#12-step-dispatch)). Validate blueprints against the schema before
    use, because the terminal does not.
22. **Duplicate `point_id`s.** `qa/ETsurface_easyQA_draft.json` and
    `qa/ETsurface_easyQA_draft_new.json` each use `4_zeroposition` twice, once
    with `surface_tracking` and once with `sphere_detection`.
23. **Mode `both` does not record separate sphere and surface translations**
    ([§3.7](#37-qa_input)).
