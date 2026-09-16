# Known issues: acquisition chain

This register lists the defects we know of in the acquisition chain of the SURF
Test Unit. It serves two readers:

- maintainers of the acquisition code;
- anyone reusing the archived data, who needs to know which values to distrust.

**Scope.** The register covers:

- the axis firmware, the heater firmware and the rotation calibration sketch;
- the measurement terminal and the blueprints;
- the raw files these produced under `data/raw/`.

Issues in the evaluation chain (time alignment, kinematic model, statistics)
belong to the analysis repository
[`surf-etds-analysis`](https://github.com/AG-Kollotzek/surf-etds-analysis) and are not
tracked here.

**Status.** None of these defects has been fixed in this release. The release
preparation made no functional change to the firmware or the measurement path
(CHANGELOG.md:7–8). Several issues concern code that moves hardware in a
treatment room.

## How to read this register

**Files.** Evidence cites `file:line`. The basenames are unique in the repository:

| Basename | Path |
|---|---|
| `terminal.py` | `software/surf_terminal/terminal.py` |
| `SURF_nanoAxis_v5.ino` | `firmware/axis/SURF_nanoAxis_v5/SURF_nanoAxis_v5.ino` |
| `SURF_nanoHeating_v4.ino` | `firmware/heating/SURF_nanoHeating_v4/SURF_nanoHeating_v4.ino` |
| `rotation_calibration.ino` | `firmware/tools/rotation_calibration/rotation_calibration.ino` |

Line numbers refer to the release-preparation branch. They are identical to the
pre-release commit `1d19cc7`: the firmware files were only moved, and
`terminal.py` differs only by a `main()` wrapper appended at its end and one
placeholder string.

**Code versions.** The archived campaigns were recorded with several successive
versions of the firmware and terminal. Where it matters, an entry states from
which commit a defect exists. Commit dates bound deployment only approximately.
For example, firmware committed at 16:37 on 2026-02-24 was already running at
16:27 that day (KI-11). The repository does not record which firmware was
flashed for any campaign (KI-09).

**Archived files.** Statements about archived data come from scanning every file
under `data/raw/` and the git history:

- **Main-format telemetry.** 118 CSVs, header `Time_Sec;Pos_H;…;Stable_B`, from
  2026-02-10 onward.
- **QA side files.** 21 `_QA.csv` files.
- **Measurement protocols.** 16 files (`_log.json` / `_log.txt`), from
  2026-08-06 onward.
- **Pilot-format CSVs.** 12 files (`PC_Time,Arduino_Time,…`) from 2025-12 and
  2026-01, written by superseded terminals that were removed during release
  preparation. Unless stated otherwise, the entries below do not apply to them.

Runs are named by directory and CSV start time, e.g. *2026-02-24 16:48:07*. The
paths are listed in the table at the end.

**Wording.** "Consistent with" means the data fit the stated mechanism, but the
repository does not allow proof.

**IDs.** Issue IDs are stable and are not reused. Entries are listed by
severity. KI-22 and KI-23 were added after the initial numbering, so they appear
inside their severity group rather than at the end.

**Severity.**

| Severity | Meaning |
|---|---|
| Critical | Silently falsifies ground truth or hardware presence in the archived record, defeats a safety control, or can actuate hardware against the operator's command. |
| High | Silently loses or corrupts measurement records or their linkage, invalidates a documented quality gate or experimental parameter, or makes the ground truth unverifiable. |
| Medium | Degrades accuracy, timing or traceability in a bounded way that can be characterised, or is a latent defect with a plausible trigger. |
| Low | Robustness, maintainability or documentation defects with small or no effect on data. |

## Summary

| ID | Severity | Component | Title |
|---|---|---|---|
| [KI-01](#ki-01) | Critical | Axis firmware, interpreter | Rejected moves are acknowledged as completed |
| [KI-02](#ki-02) | Critical | Terminal workers | An unopenable serial port silently switches to simulation and fabricates a complete run |
| [KI-03](#ki-03) | Critical | Terminal, axis firmware | STOP ALL cannot interrupt a move, and stalls the handshake when idle |
| [KI-22](#ki-22) | Critical | Terminal, both firmwares | Swapped USB ports make each controller execute the other's commands |
| [KI-04](#ki-04) | High | Terminal workers | A USB dropout ends the worker thread; logging continues with frozen values |
| [KI-05](#ki-05) | High | Axis firmware, terminal | Logged positions are commanded step counts; driver alarms are discarded and errors beyond the motor shaft are unobservable |
| [KI-06](#ki-06) | High | Axis firmware, terminal | Axis reference (homing, zero) is neither enforced, verified nor recorded |
| [KI-07](#ki-07) | High | Terminal (QA mode) | ExacTrac linkage file: unvalidated selection, non-atomic writes, swallowed failures |
| [KI-08](#ki-08) | High | Terminal (heat step) | `wait_steady` cannot confirm a temperature change, and its outcome is not recorded |
| [KI-23](#ki-23) | High | Axis firmware, blueprints | Linear axes never exceed about 5 mm/s, whatever speed is commanded |
| [KI-09](#ki-09) | High | Terminal, file formats | No persisted event log or run provenance |
| [KI-10](#ki-10) | Medium | Terminal, file formats | Sampling rate, timestamps and latency |
| [KI-11](#ki-11) | Medium | Axis firmware (historical) | Firmware before 2026-02-24 reported no positions during moves |
| [KI-12](#ki-12) | Medium | Axis firmware, terminal | Backlash compensation: state unrecorded, correction hidden |
| [KI-13](#ki-13) | Medium | Terminal, firmware, calibration | Rotation scale factor: inconsistent, undocumented, truncated |
| [KI-14](#ki-14) | Medium | Terminal, heater firmware | Logged heater state is a PC-side assumption |
| [KI-15](#ki-15) | Medium | Terminal, axis firmware | Command handshake: no framing, no command identity, timeout treated as success |
| [KI-16](#ki-16) | Medium | Terminal | Serial ports hard-coded; output paths relative to the working directory |
| [KI-17](#ki-17) | Medium | Terminal (QA input) | `_QA.csv` side files: stale paths, silent input loss, ambiguous columns |
| [KI-18](#ki-18) | Medium | Terminal | Blueprints are decoded with the platform default encoding |
| [KI-19](#ki-19) | Low | Terminal | `closeEvent` calls `QThread` methods on a `threading.Thread` |
| [KI-20](#ki-20) | Low | Heater firmware | PI update: unreachable integral reset; comment disagrees with code |
| [KI-21](#ki-21) | Low | Firmware, terminal, notes | Misleading comments and console messages |

---

<a id="ki-01"></a>
## KI-01: Rejected moves are acknowledged as completed

**Severity:** Critical · **Component:** axis firmware, terminal interpreter

**Evidence**

- `SURF_nanoAxis_v5.ino:323` computes `limits_ok`, and all motion is inside
  `if (limits_ok) { … }` (:326–376). `write_i8(COMMAND_DONE)` at :377 is outside
  that block, so a rejected move is acknowledged exactly like a completed one.
- `isTargetSafe()` (:143–156) rejects every R target while `rAxisInitialized` is
  false (:152).
  - The flag starts false (:99). It is set only by `HOME_AXIS` for R (:392–397)
    or `SET_ZERO` for R (:420–424).
  - R has no endstop: "homing" R merely declares the current angle zero (:393).
  - The flag is held in RAM and cleared by every controller reset. Nano boards
    typically reset when the terminal opens the serial port at start-up
    (`terminal.py:450`).
- The blueprint DSL has no homing or zeroing step (`terminal.py:657–830`). R must
  be initialised from the console in every controller session.
- The PC checks `LIMITS` (`terminal.py:46–50`) only for manual `m` commands
  (:1216–1219). Blueprint moves are converted and queued with no check
  (:722–747). The firmware is therefore the only guard, and its limits are step
  counts relative to whatever zero is current (KI-06).
- The same structure existed in the axis firmware in use from 2026-02-16 onward
  (`SURF_nanoAxis_v1.2.ino` at commits `3f922f5` and `533a9bd`, renamed to v5 in
  `d7f39ed`).

**Symptom.** An out-of-limits move, or any R move before R has been zeroed in
the current controller session, produces no motion. The console prints
">> Achse: Bewegung abgeschlossen." (`terminal.py:483`), and the blueprint
continues with its delays and prompts as if the phantom had moved.

**Effect on archived data**

- The logged positions remain truthful here: they report the unchanged step
  counter. Analyses that use `Pos_H/V/R` as ground truth are not biased by this
  defect.
- Analyses that take blueprint targets as nominal positions, or that segment
  tracker data by the expected motion sequence, are wrong for affected runs.
- **Instance consistent with this defect: *2026-02-24 16:48:07*.**
  - The blueprint version of that day (commit `533a9bd`) commands R 0 → +5 → −5 →
    0° at 5°/s between the V section and the final H section. `Pos_R` stays 0.00
    for the whole run.
  - The measured gap from the end of the V section (t = 47.46 s) to the next H
    motion (t = 58.12 s) is 10.66 s.
  - Five 2 s delays with immediate acknowledgements predict about 10 s. Four
    executed rotations would add about 4.4 s of motion (≈14.4 s in total).
  - As a control, the same segmentation gives 3.99 s for the two-delay,
    one-zero-move sequence between the H and V sections of that run.
  - The two earlier runs that afternoon (16:16:39, 16:27:04) did rotate.
- A complete scan for this failure is not possible, because the CSVs do not
  record which blueprint, or which blueprint version, produced them (KI-09).
  Treat as suspect any run whose `Pos_R` never changes although its blueprint
  family commands R.
- No file records a rejected move.

---

<a id="ki-02"></a>
## KI-02: An unopenable serial port silently switches to simulation and fabricates a complete run

**Severity:** Critical · **Component:** terminal (`AxisThread`, `HeatThread`, `LoggerThread`)

**Evidence**

- If `serial.Serial()` raises, the exception is caught and the thread continues
  with `ser = None`:
  - axis thread, `terminal.py:448–455`, console message "Fehler: Gerät nicht
    gefunden. Erzwungene Simulation!";
  - heater thread, :543–551, console message "Heiz-Simulation aktiv.".
- `SIMULATION_MODE` (:67) does not control this fallback.
- **Axis simulation** acknowledges every command after 0.5 s (:517–520).
  `state.pos` is never updated and stays at its initial 0.0 (:343).
- **Heater simulation** copies each setpoint into the temperature and forces
  `stable = True` every 0.1 s (:603–609). `wait_steady` therefore passes at once
  (:762–768).
- The logger writes rows whenever `state.is_logging` is set, regardless of
  hardware (:393–431).
- Nothing records the simulation:
  - no CSV column;
  - no protocol field (:223–241);
  - no config field;
  - console output is not persisted (:1128–1133).
- The fallback has existed since at least commit `b732943` (2026-02-18), where
  the message is spelled "Erpzwungene". It therefore covers every main-format
  campaign.

**Symptom.** When a port is missing or renamed (see KI-16), the terminal starts
normally. Blueprints run with plausible timing and the operator answers the
prompts. The run writes telemetry, `_QA.csv` and protocol files, with positions
0.0 and temperatures equal to the setpoints. If only one port fails, real and
fabricated columns are mixed in the same file.

**Effect on archived data**

- **Signatures.**
  - Heater simulated: `Temp_A == Set_A`, `Temp_B == Set_B` and
    `Stable_A = Stable_B = 1` in every row.
  - Axis simulated: all positions identically 0.0 although the blueprint moves.
- **Three archived runs carry the heater signature.**
  - ***2026-03-10 15:28:31*** (17.4 s). The heater thread was simulated. The axis
    state cannot be determined, because no move falls inside the recording.
    `data/raw/2026-03-10/runs.csv:2` marks it as not used in the analysis.
  - ***2026-08-06 15:20:05***, with its `_QA.csv` and the protocol
    `ETsurface_easyQA_new_20260806_151955_log.*`. Both threads were simulated:
    - the protocol shows the whole blueprint ran;
    - every `_QA.csv` position is 0.0;
    - Linac "5", sphere values 0/1 and ETDS timestamps "999999" mark a dry run;
    - the protocol's POSIX path separators mark a non-Windows machine;
    - the run wrote two placeholder entries into the config file it had selected
      (KI-07).
  - ***2026-08-21 09:30:58***, with its `_QA.csv` and the protocol
    `ETD_QA_PoP_SingleCouchRotation_20260821_093044_log.*`. Both threads were
    simulated: ±10 mm moves lie within the limits, yet no position changed. The
    Linac field reads "X", and a blueprint was selected as the config file (KI-07).
    **The entire `data/raw/2026-08-21/` directory consists of this simulated run.**
- **Constant-position runs.** Eleven main-format CSVs have all three axes constant
  for the whole recording, five of them with constant temperature as well. Only
  the three runs above carry the simulation signature. The remaining eight:
  - Five are short or motion-free recordings with live temperature readings:
    *2026-02-10 17:48:07*, *2026-02-10 18:41:14*, *2026-02-16 17:55:30*,
    *2026-02-17 16:24:06* (a heater test) and *2026-05-13 14:47:31* (stopped
    after the first QA input).
  - Three are blueprint runs of the February pilot with a live heater and no
    motion: *2026-02-17 17:25:15*, *2026-02-17 17:30:52* and
    *2026-02-19 17:26:43*. The cause cannot be determined. Candidates are an axis
    port that did not open, dropped moves (KI-15), or a run aborted before the
    first move. The terminal commit of 2026-02-18 (`b732943`) describes an
    interpreter bug fix; whether that bug is involved is not recorded.
- A simulated axis next to a live heater gives constant positions with realistic
  temperatures. Without the blueprint and its timing, this cannot be told apart
  from "no motion commanded".

---

<a id="ki-03"></a>
## KI-03: STOP ALL cannot interrupt a move, and stalls the handshake when idle

**Severity:** Critical · **Component:** terminal (GUI, `AxisThread`), axis firmware

**Evidence**

- The STOP ALL button only enqueues the command (`terminal.py:1110–1112`).
- The axis thread sends queued commands only while `state.axis_ready` is true
  (:488–492). `axis_ready` is false from the moment a move is dequeued (:496–498)
  until its `COMMAND_DONE` is parsed (:480–482).
- The firmware executes a move in a blocking loop that neither reads the serial
  port nor checks the driver alarm inputs (`SURF_nanoAxis_v5.ino:368–374`). A
  stop byte is read only after the move has finished.
- `STOP_ALL` calls `stop()` on all steppers and sends no reply (:429–432). On
  idle steppers `stop()` does nothing.
- Because the PC has already set `axis_ready = false` on dequeuing the command
  (`terminal.py:496–498`), the handshake stays blocked until the 60 s watchdog
  releases it (:459–462).
- STOP_ALL is the only opcode the terminal sends that is never answered. MOVE_AXIS
  and HOME_AXIS also go unanswered while the firmware is in alarm state (KI-15).
- `exit bp` (:1281–1285) stops the interpreter after the current move, but does
  not stop the axis.
- Since commit `76beb9d` (2026-03-10), every dequeued command blocks the
  handshake. Before that only MOVE_AXIS and HOME_AXIS did, so the 60 s stall
  applies from the 2026-03-10 campaign onward.

**Symptom**

- Pressed during a move, STOP ALL does nothing until the move has finished. The
  command then reaches an idle controller, which neither acts nor answers.
- The next blueprint move starts up to 60 s later, and the blueprint is not
  aborted.
- The README states that there is no hardware emergency stop (README.md:29–30).

**Effect on archived data.** No direct corruption. A press during a run appears
as a gap of up to 60 s before the next move, indistinguishable in the CSV from an
operator pause. No run can be checked for this, because button presses are not
logged (KI-09).

---

<a id="ki-22"></a>
## KI-22: Swapped USB ports make each controller execute the other's commands

**Severity:** Critical · **Component:** terminal (port assignment), axis and heater firmware (protocol) · **Also described in:** `docs/safety.md` G7

**Evidence**

- **Assignment by port name only.** The terminal assigns the two boards solely by
  hard-coded port name (`terminal.py:27–40`, :1008, :1012; KI-16) and performs no
  handshake before sending commands. Neither firmware identifies itself: `HELLO`
  has an empty handler (`SURF_nanoAxis_v5.ino:308`), and the heater firmware has no
  identification command at all.
- **The opcodes collide.** `MOVE_AXIS` = 1 = `CMD_SET_A`, and `HOME_AXIS` = 2 =
  `CMD_SET_B` (`SURF_nanoAxis_v5.ino:13–14`, `SURF_nanoHeating_v4.ino:13–14`).
- **Axis commands on the heater board.** The heater parser
  (`SURF_nanoHeating_v4.ino:133–147`) reads a move frame
  `[1][axis][target i32][speed i32]` (`terminal.py:504–510`) as `CMD_SET_A`, with a
  value built from the axis byte and the three low target bytes.
  - Any positive target of 26 steps or more yields a value above 65.00. The clamp
    (:143) turns it into a 65 °C setpoint for pad A. Twenty-six steps is 0.0325 mm
    on H or V, or 1.6° on R.
  - Example: `m h 10 5` sends `01 00 40 1F 00 00 A0 0F 00 00`. The heater reads
    20 480 °C and clamps it to 65 °C.
  - Negative and zero targets set pad A to about 0 °C.
- **Heater commands on the axis board.** The axis parser
  (`SURF_nanoAxis_v5.ino:297–433`) reads a setpoint frame `[pad][value i32]`
  (`terminal.py:596–598`) as an axis command. Over the terminal's accepted range
  (10.0–50.0 °C in 0.1 °C steps), a single `t b` command decodes as:
  - homing of H: `t b 20.5`;
  - homing of V: `t b 22.7` and `t b 40.2`;
  - zeroing of R: `t b 42.4`;
  - `SET_ZERO` on H: every value from 16.2 to 18.3 °C.
- **Other decodings.** A single `t a` command leaves the axis firmware blocked in
  an argument read, sending no status frames (:112–120). No in-limit move decodes,
  either from single commands or from the GUI's A+B pair.
- **Verification.** We confirmed every decoding above independently. We fed the
  terminal's exact byte encoding through a re-implementation of both parsers; the
  results match `docs/safety.md` G7.

**Symptom**

- Commanding a move drives pad A to its maximum setpoint. Setting a pad
  temperature can start homing motion or silently shift an axis zero.
- The swap is visible on screen before any command is sent. The pad temperatures
  read 2.99 °C, because axis status frames are decoded as temperatures
  (`terminal.py:566–567`), and the axis readout shows implausible positions.
- No acknowledgement ever arrives, so every axis command stalls for 60 s (KI-15).

**Effect on archived data.** No archived run shows the signature: no main-format
CSV contains a temperature between −50 °C and 15 °C. A run recorded with swapped
ports would contain temperature-derived "positions" and position-derived
"temperatures".

---

<a id="ki-04"></a>
## KI-04: A USB dropout ends the worker thread; logging continues with frozen values

**Severity:** High · **Component:** terminal (`AxisThread`, `HeatThread`, `LoggerThread`, `InterpreterThread`)

**Evidence**

- `ser.in_waiting` is evaluated in an `if` condition outside the inner `try`
  blocks: `terminal.py:465` versus :466–485 for the axis thread, and :555 versus
  :556–585 for the heater thread.
- When the device disappears, the exception leaves the `while` loop through the
  outer handler (:523–524, :612–613). The handler emits one console line and the
  thread ends. There is no reconnect path.
- The 60 s watchdog runs inside the loop that has just ended (:459–462).
- The logger keeps copying the last `state.pos` and `state.temp` values into new
  rows until logging is stopped (:414–430).
- The interpreter waits on `state.axis_ready` without a timeout (:731–747):
  - Dropout during a move: it waits at :746–747 for an acknowledgement that can no
    longer arrive.
  - Dropout while idle: it queues the next move and waits at :742–743 for a
    dequeue that no thread performs.
  - Either wait ends only with `exit bp` (:1281–1285).
- The controller finishes any move it has already received, so the phantom can
  come to rest at a pose the log never shows.

**Symptom**

- Axis link: the blueprint hangs at the next `move`, the status line freezes, and
  logging continues.
- Heater link: temperatures and stability flags freeze, while the blueprint
  continues normally.

**Effect on archived data.** A dropout leaves a structurally valid CSV. Its rows
after the dropout repeat the last received values, possibly an intermediate
position of an unfinished move. No archived run shows an unambiguous instance: a
frozen tail looks like an operator pause, and the console line was never
persisted. Long motion-free tails with unrecorded causes exist, for example
*2026-05-13 14:51:47* (see KI-15).

---

<a id="ki-05"></a>
## KI-05: Logged positions are commanded step counts; driver alarms are discarded and errors beyond the motor shaft are unobservable

**Severity:** High · **Component:** axis firmware, terminal, CSV format

**Evidence**

- **Positions are commanded counts.** The firmware reports
  `AccelStepper::currentPosition()` for H, V and R
  (`SURF_nanoAxis_v5.ino:162–164`): the number of step pulses issued, not a
  measured position. The terminal converts them with nominal factors
  (`terminal.py:476–478`).
- **The drivers close the loop on the motor shaft.**
  - The firmware header names CL57T drivers (:4). According to the hardware author
    they are closed-loop stepper drivers: each driver corrects lost steps against
    its motor encoder and asserts its ALM output when it cannot.
  - The encoder is read only inside the driver. Neither the firmware nor the
    terminal ever sees an encoder position.
  - The loop does not cover anything downstream of the motor shaft: lead-screw
    error, coupling compliance, gear backlash (KI-12) and linkage geometry.
  - The repository documents neither the motors and encoders nor the drivers'
    error thresholds (`hardware/bom.csv`, items 3–4).
- **Alarm information is transmitted, then discarded.**
  - Every telemetry frame carries a status byte holding the H and V ALM bits and
    the firmware's alarm state (`SURF_nanoAxis_v5.ino:166–172`), along with the
    controller's `millis()` (:161).
  - The terminal reads both and discards them (`terminal.py:469`, :473). The CSV
    header has no column for either (:405–410).
  - The pilot-format CSVs of 2025-12 and 2026-01 did record `Arduino_Time` and
    `Status_Bits`.
- **Alarms are not acted on during moves.** The firmware checks ALM only in the
  idle main loop (:273–275) and during homing (:185), never inside the move loop
  (:368–374). If a driver alarms mid-move, `currentPosition()` still reaches the
  target and `COMMAND_DONE` is sent (:377). See also `docs/safety.md` G4.
- **R has no alarm input.** Only `PIN_ALM_H` and `PIN_ALM_V` exist (:30, :33); the
  R pin set has none (:35).

**Symptom.** Two kinds of failure produce a log identical to a successful move: a
driver that could not hold position and raised an alarm, and any error downstream
of the motor shaft.

**Effect on archived data**

- **Every position is a commanded count.** This applies to every `Pos_H`, `Pos_V`
  and `Pos_R` value in every archived run.
- **Freedom from uncorrected step loss cannot be demonstrated.** The alarm bits
  that would show it for H and V were discarded, and R has none. This entry does
  not claim that steps were lost: the drivers correct ordinary step loss at the
  motor shaft.
- **Nothing between motor shaft and phantom is represented:** lead-screw and gear
  backlash (KI-12), compliance, thermal expansion, mounting errors.
- **Independent measurements** in this repository are limited to one dial-gauge
  session:
  - H: no measurable backlash, at most 5 µm
    (`docs/calibration/backlash-measurement-raw.txt:20–21`);
  - V: not measured;
  - R: see KI-12 and KI-13.
- `data/raw/2026-03-10/runs.csv:18` records a radiographic check of static
  extreme positions in the analysis repository. That check is outside this
  repository and is not assessed here.
- Whether a driver alarm occurred during any archived run cannot be determined.

---

<a id="ki-06"></a>
## KI-06: Axis reference (homing, zero) is neither enforced, verified nor recorded

**Severity:** High · **Component:** axis firmware, terminal, blueprints

**Evidence**

- `hAxisInitialized` and `vAxisInitialized` are declared
  (`SURF_nanoAxis_v5.ino:100–101`) but never used. `isTargetSafe()` checks
  initialisation only for R (:152).
  - H and V moves are accepted without homing.
  - Their limits (:55–64) then apply relative to wherever the carriage stood at the
    last counter reset.
- `HOME_AXIS` computes `success` (:384–390), ignores it, and always replies
  `COMMAND_DONE` (:400–401).
  - A homing run can time out (20 s, :198) or abort on a driver alarm (:185). It
    then skips `setCurrentPosition(home offset)` (:231), and the counter keeps an
    arbitrary value.
  - The PC still prints ">> Achse: Bewegung abgeschlossen." (`terminal.py:483`).
- R zero is whatever angle the phantom has when `h r` or `set r zero` is issued
  (:392–397, :420–424). There is no mechanical reference (README.md:104).
- Step counters are held in RAM and restart at 0 on every controller reset. The
  terminal opens both ports at every start (`terminal.py:450`, :545), which
  typically resets a Nano.
- Blueprints only ask the operator ("Sind alle Achsen gehomed …?", e.g.
  `blueprints/qa/ETsurface_easyQA_new.json:8`). The answer reaches the protocol
  only from 2026-08-06 onward (`terminal.py:712`). The controller's homing state
  is never queried.
- The firmware limits themselves changed between campaigns:
  - until 2026-02-19 (commit `c525676`): H ±35 mm and R ±45°;
  - from 2026-02-24 (commit `533a9bd`): H −45 … +25 mm and R −30 … +120°.

**Symptom.** A session that was never homed, or whose homing failed, runs normally
and logs coordinates relative to an arbitrary origin. The firmware soft limits
then do not protect the mechanical range.

**Effect on archived data**

- Positions are internally consistent within one controller session. However, no
  archived file shows whether that session was homed, whether homing succeeded,
  or where R zero was set. Absolute positions may therefore not be comparable
  across sessions or days.
- The R rejection in *2026-02-24 16:48:07* (KI-01) is consistent with R
  initialisation being lost between runs.
- Homing during logging shows up as excursions beyond the envelope. For example,
  *2026-02-17 17:08:46* reaches H = 40.91 mm and V = 62.5 mm.

---

<a id="ki-07"></a>
## KI-07: ExacTrac linkage file: unvalidated selection, non-atomic writes, swallowed failures

**Severity:** High · **Component:** terminal (QA mode: `QAConfigFile`, `load_blueprint`, `handle_etds_timestamp`)

**Evidence**

- Any JSON file can be selected as the config file. It is neither parsed nor
  validated on selection (`terminal.py:1323–1336`).
- Every append re-reads and rewrites the whole file (:184–192):
  - `open(path, "w")` truncates first, then writes (:179–182), with no temporary
    file, no `fsync` and no atomic rename.
  - `_load()` treats an empty file as an empty table (:176–177).
  - The whole table fits in one write buffer, so an interruption between
    truncation and close most likely leaves an empty file. The next append would
    then restart at key "1" and overwrite every earlier entry.
- A failed write is reduced to a console line and the measurement continues
  (:1457–1459). The protocol records the ETDS event with `config_key: null` and no
  error text (:1461–1466).
- `patch_surf_timestamp()` reads the file at logging start outside any `try`
  (:1519–1523). An invalid file therefore raises an unhandled exception in the Qt
  slot, visible only on stderr.

**Symptom.** A broken or wrong config file does not stop a QA session. The
operator types the ETDS timestamps, the dialog closes normally, and the only
feedback is a console line.

**Effect on archived data**

- **Eight timestamps lost on 2026-08-06.**
  - The config copy used that day was
    `firmware/measurement_pc/etds_qa_2026_config_copy.json` (removed during
    release preparation).
  - It was committed at 16:18:48 (commit `9a0adb1`) in the state still present in
    `1d19cc7`: 1,623 bytes, ending with a trailing comma after entry "8", i.e. not
    valid JSON. That was before the first QA run that selected it.
  - All eight `etds_timestamp` events of runs 16:37:03, 16:55:21, 17:33:50 and
    18:02:57 carry `config_key: null`.
  - The operator-entered timestamps 164356, 164743, 170015, 170312, 173610,
    173911, 180626 and 180934 survived only in the protocol files (the `_log.json`
    event lists and their `_log.txt` renderings).
  - They now appear as keys 13–20 of `data/etds_qa_2026_config.json`,
    reconstructed during release preparation.
  - The shape of the file suggests a manual edit rather than an interrupted write.
    The repository does not establish the cause.
- **Placeholder entries from a dry run.** On 2026-08-06, the simulated dry run
  (protocol 15:19:55, KI-02) appended two entries with ETDS timestamp "999999"
  (keys 9 and 10) to the file it had selected, `etds_qa_2026_config.json` on that
  machine. That file is not the archived table: the archived keys 9–12 belong to
  the two 2026-07-29 runs.
- **A blueprint selected as config file.** On 2026-08-21 the blueprint
  `ETD_QA_BasicPoP.json` was selected as the config file (protocol
  `ETD_QA_PoP_SingleCouchRotation_20260821_093044_log.json`). The blueprint that
  ran has no end-position prompt, so nothing was written. With one, key "1" would
  have been inserted into the blueprint.
- **Undocumented entries.** Entries 1–8 of the archived table match the committed
  copy. The source of entries 9–12 is not documented in this repository.

---

<a id="ki-08"></a>
## KI-08: `wait_steady` cannot confirm a temperature change, and its outcome is not recorded

**Severity:** High · **Component:** terminal (`HeatThread` stability, interpreter `heat` step)

**Evidence**

- **The history window is 120 s, not 20 s.** Stability requires a full
  120-sample history (`terminal.py:354–355`, :576) in which every sample lies
  within 0.2 °C of the current setpoint (:577–578). Samples arrive at the 1 Hz
  heater frame rate (`SURF_nanoHeating_v4.ino:116`), so a pad must stay in the
  band for at least 120 s. The comment at `terminal.py:353` says "20 Sek".
- **The history is not cleared on a setpoint change** (:588–592). Samples from
  before the change are judged against the new setpoint.
- **The wait budget equals the window.** The interpreter polls at most 120 times
  at 1 s intervals (:762–770). After any change larger than 0.2 °C, a genuine
  transition to stability cannot be observed within that budget.
- **The first poll reads a stale flag.** It happens immediately after queuing
  (:751–756, :762–768). At that moment the heater thread has not yet applied the
  new setpoint (it loops every 0.1 s, :611), and the next 1 Hz frame has not
  re-evaluated `stable` (:574–580). If the pads were stable at the previous
  setpoint, the step passes at once with "Temperatur stabil!" (:789–790).
- **The operator's answer is not recorded.** On timeout the operator is asked
  "Für Simulationszwecke ignorieren und Blueprint fortsetzen?" (:776–779). The
  answer is not written to the protocol; only `checkpoint` steps emit `log_event`
  (:712).
- In simulation, `stable` is forced true (:608–609).
- `wait_steady: true` is used by all eight blueprints in `blueprints/pop/` and by
  `blueprints/qa/ETsurface_easyQA_wcouch_T32.json` and `…_wcouch_T32_new.json`.

**Symptom.** In heated blueprints the step either passes instantly without
waiting, or always times out and the operator continues.

**Effect on archived data**

- The tool never verified thermal equilibrium at the start of a heated run, and
  the operator's decision is not recorded. This matters because the tracker export
  carries a thermal quality metric (`rmseThermal`, read in
  `matlab/ETDCombinedJSONCSVViewerApp.m:221`).
- By the terminal's own criterion, 13 blueprint runs with a 32 °C or 36 °C
  setpoint have at least one pad that is never flagged stable in any row. "(B)"
  means only pad B; otherwise both pads:
  - 2026-02-17 16:50:02 (B), 17:25:15 (B), 17:30:52, 17:38:17;
  - 2026-02-19 18:21:08;
  - 2026-02-24 16:16:39, 16:27:04, 16:48:07;
  - 2026-03-10 18:42:05 (B), 18:43:48;
  - 2026-07-15 14:19:09, 14:23:33;
  - 2026-08-06 16:55:55 (B).
- Some of these are far from their setpoint:
  - *2026-07-15 14:19:09* heats from 30.5 °C towards 36 °C during the run;
  - *2026-07-15 14:23:33* cools from about 35 °C towards 32 °C;
  - *2026-02-24 16:16:39* reads 33.6–34.2 °C against a 32 °C setpoint.
- In the 2026-03-10 campaign, the two runs listed belong to the warm-up
  experiment. `data/raw/2026-03-10/runs.csv:28–29` marks them as not used in the
  tracking evaluation.
- The `Stable_A` and `Stable_B` columns remain usable for post-hoc screening.
  Caveat: `Set_A` and `Set_B` may not be the controller's setpoint (KI-14).

---

<a id="ki-23"></a>
## KI-23: Linear axes never exceed about 5 mm/s, whatever speed is commanded

**Severity:** High · **Component:** axis firmware (step generation), blueprints · **Also described in:** `docs/safety.md` G9

**Evidence**

- **Commanded speeds.** Across all blueprints under `blueprints/`:
  - H: 20 mm/s for traverses (290 moves) and 50 mm/s for sync pulses (72 moves);
  - V: 20 mm/s (110 moves);
  - R: 0.5, 1, 2, 5, 10, 15 and 20 °/s.
- **What the firmware is asked for.** The terminal converts linear speeds into
  16 000 and 40 000 steps/s (`terminal.py:739`). The firmware caps linear speed
  at 40 000 steps/s (`SURF_nanoAxis_v5.ino:42`, :50, :316–317) and passes the value
  to `setMaxSpeed()` (:365).
- **What the firmware can deliver.**
  - Steps are generated by calling `AccelStepper::run()` in a blocking loop
    (:368–374).
  - AccelStepper documents about 4000 steps/s as the fastest reliable rate on a
    16 MHz Arduino (quoted in `docs/safety.md` G9). At 800 steps/mm (:39) that
    corresponds to 5 mm/s.
  - The 50 mm/s cap therefore never engages.
- **R stays below the ceiling.** R at 20 °/s needs only 323 steps/s (:40).

**Symptom**

- H and V moves take about 4 times longer than commanded at 20 mm/s, and about
  10 times longer at 50 mm/s.
- The "fast" sync pulses and the "normal" traverses run at the same speed.
- R runs at its commanded speed.

**Effect on archived data**

- **Linear speed.** We fitted a straight line to the interior of every H and V
  motion segment in all runs from 2026-02-24 onward that log mid-move positions.
  - Over 1,094 segments the median speed is 5.08 mm/s (5th–95th percentile
    4.88–5.18 mm/s, maximum 5.55 mm/s).
  - Per-campaign medians lie between 5.02 and 5.15 mm/s.
  - In the 2026-03-10 campaign the medians are 5.07 mm/s on H and 5.12 mm/s on V.
- **Rotary speed.** R segments cluster at the commanded values of 0.5, 1, 2, 5,
  10, 15 and 20 °/s.
- **Consequences for analysis.**
  - Every linear move in the archive ran at about 5.1 mm/s, whether it was
    commanded at 20 or at 50 mm/s.
  - Any analysis, figure or caption that assumes the blueprint speeds for H or V
    is wrong.
  - Speed-dependent statements for the linear axes rest on a single speed.
  - The logged positions show the realised motion, so velocities must be taken
    from the telemetry, never from the blueprint.
- **Earlier runs.** Runs before 2026-02-24 cannot show their realised speed
  (KI-11). Their firmware did less work per step-loop iteration, so their ceiling
  is not known.

---

<a id="ki-09"></a>
## KI-09: No persisted event log or run provenance

**Severity:** High · **Component:** terminal, CSV and protocol formats

**Evidence**

- **Diagnostics go only to the on-screen console** (`terminal.py:1128–1133`):
  - simulation fallback (:455, :551);
  - watchdog releases (:462);
  - acknowledgements (:483);
  - send errors (:513, :600);
  - thread termination (:524, :613);
  - temperature timeouts (:773);
  - blueprint load errors (:1311);
  - config write failures (:1459);
  - zero and backlash commands (:1265–1295).
- **The telemetry CSV carries no metadata:** a fixed ten-column header and nothing
  else (:405–410).
- **The protocol records little provenance.** `MeasurementLog` (:210–335) exists
  only from commit `9338502` (2026-08-06). It records the blueprint file name but
  not its content or hash. It also does not record:
  - the terminal or firmware version;
  - port names or connection state;
  - simulation;
  - homing and zero state;
  - backlash state;
  - driver status;
  - manual console commands or button presses.
- **Blueprints were edited in place.** For example, `ETD_QA_BasicPoP.json`
  commanded ±30 mm and ±30° in commit `3f922f5` (2026-02-16), and ±10 mm and ±5°
  from `c525676` (2026-02-19).
- **Logging prefixes are shared.** 16 blueprints (every `SingleCouchRotation*`
  variant in `blueprints/pop/` and `blueprints/heating-off/`) log with the prefix
  `ETD_QA_PoP_SingleCouchOrientation`, and four blueprints share
  `ETsurface_easyQA`.
- **Firmware limits changed between campaigns** (KI-06).

**Symptom.** After a session, the files do not show what the terminal reported,
which blueprint version ran, or which firmware and settings were active.

**Effect on archived data**

- For every run before 2026-08-06, the blueprint has to be inferred from the file
  name prefix, the motion pattern and external paper protocols. Such inferences can
  conflict: for run 23, `data/raw/2026-03-10/runs.csv:27–29` records that the
  paper protocol names a different blueprint than the one the file matches.
- The absence of an error in the archive is not evidence that none occurred.
  KI-01, KI-02, KI-03, KI-04, KI-07, KI-08, KI-15 and KI-23 are all silent in the
  files.

---

<a id="ki-10"></a>
## KI-10: Sampling rate, timestamps and latency

**Severity:** Medium · **Component:** terminal (`LoggerThread`, workers), CSV format

**Evidence**

- **Sleep after work.** The logger sleeps a fixed 0.1 s after each write
  (`terminal.py:379`, :428–430). The period is therefore 0.1 s plus loop, lock,
  write and flush time, not a fixed-rate schedule.
- **`Time_Sec` is the PC read time.** It is taken from the PC clock at the top of
  each iteration (:415). The row then copies whatever the workers last parsed
  (:416–426).
- **Positions lag their timestamps.**
  - Axis frames are sent every 50 ms (`SURF_nanoAxis_v5.ino:96`, :282, :370–373).
  - The PC parses at most one message per 10 ms loop iteration, and only once
    18 bytes are buffered (`terminal.py:465`, :521).
  - A logged position is thus up to one frame period old, plus USB and polling
    latency. At the realised linear speed of about 5.1 mm/s (KI-23), 50 ms is
    about 0.25 mm; at R's fastest archived speed of 20 °/s, it is 1°.
- **Controller clocks are discarded** (:469, :561).
- **Temperatures are repeated and late.** They arrive at 1 Hz
  (`SURF_nanoHeating_v4.ino:116`) and are repeated in every row, without marking
  which rows are fresh. Each value is itself about one conversion cycle old: it is
  read before the next conversion is requested (:117–123).
- **The only absolute time reference has one-second resolution.** It is the start
  time in the file name, formatted `%H%M%S` from the PC wall clock
  (`terminal.py:1487`, :1490, :1514), i.e. truncated to whole seconds. No
  synchronisation with the tracking workstation's clock is recorded, and ETDS
  timestamps are typed by hand (:975–983).

**Symptom.** A nominal 10 Hz log runs at about 9.3 Hz with irregular intervals and
occasional gaps. Positions during motion lag their timestamps.

**Effect on archived data**

- **Rates.** Across the 103 main-format runs from 2026-02-24 onward, mean rates
  are 9.13–9.78 Hz (median 9.26 Hz; 95 of 103 runs between 9.15 and 9.35 Hz).
  Median intervals are 0.101–0.109 s. The largest single gap is 1.94 s
  (*2026-07-15 14:29:24*).
- **February pilot.** The pilot runs, recorded with terminal versions up to
  `b732943`, logged at 0.5 s intervals (≈1.97 Hz).
- **Static versus dynamic.** Static dwell positions are unaffected. Dynamic
  comparisons (velocity, lag, tracking during motion) must allow for tens of
  milliseconds of timestamp uncertainty and non-uniform sampling, and must not
  assume 10 Hz.
- **Absolute alignment.** Wall-clock alignment with tracker data carries up to 1 s
  of truncation plus an unknown clock offset. The analysis repository instead
  aligns runs on short H excursions within the blueprints
  (`data/raw/2026-03-10/runs.csv:40`). The precision of that alignment is bounded
  by the effects above.

---

<a id="ki-11"></a>
## KI-11: Firmware before 2026-02-24 reported no positions during moves

**Severity:** Medium · **Component:** axis firmware (historical; resolved in current firmware) · **Status:** affects archived data only

**Evidence**

- In the axis firmware at commits `b732943` (2026-02-18) and `c525676`
  (2026-02-19), the move loop only calls `run()`. It carries the comment "Hier
  optional: weiterhin LOG_DATA senden, falls gewünscht"
  (`firmware/arduino/src/SURF_nanoAxis_v1.2/SURF_nanoAxis_v1.2.ino` in those
  commits).
- `sendStatusLog()` inside the loop first appears in commit `503efe3`
  (2026-02-24 16:37). It is present today at `SURF_nanoAxis_v5.ino:370–373`.

**Symptom.** During every move the log keeps showing the start position. The
target appears only after the move has finished.

**Effect on archived data**

- Seven runs contain only jumps between targets, with no intermediate positions:
  - 2026-02-17 16:50:02, 17:38:17 and 18:36:45 (`_firsttry`);
  - 2026-02-19 17:38:57 (`_pop1`), 18:00:23 (`_pop1_first_half`) and 18:21:08
    (`_pop3_repeat`);
  - 2026-02-24 16:16:39.
- In these runs, motion-phase positions are wrong by up to the full move
  amplitude: 20 mm or 10° for ±10 mm / ±5° moves, 60 mm or 60° for the ±30 moves
  of 2026-02-17.
- The onset of motion is not visible; only arrival is. Dwell positions are
  unaffected.
- The run at 16:27:04 on 2026-02-24 already contains intermediate positions, ten
  minutes before the change was committed.

**For reuse.** Exclude
the motion phases of these runs. Do not reconstruct them from blueprint speeds:
the commanded linear speeds were not realised (KI-23), and the speed ceiling of
this older firmware is unknown.

---

<a id="ki-12"></a>
## KI-12: Backlash compensation: state unrecorded, correction hidden

**Severity:** Medium · **Component:** axis firmware, terminal console

**Evidence**

- **Off by default, R only.** `backlash_on` defaults to false
  (`SURF_nanoAxis_v5.ino:45`). Only R has a non-zero correction: 4 steps ≈ 0.248°
  (:46).
- **Console only, lost on reset.** It is switched only by the console commands
  `backlash on` / `backlash off` (`terminal.py:1290–1295`;
  `SURF_nanoAxis_v5.ino:405–410`).
  The blueprint DSL has no equivalent (`terminal.py:657–830`). The flag is held in
  RAM and cleared by every controller reset.
- **The correction is hidden.** On a detected direction reversal, the firmware
  moves the 4 steps and then restores the previous count with
  `setCurrentPosition(current_pos)` (`SURF_nanoAxis_v5.ino:343–356`). The
  correction never appears in `currentPosition()` or in the log, and no status
  frames are sent while it runs (:349–351).
- **Stale direction after toggling.** `last_dir` is updated only while
  compensation is on (:358–360). After switching compensation off, moving, and
  switching it on again, the first move is judged against a stale direction. The
  result is a spurious or a missed 4-step correction.
- **One dial-gauge session.** The value comes from a single session on 2026-03-09
  and 2026-03-10.
  - Readings: 5–6 divisions (0.05–0.06 mm) at a 15 mm lever arm, i.e. 0.19–0.23°
    or 3.1–3.7 steps (`docs/calibration/backlash-measurement-raw.txt:24–39`,
    `rotation_calibration.ino:12–13`).
  - One division (0.01 mm) at that lever arm is about 0.04°, or 0.6 steps.
  - The correction assumes a constant slack, and that the load never holds the
    gear against one flank. Neither was characterised.
- The code was added in commit `76beb9d` (2026-03-10 15:02).

**Symptom.** Two runs with identical logs can differ physically by about 0.25° in
R after every reversal, depending on a console command issued earlier in the
session.

**Effect on archived data**

- After every reversal, the logged R angle carries an ambiguity of the order of
  the backlash (≈0.2–0.25°), because it is unknown whether compensation was
  active.
- Campaigns before 2026-03-10 cannot have used compensation, provided the flashed
  firmware matched the repository. The repository cannot confirm that.
- For 2026-03-10, the paper-protocol transcription at
  `data/raw/2026-03-10/runs.csv:15` (run 10) reads "backlash corrected but a
  rotation offset remained (5 deg vs 4.7 deg)". This suggests compensation was
  switched on during that campaign. No acquisition file shows when, or whether it
  stayed on for later runs and campaigns.

---

<a id="ki-13"></a>
## KI-13: Rotation scale factor: inconsistent, undocumented, truncated

**Severity:** Medium · **Component:** terminal, axis firmware, calibration sketch

**Evidence**

- **Two different values.**
  - `STEPS_PER_DEG = 16.156` in the terminal (`terminal.py:69`);
  - `STEPS_PER_DEG_R = 16.156f` in the firmware (`SURF_nanoAxis_v5.ino:40`);
  - `STEPS_PER_DEGREE = 16.1599` in the calibration sketch
    (`rotation_calibration.ino:9`), under the heading "KALIBRIERTE WERTE" (:8).
- **No calibration record.** The repository contains no procedure, raw readings,
  date or uncertainty for either value. `firmware/README.md:10` describes the
  sketch as the tool used to determine `STEPS_PER_DEG`, but the sketch only
  executes moves and reports nothing.
- **Truncation.** Targets are converted with `int(target * factor)`, which
  truncates toward zero (`terminal.py:739`, :1223); speeds likewise (:739). One R
  step is 1/16.156 ≈ 0.0619°.

**Symptom**

- Commanded and logged angles differ by up to one step.
- The two constants differ by 0.024 %, i.e. 0.47 steps (0.03°) over 120°.

**Effect on archived data**

- **Truncation is visible in the archive:** 1° → 0.9903°, 2° → 1.9807°,
  5° → 4.9517°, 30° → 29.958°, 91° → 90.988°, 92° → 91.978°. The 1°, 2°, 91° and
  92° values appear in the `R_pos` column of
  `2026-07-15/ETsurface_easyQA_wcouch_T32_20260715_165141_QA.csv`. The 5° and 30°
  values are the `Pos_R` extremes of, for example, *2026-03-10 16:33:25* and
  *2026-03-25 17:55:23*.
- **Logged versus nominal angles.**
  - Analyses based on logged angles agree with the step count.
  - Analyses based on blueprint nominal angles carry a bias toward zero of up to
    one step. At the 1–5° amplitudes used, that is about 1 % of the amplitude.
- **Resolution floor.** The smallest R increment that can be commanded is one
  step (0.062°). A 0.1° command produces one step, and any fraction of a step is
  silently dropped.
- **Unknown absolute scale.** Because the factor has no documented calibration,
  the absolute scale error of every archived R value is unknown. It may exceed
  both effects above.
- **H and V** (800 steps/mm) are affected by truncation only at the 1.25 µm level.

---

<a id="ki-14"></a>
## KI-14: Logged heater state is a PC-side assumption

**Severity:** Medium · **Component:** terminal (`SystemState`, `HeatThread`), heater firmware, protocol

**Evidence**

- **The initial setpoints disagree.** The terminal starts with setpoint 25.0 °C
  for both pads (`terminal.py:349`) and never sends it on connect (:545–549). The
  heater firmware starts at 0.0 °C, i.e. with the pads unpowered
  (`SURF_nanoHeating_v4.ino:41–42`).
- **The setpoint is never read back.** The heater frame contains no setpoint
  (:125–128). The PC updates its own copy when a command is dequeued, before and
  regardless of a successful send (`terminal.py:589–600`).
- **The CSV logs the PC's belief.** `Set_A` and `Set_B` (:424) are that PC copy,
  and `Stable_A` and `Stable_B` (:425) are judged against it.
- **The heating condition is declared, not measured.** `heatingpads` in the
  protocol and config (:1357, :1444) comes from the blueprint name, a blueprint
  field or operator input (:137–153, :914, :940), never from the controller.
- **Sensor dropouts are logged as temperatures.** A disconnected DS18B20 reads
  −127 °C. The firmware then switches that pad off (`SURF_nanoHeating_v4.ino:61–64`)
  but still transmits the value. The PC applies the outer-surface calibration and
  logs −105.56 °C without a flag (`terminal.py:62–64`, :566–567).
- **Blueprint setpoints are not range-checked** (:750–754). The GUI and console
  enforce 10–50 °C (:1139, :1258), while the firmware only clamps to 0–65 °C
  (`SURF_nanoHeating_v4.ino:143`).

**Symptom**

- In a session without a heat command, the CSV shows `Set_A = Set_B = 25.0` while
  the pads are unpowered.
- The protocol's heating condition can disagree with what was commanded.

**Effect on archived data**

- **`Set = 25.0` does not mean 25 °C was commanded.** All heating-off runs of
  2026-03-10 read 22.97–23.08 °C, which is consistent with unpowered pads.
- **An "OFF" run was regulated to 24 °C.** *2026-08-06 18:03:21* is labelled
  `heatingpads: "OFF"` in its protocol and in `data/etds_qa_2026_config.json`
  (keys 19–20). Yet its CSV shows `Set_A = Set_B = 24.0` from the first row: a
  24 °C command had been issued earlier in the session.
- **Sentinel rows.** 48 rows in five files contain −105.56 °C:
  `2026-02-pilot/ETD_QA_BasicPoP_20260217_170846.csv` (2 rows) and the four
  2026-05-13 runs (46 rows). Averages over these files are corrupted unless the
  sentinel is filtered.

---

<a id="ki-15"></a>
## KI-15: Command handshake: no framing, no command identity, timeout treated as success

**Severity:** Medium · **Component:** terminal (`AxisThread`, interpreter), axis firmware

**Evidence**

- **No framing.** The byte stream has no sync pattern, no length and no checksum
  (`SURF_nanoAxis_v5.ino:159–173`, :377).
  - The PC takes any byte equal to 10 as a frame header and any byte equal to 4 as
    an acknowledgement (`terminal.py:467–483`). After a misaligned read, a data
    byte can be mistaken for either.
  - A read error discards the whole input buffer, including any pending
    acknowledgement (:484–485).
- **No command identity.** `COMMAND_DONE` does not say which command it answers.
  The PC assigns it to whatever command it believes is outstanding.
- **Unanswered commands.**
  - In alarm state, the firmware drops MOVE_AXIS and HOME_AXIS without replying
    (`SURF_nanoAxis_v5.ino:301–305`).
  - HELLO (:308) and unknown opcodes are not answered either; for STOP_ALL see
    KI-03.
- **Timeout counts as success.** The watchdog marks any unanswered command
  "ready" after 60 s (`terminal.py:459–462`). The interpreter cannot tell this
  from completion and continues (:746–747).
- **Long moves desynchronise the handshake.** For a move longer than 60 s, the
  watchdog releases while the axis is still moving:
  - the next command is sent early;
  - the blocking firmware executes it after the current move;
  - every later acknowledgement is then off by one.

  The longest blueprint move is 20 s (10° at 0.5°/s in
  `ETD_QA_PoP_SingleCouchRotation_RvarySpeed.json`), so blueprints are unaffected
  so far, but slow manual moves can trigger it.
- **Race in the interpreter wait.** The interpreter first waits for `axis_ready`
  to become false (:742–743), then for it to become true (:746–747). If the whole
  dequeue–send–acknowledge cycle completes between two 10 ms polls, it waits
  forever. A zero-distance move, which the firmware acknowledges immediately, is
  the most likely trigger.
- **Unbounded reads in the firmware.** Command arguments are read with busy-waits
  that never time out (`SURF_nanoAxis_v5.ino:112–120`). A truncated command stalls
  the controller, including its status frames.

**Symptom.** Occasional stalls of exactly 60 s, blueprint steps running while the
phantom is still moving, and hangs without an error message.

**Effect on archived data**

- ***2026-05-13 14:51:47*** shows the watchdog signature:
  - H → 5 mm starts at t = 12.25 s and ends at 13.56 s.
  - The next motion, H → 0, starts at 72.31 s, i.e. 60.06 s after the previous
    command, although the blueprint separates the two moves by a 2 s delay.
  - The run then shows no motion for its remaining 682 s.
  - The PC evidently never registered the acknowledgement. The cause cannot be
    reconstructed (KI-09).
- The only other 60 s spacing between motion starts in the archive
  (*2026-08-06 16:55:55*) coincides with a logged operator prompt.
- No QA input in any `_QA.csv` falls during motion, so no off-by-one sequence was
  found. Only runs from 2026-05-13 onward have QA input timestamps.

---

<a id="ki-16"></a>
## KI-16: Serial ports hard-coded; output paths relative to the working directory

**Severity:** Medium · **Component:** terminal

**Evidence**

- **Fixed ports.** `AXIS_PORT` and `HEAT_PORT` are fixed per platform at import
  time (`terminal.py:27–40`): `COM3`/`COM4` on Windows, `/dev/cu.usbserial-120`
  and `-140` elsewhere.
- **No override.** There is no command-line option, environment variable or
  config file. The entry points pass no arguments
  (`software/surf_terminal/__main__.py:1–4`, `pyproject.toml:21–22`).
- **Unused port detection.** `serial.tools.list_ports` is imported (:24) but never
  used. Automatic port detection was added and removed twice: commits `4470288` and
  `d687cd4` (2026-01-28), and `d74cb1c` and `965c5e2` (2026-02-24).
- **Relative output paths.** Every output is written relative to the process
  working directory: telemetry (:396), `_QA.csv` (:1494), protocols (:1347) and
  plots (`data/plot_<timestamp>.png`, :1180–1182).

**Symptom**

- On another machine, or on the laptop after a USB device comes back under a
  different COM number, the terminal opens no controller and falls back to
  simulation (KI-02).
- If the two port names end up exchanged, each controller receives the other's
  commands (KI-22).
- Started from a different directory, it writes a separate `data/` tree.

**Effect on archived data**

- The archived campaigns were written under `firmware/measurement_pc/data/` (git
  history) and moved to `data/raw/` during release preparation.
- Both simulated dry runs of 2026-08 (KI-02) ran on a non-Windows machine, where
  these device names depend on the physical USB socket. A port mismatch is
  consistent with, but not proven as, their cause.

---

<a id="ki-17"></a>
## KI-17: `_QA.csv` side files: stale paths, silent input loss, ambiguous columns

**Severity:** Medium · **Component:** terminal (QA input)

**Evidence**

- **Stale output path.** `qa_csv_filepath` and `measurement_start_ref` are set at
  logging start (`terminal.py:1155`, :1488, :1494). They are initialised once
  (:1021) and never reset. `handle_qa_input` appends to whatever path is stored
  (:1538–1555). Three ways this misfiles or loses QA values:
  - **Logging already running.** The blueprint's `logging start` is then ignored
    (:1484), e.g. after the GUI button (:1148–1166), which sets neither variable.
    The QA rows go into the previous blueprint run's `_QA.csv`, with `Time_Sec`
    relative to the manual recording. `surf_timestamp` stays empty, so config
    entries get no CSV link (:1446).
  - **`qa_input` placed before `logging start`.** The rows go into the previous
    run's file in the same way.
  - **No blueprint logging yet in the session.** QA values reach only the protocol
    (:1558–1562), which exists only from 2026-08-06 onward.
- **Silent input loss.** Invalid numeric input (e.g. "1,2.3") silently becomes an
  empty cell (:879–883).
- **Ambiguous columns.**
  - In `surface_tracking` mode, the same x/y/z values are written to both the
    `Sphere_*` and the `Surf_*` columns (:1549–1553).
  - `both` mode collects only one x/y/z set (:855–857).
- **Wrong file in the stop event.** The protocol's `logging stop` event records the
  `_QA.csv` path, not the telemetry file (:1527).

**Symptom.** QA values can land in the wrong file or vanish without a warning, and
blank cells are ambiguous.

**Effect on archived data**

- **No misfiled rows found.** No archived QA row lies outside its own run's time
  span, and no current blueprint places `qa_input` before `logging start`.
- **Ambiguous blank cells.** Blank cells exist, and it cannot be determined whether
  they were left empty on purpose or rejected as invalid:
  - `2026-07-15/ETsurface_easyQA_20260715_134010_QA.csv`: `0_Referenz` entirely
    blank, and three rows with only `Sphere_X`;
  - `2026-07-15/ETsurface_easyQA_wcouch_20260715_153326_QA.csv`: `2_zeroposition`;
  - `2026-05-13/ETsurface_easyQA_20260513_151302_QA.csv`: `1_minVerschub`,
    `Sphere_Z`.
- **`surface_tracking` rows.** Only `blueprints/qa/ETsurface_easyQA_draft*.json`
  use that mode, and no archived `_QA.csv` contains such a row.

---

<a id="ki-18"></a>
## KI-18: Blueprints are decoded with the platform default encoding

**Severity:** Medium · **Component:** terminal

**Evidence**

- **Blueprint load.** Blueprints are opened with `open(file_name, 'r')`, without
  `encoding` (`terminal.py:1308`).
  - On Windows, the default is the ANSI code page (cp1252 on a German
    installation), unless Python's UTF-8 mode is active. PEP 686 makes UTF-8 mode
    the default only from Python 3.15.
  - The blueprints are UTF-8, with umlauts and "°" in `name` and `msg`. They decode
    without error into mojibake.
  - A few byte values are undefined in cp1252; they make the load fail with a
    console-only message (:1310–1312).
- **CSV writers.** The CSV writers omit `encoding` as well (:402, :1498, :1544).
- **Protocol writers.** The protocol writers use UTF-8 (:264, :267), so the
  mangled strings were stored faithfully as mojibake.

**Symptom**

- Prompts appear garbled on the measurement laptop ("fÃ¼r", "0Â°").
- Protocol files contain double-encoded text.
- A non-ASCII `prefix` or `point_id` would produce platform-dependent file names
  and cell contents.

**Effect on archived data**

- **Six protocols with mojibake.** In commit `1d19cc7`, six protocol pairs of
  2026-08-06 contain "fÃ¼r", "0Â°" and "mÃ¼ssen" in `blueprint_name` and `msg`.
  Their blueprint load times are 16:27:53, 16:37:03, 16:55:21, 17:24:22, 17:33:50
  and 18:02:57. The four of them that record a file path use Windows separators.
  The one protocol of that day with POSIX separators (15:19:55) is clean.
- **Repaired copies.** The mojibake was repaired during release preparation
  (CHANGELOG.md:41). The archived protocols therefore differ from the originals in
  this respect only.
- **Numeric data unaffected.** Every point ID, mode and prefix in the blueprints is
  ASCII, and the main-format telemetry and `_QA.csv` files contain only ASCII.

---

<a id="ki-19"></a>
## KI-19: `closeEvent` calls `QThread` methods on a `threading.Thread`

**Severity:** Low · **Component:** terminal

**Evidence**

- `LoggerThread` derives from `threading.Thread` (`terminal.py:378`), which has no
  `isRunning()` or `wait()`.
- `closeEvent` calls both on every thread in its list (:1588–1591).
- The logger joins that list as soon as logging has run once in the session
  (:1582–1583), because `logger_thread` is never reset.

**Symptom**

- Closing the window after any logging raises `AttributeError` inside
  `closeEvent`.
- The interpreter thread comes after the logger in the list (:1585–1586) and is
  never stopped. If a blueprint is still running, Qt destroys a running `QThread`
  at exit.

**Effect on archived data**

- None on completed runs.
- If the window is closed while logging, the telemetry file ends at its last
  flushed row (:429). No plot is saved, and the protocol gets neither a
  `logging stop` event nor an end time.
- None of the archived protocols shows that pattern: every protocol with a
  `logging start` event also has a `logging stop` event.

---

<a id="ki-20"></a>
## KI-20: PI update: unreachable integral reset; comment disagrees with code

**Severity:** Low · **Component:** heater firmware

**Evidence**

- **Duplicated block.** `updateHeater()` contains a duplicated block
  (`SURF_nanoHeating_v4.ino:60–99`):
  - an outer `if (fabs(error) < 10.0)` (:69) encloses a redeclared `error` (:72)
    and an inner `if` with the same condition (:74);
  - so the inner `else { h.integral = 0; }` (:86–88) can never run;
  - outside the ±10 °C window the integral keeps its previous value instead of
    being reset;
  - the duty cycle is computed a second time after the block (:94–95), from an
    identical `error`.
- **Comment versus code.** The header comment states `Ki=0.005` (:3); the
  constant is `KI = 0.0025f` (:28).
- **Unused constant.** `HEATING_WINDOW` (:26) is declared and never used.

**Symptom**

- After a setpoint step larger than 10 °C, a stale integral carries into the
  approach. It is bounded by `MAX_I` = 0.25 duty (:29).
- On heating steps this can add overshoot.
- On cooling steps it drains within seconds, because negative errors are weighted
  by a factor of 5 (:77–79).

**Effect on archived data**

- Temperatures are measured values and remain valid.
- Warm-up behaviour differs from the evident design intent. This may contribute to
  the overshoot and slow settling seen under KI-08, but cannot be separated from
  other causes.

---

<a id="ki-21"></a>
## KI-21: Misleading comments and console messages

**Severity:** Low · **Component:** axis and heater firmware, terminal, calibration notes

**Evidence**

- **Endstop polarity.** The firmware comment says the switches are active-low with
  "LOW = Gedrückt" (`SURF_nanoAxis_v5.ino:125–127`), and the header says
  "ActiveLow Endstops" (:5).
  - The code treats HIGH as triggered (:127). That is correct for normally closed
    switches to ground with `INPUT_PULLUP`, which is what the README describes
    (README.md:102–103).
  - Changing the code to match the comment would invert endstop detection during
    homing.
- **Stability window.** The comment "20 Sek" (`terminal.py:353`) contradicts the
  actual 120 s window (KI-08).
- **Simulation flag.** The comment "Auf False setzen, wenn Hardware angeschlossen
  ist" on `SIMULATION_MODE` (:67) implies that the flag decides simulation. The
  automatic fallback ignores it (KI-02).
- **Zero commands.** `set h zero` and `set v zero` log "Setze aktuelle
  R-Position als 0", and their comments say "2 entspricht AXIS_R" (:1268–1273).
- **Heater protocol.** The heater header claims a "Robustes binäres Protokoll
  (Handshake-kompatibel)" (`SURF_nanoHeating_v4.ino:5`), but the heater protocol
  has no acknowledgement.
- **Backlash note.** The notes read "6mm"
  (`docs/calibration/backlash-measurement-raw.txt:36`). The readings (:27–32) and
  the sketch comment (`rotation_calibration.ino:12`) correspond to 0.06 mm.

**Symptom**

- Maintainers and operators are misled.
- The endstop comment in particular invites a change that would break homing.

**Effect on archived data.** None directly.

---

## Archived runs with specific findings

The table lists every archived file for which a specific finding exists. Some
issues apply to entire classes of data and are not repeated per row:

- every run: KI-05, KI-06, KI-10;
- every linear move: KI-23;
- R data: KI-12, KI-13;
- heater columns: KI-14.

All paths are relative to `data/raw/`.

| File(s) | Finding | Issue |
|---|---|---|
| `2025-12-pilot/*`, `2026-01-pilot/*` (12 pilot-format CSVs) | Written by superseded terminals and firmware, and not otherwise assessed here. `manual_final_h_0-10.csv` and `qa_log_20260126_103910.csv` contain concurrent two-axis motion (V+R and H+V). | — |
| `2026-02-pilot/ETD_QA_BasicPoP_20260217_165002.csv` | No mid-move positions; pad B never stable | KI-11, KI-08 |
| `2026-02-pilot/ETD_QA_BasicPoP_20260217_170846.csv` | Homing during logging (H 40.91 mm, V 62.5 mm); 2 sentinel rows | KI-06, KI-14 |
| `2026-02-pilot/ETD_QA_BasicPoP_20260217_172515.csv`, `…_173052.csv` | No motion with a live heater, cause undetermined; pad B / both pads never stable | KI-02, KI-08 |
| `2026-02-pilot/ETD_QA_BasicPoP_20260217_173817.csv` | No mid-move positions; pads never stable | KI-11, KI-08 |
| `2026-02-pilot/ETD_QA_BasicPoP_20260217_183645_firsttry.csv` | No mid-move positions | KI-11 |
| `2026-02-pilot/ETD_QA_BasicPoP_20260219_172643.csv` | No motion with a live heater, cause undetermined | KI-02 |
| `2026-02-pilot/ETD_QA_BasicPoP_20260219_173857_pop1.csv`, `…_180023_pop1_first_half.csv` | No mid-move positions | KI-11 |
| `2026-02-pilot/ETD_QA_BasicPoP_20260219_182108_pop3_repeat.csv` | No mid-move positions; pads never stable | KI-11, KI-08 |
| `2026-02-24/ETD_QA_PoP_SingleCouchOrientation_20260224_161639.csv` | No mid-move positions; pads never stable (33.6–34.2 °C at a 32 °C setpoint) | KI-11, KI-08 |
| `2026-02-24/ETD_QA_PoP_SingleCouchOrientation_20260224_162704.csv` | Pads never stable | KI-08 |
| `2026-02-24/ETD_QA_PoP_SingleCouchOrientation_20260224_164807.csv` | Four R moves acknowledged without motion; pads never stable | KI-01, KI-08 |
| `2026-03-10/ETD_QA_PoP_SingleCouchOrientation_20260310_152831.csv` | Heater simulated; axis state undetermined | KI-02 |
| `2026-03-10/ETD_QA_PoP_SingleCouchOrientation_20260310_184205.csv`, `…_184348.csv` | Pad B / both pads never stable (warm-up experiment, not used in the evaluation) | KI-08 |
| `2026-05-13/ETsurface_easyQA_20260513_144731.csv`, `…_145147.csv`, `…_150617.csv`, `…_151302.csv` | 46 sentinel rows in total | KI-14 |
| `2026-05-13/ETsurface_easyQA_20260513_145147.csv` | 60.06 s watchdog stall, then 682 s without motion | KI-15 |
| `2026-05-13/ETsurface_easyQA_20260513_151302_QA.csv` | Blank QA cell | KI-17 |
| `2026-07-15/ETD_QA_BasicPoP_20260715_141909.csv` | Heats from 30.5 °C towards 36 °C during the run | KI-08 |
| `2026-07-15/ETD_QA_PoP_SingleCouchOrientation_20260715_142333.csv` | Cools from about 35 °C towards 32 °C during the run | KI-08 |
| `2026-07-15/ETsurface_easyQA_20260715_134010_QA.csv`, `2026-07-15/ETsurface_easyQA_wcouch_20260715_153326_QA.csv` | Blank QA cells | KI-17 |
| `2026-08-06/ETsurface_easyQA_20260806_152005.csv`, `…_152005_QA.csv`, `ETsurface_easyQA_new_20260806_151955_log.*` | Simulated dry run; it wrote placeholder entries into another config file | KI-02, KI-07 |
| `2026-08-06/ETsurface_easyQA_20260806_163851*`, `…_165555*`, `…_173403*`, `…_180321*` and their protocols | ETDS timestamps never reached the config file (keys 13–20 were reconstructed) | KI-07 |
| `2026-08-06/ETsurface_easyQA_20260806_165555.csv` | Pad B never stable | KI-08 |
| `2026-08-06/ETsurface_easyQA_20260806_180321.csv` | Labelled `heatingpads: "OFF"`, but the setpoint was 24 °C | KI-14 |
| `2026-08-06/*_log.json`, `*_log.txt` (six pairs) | Mojibake, repaired during release preparation | KI-18 |
| `2026-08-21/` (all four files) | Simulated run; a blueprint was selected as the config file | KI-02, KI-07 |
