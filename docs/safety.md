# Safety

This document describes the hazards of the SURF Test Unit **as built and as its
firmware and software behave at this commit**. It lists the protections that
exist and, just as plainly, the gaps in them. It is **not a risk assessment**:
none has been carried out (see [`disclaimer.md`](disclaimer.md)). Software
defects that are not safety-relevant are catalogued in
[`known-issues.md`](known-issues.md).

**Citations.** `axis:<line>` refers to
[`firmware/axis/SURF_nanoAxis_v5/SURF_nanoAxis_v5.ino`](../firmware/axis/SURF_nanoAxis_v5/SURF_nanoAxis_v5.ino),
`heat:<line>` to
[`firmware/heating/SURF_nanoHeating_v4/SURF_nanoHeating_v4.ino`](../firmware/heating/SURF_nanoHeating_v4/SURF_nanoHeating_v4.ino),
and `terminal.py:<line>` to
[`software/surf_terminal/terminal.py`](../software/surf_terminal/terminal.py).
Library behaviour is cited from the library versions pinned in
`.github/workflows/arduino-build.yml:31-37` (AccelStepper 1.64, OneWire 2.3.8,
DallasTemperature 4.0.6). `1d19cc7:<path>:<line>` refers to a superseded file
retained in git history (`git show 1d19cc7:<path>`). German source strings are
quoted in English translation. Pin-level detail is in
[`hardware/pinout.md`](../hardware/pinout.md).

---

## 1. Read this first

- **There is no hardware emergency stop.** The red "STOP ALL" button is a serial
  command. It cannot reach the controller while a move is running, has no
  effect when it does arrive, and does not stop a running blueprint
  ([G1](#g1-there-is-no-emergency-stop-stop-all-is-not-one)). Today the only
  way to stop a move in progress is to remove power from the drivers.
- **The rotation axis has no endstop and no physical homing.** Its limits are
  software-only and are measured from wherever an operator last zeroed it
  ([G2](#g2-r-has-no-endstop-no-physical-homing-and-no-alarm-input)).
- **The H and V endstops are homing references, not limit switches.** They are
  not read during moves, and there is no switch at the negative end of either
  axis ([G3](#g3-the-h-and-v-endstops-are-not-limit-switches-and-the-limits-depend-on-homing)).
- **Several failures are reported to the PC as success.** A move refused by the
  limit check and a failed homing both return `COMMAND_DONE`
  ([G5](#g5-failures-are-acknowledged-as-success)). Driver alarms are not acted
  on during a move and are never shown to the operator
  ([G4](#g4-driver-alarms-are-ignored-during-moves-non-latching-and-invisible)).
- **The screen is not evidence of the machine state.** If a serial port fails to
  open, the terminal simulates the hardware
  ([G6](#g6-the-terminal-simulates-hardware-when-a-port-does-not-open)). If the
  two USB ports are swapped, each controller receives the other's commands, and
  an ordinary move command can set a heater to its 65 °C maximum
  ([G7](#g7-swapped-serial-ports-cross-command-the-two-controllers)).
- **Heater over-temperature protection is firmware-only.** It uses the same
  single sensor that regulates the pad, it needs a running Arduino, and it
  releases automatically. No independent thermal cutout is documented
  ([G8](#g8-heater-protection-is-firmware-only-single-sensor-and-non-latching)).
- **The supply voltages are not recorded anywhere in the repository**
  ([§6.3](#63-electrical)).

## 2. Scope

**Covered:** mechanical, thermal and electrical hazards of the rig, and the
behaviour of the axis firmware, heating firmware and PC terminal that bears on
them.

**Not covered**, and governed by local rules:

- Radiation protection. Measurements involve imaging with the room's X-ray
  system; blueprint prompts refer to "the first XRAY"
  (`blueprints/qa/ETsurface_easyQA_new.json:12`).
- Room access and treatment-couch interlocks.
- Anything involving a patient. That use is prohibited
  ([`disclaimer.md`](disclaimer.md)).

## 3. What the machine is

An Arduino Nano drives three closed-loop stepper drivers (CL57T, `axis:4`) for a
horizontal slide (H), a vertical slide (V) and a rotation stage (R). A second
Nano switches two heating pads through MOSFETs under PI control, reading one
DS18B20 sensor per pad. A PC terminal sends commands over USB and runs scripted
sequences ("blueprints").

The rig carries a phantom and sits on the treatment couch, which is rotated
during some sequences. For example, one prompt reads "Please move the couch to
−90° … 'No' to abort" (`blueprints/qa/ETsurface_easyQA_wcouch_T32_new.json:125`),
and point IDs encode couch angles (`terminal.py:95-96`).

Not documented in the repository:

- the order in which the axes are stacked;
- the frame;
- the phantom's mass;
- the power supplies.

See [`hardware/assembly.md`](../hardware/assembly.md).

## 4. Protections that exist

### 4.1 Motion

| Protection | What it does | Where | Limitation |
|---|---|---|---|
| Software position limits | Refuse a `MOVE_AXIS` whose target lies outside H −45…+25 mm, V −35…+50 mm, R −30…+120° | limits `axis:55-70`; check `axis:143-156`, applied `axis:323-326` | Relative to the current zero, which may be unreferenced (G2, G3). A refusal is reported as success (G5). |
| Same limits in the terminal | Refuse out-of-range targets typed as `m <axis> <pos> <speed>` | `terminal.py:46-50`, `:1216-1219` | Not applied to blueprint moves (`terminal.py:722-747`) |
| R refuses to move until zeroed | `isTargetSafe` returns false for R until `rAxisInitialized` is set | `axis:99`, `:151-152`; set at `:394`, `:423` | "Zeroed" means only that someone issued `h r` or `set r zero` (G2) |
| Speed caps | Clip commanded speed to 50 mm/s = 40 000 steps/s (H, V) and 90 °/s = 1 454 steps/s (R) | `axis:42-43`, `:50-51`, `:316-320` | One-sided, and on H and V never the binding limit (G9) |
| Acceleration | 80 mm/s² on H and V, 40 °/s² on R, set at start-up | `axis:86-87`, `:263-267` | — |
| Normally closed endstops on H and V, with homing | Reference switches at the positive end. Homing sets the switch trigger point to +33 mm (H) and +62 mm (V), then drives to 0. | `axis:30`, `:33`, `:80-83`, `:126-128`, `:204-241`; NC wiring per `1d19cc7:firmware/arduino/src/oldDrives/firsttry_mitebox.ino:23-24` | Read only during homing (G3). A broken wire reads "triggered" and makes homing run the other way (G3). |
| Homing timeout | Each search phase gives up after 20 s | `axis:78`, `:198` | The failure is reported as success (G5) |
| Driver alarm inputs on H and V | Between commands: stop all steppers, set `isAlarmState`, discard later `MOVE_AXIS` and `HOME_AXIS` frames. Also checked during the homing search. | `axis:30`, `:33`, `:185`, `:273-275`, `:301-305` | Not checked during a move; non-latching; invisible on the PC; no input for R; an open wire reads "no alarm" (G4) |

### 4.2 Heating

| Protection | What it does | Where | Limitation |
|---|---|---|---|
| Over-temperature cutout | If the pad's sensor reads above 65 °C (`MAX_SAFE_TEMP`), switch the MOSFET off and zero the integral and duty | `heat:24`, `:61-65` | Same sensor as the regulation, firmware-only, non-latching (G8) |
| Sensor-fault guard | The same branch triggers on NaN or a reading below −50 °C. This catches a disconnected DS18B20, which DallasTemperature reports as −127 °C (`DallasTemperature.h:33`). | `heat:61` | Cannot detect a sensor that is connected but no longer touching the pad (G8) |
| Setpoint clamp | Received setpoints are constrained to 0…65 °C | `heat:143` | 65 °C is also the cutout threshold, so the firmware accepts setpoints right up to it |
| Terminal setpoint range | GUI, `t a <temp>` and `t b <temp>` accept only 10…50 °C surface temperature, i.e. 8.2…55.0 °C at the sensor via `terminal.py:58-60` | `terminal.py:1139`, `:1258` | Blueprint `heat` steps bypass the check (`terminal.py:750-754`) |
| PI integral clamp | Integral constrained to 0…0.25 (`MAX_I`); duty constrained to 0…1 | `heat:29`, `:85`, `:91`, `:95` | See the control defect under G8 |
| Safe start-up setpoints | Both setpoints are 0 °C after every power-up or reset, so the pads stay off once `setup()` has run | `heat:40-42`, `:104-105` | Pads are undefined *before* `setup()` runs ([`pinout.md`](../hardware/pinout.md), pitfall 6). The terminal displays 25.0 °C instead (G8). |

### 4.3 Procedural prompts

- **`h all`** asks "Phantom aligned and all cables clear of the phantom?" before
  homing, then homes in the order V, R, H (`terminal.py:1228-1245`). Homing a
  single axis (`h h`, `h v`, `h r`) asks nothing (`terminal.py:1246-1250`).
- **Blueprints** open with a checkpoint such as "Are all axes homed and the
  phantom correctly mounted, and moved to zero position?"
  (`blueprints/heating-off/ETD_QA_PoP_SingleCouchRotation.json:6`). This relies
  on the operator's judgement, which the gaps below can mislead.

## 5. Gaps in the protections

Several gaps come from how commands flow, so that is summarised first. The
terminal keeps a flag, `axis_ready`. The axis worker thread sends the next
queued command only while `axis_ready` is true (`terminal.py:488-493`), sets it
false as soon as it takes a command from the queue (`terminal.py:496-498`), and
sets it true again on receiving `COMMAND_DONE` (`terminal.py:480-482`), or after
60 s without one (`terminal.py:459-462`). On the Arduino, every move and every
homing runs in a blocking loop that never reads the serial port
(`axis:368-374`, `:176-202`, `:209-212`, `:236-239`).

### G1. There is no emergency stop; STOP ALL is not one

- **The button is a queued serial command.** "STOP ALL" is commented as the
  emergency-stop button (German "Not-Aus", `terminal.py:1109`). All it does is
  put `STOP_ALL` into the same first-in, first-out queue as every other axis
  command (`terminal.py:1110-1113`). For it to take effect, the Qt GUI, the
  Python process, the axis worker thread, the USB link and the firmware's
  command parser must all be working. The worker thread ends permanently on a
  serial exception, logging only "AXIS CRITICAL" (`terminal.py:465`,
  `:523-524`); after that, nothing queued is ever sent.
- **It cannot reach the controller during a move.** While a move or homing
  runs, `axis_ready` is false, so the command stays in the PC's queue, behind
  any commands queued before it (`m zp` and `h all` each queue three). Even if
  the byte were sent, the firmware would not read it until the blocking loop
  ended.
- **It does nothing when it arrives.** The handler calls `stop()` on the three
  steppers (`axis:429-432`). In AccelStepper this decelerates a *moving* motor
  and does nothing to a stationary one (`AccelStepper.cpp:664-674`). Because
  every move is blocking, the steppers are always stationary by the time a
  command is parsed. `STOP_ALL` never touches ENA, so the drivers stay
  energised (`axis:257`).
- **It delays later commands by up to a minute.** The firmware sends no
  `COMMAND_DONE` for `STOP_ALL`, so `axis_ready` stays false until the 60 s
  watchdog. Commands typed in the meantime queue up and are then sent one after
  another, with no further confirmation.
- **It does not stop a blueprint.** The interpreter thread keeps its sequence
  and sends the next move as soon as `axis_ready` is released
  (`terminal.py:730-747`). **Motion resumes about 60 s after STOP ALL without
  any operator action.** Only `exit bp` ends a blueprint
  (`terminal.py:1281-1287`), and it also acts only between steps: a move
  already sent runs to completion.

**Consequence:** nothing in hardware or software can stop a move in progress,
short of removing power. See the [recommendation](#8-recommendation-fit-a-hardwired-latching-emergency-stop).

### G2. R has no endstop, no physical homing, and no alarm input

- **No switch and no alarm input.** Only PUL, DIR and ENA pins are defined for R
  (`axis:35`). A superseded sketch says so directly: "R has no endstop/alarm"
  (`1d19cc7:firmware/arduino/src/oldDrives/SURF_nanoAxis_v3/SURF_nanoAxis_v3.ino:19`).
- **Homing R does not move it.** `HOME_AXIS` on R only calls
  `setCurrentPosition(0)` and sets `rAxisInitialized` (`axis:392-396`).
  `SET_ZERO` on R does the same (`axis:420-423`). The comment in `h all` says R
  is "rotated" (`terminal.py:1239`); it is not.
- **The limit window moves with the zero.** The −30…+120° limits are measured
  from wherever R was when zeroed. An R zeroed at the wrong angle shifts the
  whole window, including the travel the software believes is safe, by that
  error.
- **Every reset clears the zero.** A reset of the axis Nano clears
  `rAxisInitialized` (`axis:99`), after which R moves are refused, and each
  refusal is reported as success (G5).
- **R driver faults are invisible.** A fault on the R driver is seen by neither
  the firmware nor the PC.

### G3. The H and V endstops are not limit switches, and the limits depend on homing

- **Endstops are read only while homing.** They are read in the homing routine
  and for the LED (`axis:130-135`, `:176-241`, `:278`) and nowhere in
  `MOVE_AXIS` (`axis:310-379`). A move that reaches a switch keeps going.
- **No switch at the negative end.** Each axis has one switch, at the end that
  homing approaches (`HOMING_SIGN_H = HOMING_SIGN_V = +1`, `axis:82-83`).
- **Limits apply before homing, around an arbitrary zero.**
  `hAxisInitialized` and `vAxisInitialized` are declared but never used
  (`axis:100-101`), and the H and V checks do not require homing
  (`axis:144-149`). After power-up or reset the step counters start at 0
  wherever the slides happen to be, so the −45…+25 mm and −35…+50 mm windows
  are centred on that arbitrary point.
- **Where the window sits after homing.** The switch trigger point becomes
  +33 mm (H) or +62 mm (V) (`axis:80-81`, `:231`). The positive limits
  therefore stop 8 mm (H) and 12 mm (V) short of the trigger point. The negative
  limits lie 78 mm (H) and 97 mm (V) beyond it, with no switch. Whether the
  mechanics have that much free travel is not documented.
- **Re-zeroing H or V moves the window.** `SET_ZERO` on H or V (`axis:412-419`;
  commands `set h zero` and `set v zero`, `terminal.py:1268-1273`) re-references
  the window without any check. Zeroing a homed H at +20 mm puts the new
  positive limit 45 mm from the working zero, 12 mm past the switch trigger
  point. The terminal's log message for both commands wrongly says the *R*
  position was zeroed (`terminal.py:1270`, `:1273`).
- **A switch that reads "triggered" at rest makes homing run away.** This
  happens with a broken wire or with normally open switches fitted as the stale
  comments suggest. Homing then moves up to about 48 mm towards the switchless
  negative end (8 mm clearing move + 2 mm/s × 20 s timeout) and fails silently;
  details in [`pinout.md`](../hardware/pinout.md), pitfall 1. During homing no
  software limit applies. The clearing move and the final move to the working
  zero check neither the endstop nor the alarm inputs (`axis:206-213`,
  `:233-239`).

### G4. Driver alarms are ignored during moves, non-latching, and invisible

- **Not checked during a move.** The blocking move loop never reads ALM
  (`axis:368-374`). An alarm raised during a move is first seen after the move
  has ended (`axis:273-275`).
- **Detection does little.** The `stop()` calls then have no effect, because
  the steppers are already stationary. Later `MOVE_AXIS` and `HOME_AXIS` frames
  are read and discarded **without** `COMMAND_DONE` (`axis:301-305`), so each
  discarded command costs the terminal a 60 s watchdog timeout, after which it
  sends the next.
- **Non-latching.** Once the ALM line returns to HIGH, `isAlarmState` clears on
  the next loop pass (`axis:275`) and commands are accepted again, with no
  acknowledgement required.
- **Invisible to the operator.** The firmware reports both alarm bits and the
  alarm state in every status frame (`axis:166-172`). The terminal reads that
  byte into `_stat` and discards it (`terminal.py:473`); nothing appears on
  screen.
- **Drivers stay enabled.** ENA is never released on an alarm (`axis:257`).
- **Coverage is incomplete.** There is no alarm input for R, and a disconnected
  ALM wire reads as "no alarm" ([`pinout.md`](../hardware/pinout.md), pitfall 2).

### G5. Failures are acknowledged as success

- **Refused moves.** `MOVE_AXIS` writes `COMMAND_DONE` whether or not the limit
  check passed (`axis:323-377`). A target out of range, an unknown axis, and an
  R move before zeroing are all acknowledged exactly like a completed move. The
  terminal logs "Axis: movement completed" (`terminal.py:483`) and the
  blueprint continues. Blueprint targets are not checked on the PC
  (`terminal.py:722-747`), so a mistyped target is silently skipped and the
  following operator prompts assume a pose the phantom never reached.
- **Failed homing.** `HOME_AXIS` computes `success` and never transmits it
  (`axis:384-401`). A timeout, an alarm during homing, and a switch that reads
  triggered at rest all produce the same `COMMAND_DONE` as a successful homing.

**Consequence:** the operator can believe an axis is referenced, or at its
target, when it is not, and base later motion and decisions to approach the rig
on that belief.

### G6. The terminal simulates hardware when a port does not open

- **Axis port.** If the port fails to open, the terminal logs "Error: device not
  found. Forced simulation!" (`terminal.py:454-455`). From then on every
  command "completes" after 0.5 s (`terminal.py:517-520`) and positions stay at
  0.0.
- **Heating port.** The terminal logs "Heating simulation active."
  (`terminal.py:550-551`), then sets the displayed temperatures equal to the
  setpoints and marks them stable (`terminal.py:602-609`). A blueprint's
  `wait_steady` step therefore passes at once.
- **No lasting indication.** Each case produces one console line, which scrolls
  away. The status bar keeps showing "BEREIT" (ready) and "STABIL" (stable)
  exactly as it does for real hardware (`terminal.py:1615-1624`). Setting
  `SIMULATION_MODE = False` (`terminal.py:67`) does not prevent the fallback.
- **Losing USB later.** A USB disconnect after start-up ends the affected worker
  thread with one log line ("AXIS CRITICAL", `terminal.py:523-524`; "HEAT THREAD
  ERROR", `terminal.py:612-613`). After that, axis commands, including STOP
  ALL, and heater setpoints are silently never sent.

Do not decide to approach or handle the rig from what the screen shows.

### G7. Swapped serial ports cross-command the two controllers

The terminal assigns the two boards purely by hard-coded port name
(`terminal.py:30-39`), and neither firmware identifies itself
([`pinout.md`](../hardware/pinout.md#boards-and-host-connection)). The command
codes collide: `MOVE_AXIS` = 1 = `CMD_SET_A` and `HOME_AXIS` = 2 = `CMD_SET_B`
(`axis:13-14`, `heat:13-14`). Both directions below were verified by feeding the
terminal's exact byte encoding (`terminal.py:365-368`, `:504-510`, `:596-598`)
through a reimplementation of each firmware's parser (`axis:297-433`,
`heat:133-147`).

- **Axis commands reaching the heating board set a heater to maximum.** The
  heating firmware reads a move frame `[1][axis][target int32][speed int32]` as
  `CMD_SET_A`, with a value built from the axis byte and the low three target
  bytes. **Any positive target of 26 steps or more** (0.0325 mm on H or V,
  1.61° on R) produces more than 65.00 °C, which the clamp turns into a
  65 °C setpoint for pad A (`heat:141-145`). Example: `m h 10 5` sends
  `01 00 40 1F 00 00 A0 0F 00 00`. The heating firmware reads `0x001F4000`
  = 2 048 000, i.e. 20 480 °C, and pad A's setpoint becomes 65 °C.
- **Heater setpoints reaching the axis board can start homing or move the limit
  window.** A setpoint frame `[pad][value int32]` is read as an axis command.
  Over the terminal's accepted range (10.0…50.0 °C in 0.1 °C steps), a single
  `t b` command decodes as:
  - homing of H for `t b 20.5`;
  - homing of V for `t b 22.7` and `t b 40.2` (both real motion);
  - zeroing of R for `t b 42.4`;
  - `SET_ZERO` on H for every value from 16.2 to 18.3 °C (22 values), which
    silently shifts the H limit window.

  No in-limit move was decoded, from single commands or from the GUI's A+B
  pair.

**How a swap shows before any command is sent:** the pad temperatures read
2.99 °C while the axes are at zero, because axis status frames are being decoded
as temperatures (`terminal.py:566-567`), and the axis readout shows implausible
positions.

### G8. Heater protection is firmware-only, single-sensor, and non-latching

- **One sensor, no independent cutout.** The 65 °C cutout judges the same
  DS18B20 reading that drives the regulation (`heat:117-120`, `:61`). It works
  only while the heating Nano runs. No independent device (thermal fuse, bimetal
  thermostat) is documented anywhere in the repository.
- **Non-latching.** Regulation resumes on the next 1 Hz update once the reading
  is back at or below 65 °C (`heat:61-67`, `:116`).
- **Blind to the likeliest overheating faults.** A sensor that has come off its
  pad reads a cooler spot, and the cutout never sees the overheating. With the
  integral at zero, the proportional term alone commands 100 % duty once the
  setpoint exceeds the reading by 6.67 °C (`KP = 0.15`, `heat:27`, `:90-91`). A
  detached sensor at room temperature under a routine 32 °C surface target
  (33.94 °C at the sensor) is well past that, so the pad is driven at full power
  continuously. A MOSFET that fails in the conducting state cannot be switched
  off by the firmware at all. **The temperature a pad reaches at full power is
  not documented.**
- **High setpoints are reachable.** The firmware accepts setpoints up to 65 °C
  (`heat:143`). Blueprint `heat` steps bypass the terminal's 10–50 °C check
  (`terminal.py:750-754`), and swapped ports can set 65 °C (G7).
- **Setpoints persist, and there is no "off".** The heating loop has no host
  timeout (`heat:111-157`), so a setpoint stays active for as long as the Nano
  has power. The terminal sends nothing when it closes (`terminal.py:1575-1593`)
  and has no "off" command. The lowest value it accepts, 10 °C, maps to 8.2 °C
  at the sensor, which keeps a pad unpowered at any normal room temperature.
- **The display disagrees with the firmware.** The terminal shows setpoints of
  25.0 °C at start-up (`terminal.py:349`, `:1053`, `:1057`), while the firmware
  holds 0 °C (`heat:40-42`). The terminal never reads setpoints back. The
  temperature it displays is a model estimate fitted on one pad only
  ([`hardware/README.md`](../hardware/README.md#thermal-calibration-provenance)),
  so "STABIL" does not certify the actual surface temperature.
- **Control-code defect, bounded by the clamps.** In `updateHeater`, the block
  at `heat:69-92` repeats its own condition and is mis-nested. As a result the
  integral reset for errors of 10 °C or more (`heat:86-88`) can never run, and
  the integral keeps its last value (at most 0.25) outside the ±10 °C window.
  Outside that window the proportional term already saturates the duty, so the
  effect is limited to carrying stale integral back into the window. The header
  comment's "Ki=0.005" (`heat:3`) also disagrees with the code's
  `KI = 0.0025f` (`heat:28`).

### G9. The speed caps are one-sided and not the binding limit

- **Negative speeds bypass the cap.** Only values *above* the cap are clipped
  (`axis:316-320`). In AccelStepper, `setMaxSpeed()` uses the magnitude of a
  negative value (`AccelStepper.cpp:265-266`), so a negative speed bypasses the
  cap. A zero speed is not rejected either; what the blocking move loop then
  does has not been tested. The terminal validates neither the speed field of
  `m` (`terminal.py:1214`, `:1223`) nor that of blueprint moves
  (`terminal.py:723`, `:739`).
- **On H and V the cap never engages.** The linear cap of 40 000 steps/s is ten
  times the "about 4000 steps per second" that AccelStepper documents as
  reliable on a 16 MHz Arduino (`AccelStepper.h:324-325`). The archived logs
  agree. In `data/raw/2026-08-06/ETsurface_easyQA_20260806_180321.csv`, recorded
  with `blueprints/qa/ETsurface_easyQA_new.json`, whose H and V moves all
  command 20 mm/s, H covers 30 mm in about 5.9 s and V covers 50 mm in about
  9.8 s. That is ≈5.1 mm/s (≈4 100 steps/s), a quarter of the commanded speed.
  The real ceiling is step generation, not the cap.
- **A faster controller would make existing blueprints faster.** If step
  generation ever becomes faster (another microcontroller or library, or less
  work in the move loop), existing blueprints will move 4× faster than observed
  at their 20 mm/s steps and 10× faster at their 50 mm/s steps. Re-validate
  speeds after any such change.

### G10. Other behaviour that matters for safety

- **Truncated frames freeze the axis firmware.** Serial reads have no timeout
  (`axis:112-120`). A truncated command frame leaves the firmware waiting
  indefinitely, sending no status frames and polling no alarms, until more
  bytes arrive.
- **Positions are volatile.** A reset of the axis Nano zeroes all three step
  counters, clears R's zeroed state (`axis:99`) and switches backlash
  compensation off (`axis:45`). Classic Nano boards commonly reset when a
  serial port is opened. Whether these boards do is not recorded, but the
  terminal waits 2 s after opening each port (`terminal.py:451`, `:546`), which
  is consistent with it. **After every terminal start, treat all positions as
  unreferenced.**

## 6. Hazards by type

### 6.1 Mechanical

- **Moving parts.** Two slides and a rotation stage carrying the phantom and
  the pads. The phantom's mass, the moving mass of each axis and the order in
  which the axes are stacked are not documented. The motors are NEMA 23
  (`1d19cc7:README.md:1`) driving screws with a 4 mm lead
  (`1d19cc7:firmware/arduino/src/oldDrives/firsttry_mitebox.ino:62-65`). That
  combination can develop high axial force at low speed. The driver current
  setting that bounds the force is not recorded, and no force has been measured.
- **Pinch, crush and shear points.** These occur at the ends of both slides,
  under the V carriage, at the lead screws and nuts, the couplings, the bevel
  gear, and between the rotating stage and fixed parts. V moves 35 mm below its
  working zero. Comments indicate that positive V is up (`axis:61-62`: "Example:
  larger range at the top" / "Example: must not go down deep";
  `terminal.py:1238`: homing drives "V up"); confirm this on the rig. **No guard, cover or enclosure is
  documented.** The `hardware/enclosure/` and `hardware/safety/` directories at
  `1d19cc7` held only `.gitkeep` placeholders.
- **Unexpected motion.** The rig can move with no operator action:
  - queued commands sent up to 60 s after STOP ALL, and blueprints resuming
    after it (G1);
  - homing running away towards the negative end (G3);
  - a heater command decoded as homing on swapped ports (G7).
- **Rotation sweep.** R sweeps −30…+120° from wherever it was zeroed. A wrongly
  set zero shifts the sweep relative to the rig (G2).
- **Cables.** Motor, sensor and heater cables ride on moving stages. `h all`
  asks for cables to be clear (`terminal.py:1231`); nothing enforces it.
- **Treatment couch.** The rig is carried through couch rotations (§3). How the
  rig is secured to the couch, the couch load it imposes, and collision
  clearances in the room are not documented. Use that could affect
  patient-bearing equipment is prohibited ([`disclaimer.md`](disclaimer.md)).
- **Loss of drive power.** Whether V drops under gravity, or R turns under an
  unbalanced load, when driver power or enable is removed is not documented.
  Establish this before relying on "remove power" as a safe state (§8).

### 6.2 Thermal

- **Routine temperatures.** Blueprints request surface temperatures of 32 °C
  (eight steps), 35 °C and 36 °C. The terminal converts these to 33.94, 37.45
  and 38.62 °C at the sensor (`terminal.py:58-60`).
- **Measured range.** In the calibration session, surface temperatures of
  24.6–46.6 °C were measured with a reference thermometer, at sensor readings
  of 25.0–51.3 °C (`hardware/calibration/heating-pad-calibration.csv`).
- **Beyond the measured range.** The GUI accepts up to 50 °C surface, which is
  55.0 °C at the sensor and outside the calibrated range. Blueprints and swapped
  ports can reach the 65 °C sensor clamp. The surface temperature at a 65 °C
  sensor reading has never been measured.
- **Contact burns.** Prolonged skin contact at these temperatures can burn. The
  threshold depends on contact time and surface material; ISO 13732-1 gives
  assessment methods. The repository does not establish a safe contact time
  for these pads.
- **Unattended heating and fire.** Pads keep heating after the terminal is
  closed (G8). A sensor detached from its pad drives full power (G8). The pad
  construction, adhesive, insulation and full-power temperature are not
  documented.

### 6.3 Electrical

**What the firmware and repository establish:**

- Two Arduino Nano boards (5 V logic), each connected to the PC by USB
  (`terminal.py:30-39`).
- Three CL57T drivers, taking PUL, DIR and ENA from the axis Nano. H and V
  return ALM ([`pinout.md`](../hardware/pinout.md)).
- Three stepper motors, NEMA 23 per `1d19cc7:README.md:1`.
- Two heating pads switched by MOSFETs, which the heating Nano drives HIGH to
  turn on (`heat:21-22`, `:150-156`).
- The ENA outputs are written once at start-up and never released by any
  software path (`axis:257`). The motors are therefore energised, holding
  torque, whenever the driver supply is on.

**The supply voltage is not determinable from the repository.** No file in the
working tree, and none of the 107 commits in its history, states the voltage of
the driver and motor supply or of the heating-pad supply. Do not infer it from
the driver model, which does not fix the voltage a particular build uses.

Also not documented:

- the number and current rating of the supplies;
- whether and how they connect to mains: inlet, switch, fusing, protective
  earth of the frame;
- the enclosure of live parts;
- wire gauges and connectors;
- the pads' voltage and power;
- the MOSFET type and ratings;
- the ground relationship between PC, Nanos and power stage;
- **how the two Nanos are powered.** This decides what happens when USB is
  disconnected. A heating Nano powered only from USB switches off, and the pads
  then depend on an undocumented gate pull-down
  ([`pinout.md`](../hardware/pinout.md), pitfall 6). A Nano powered from
  another source keeps regulating to its last setpoint.

**Hazards that follow:**

- Exposed live terminals on the power stage: no enclosure is documented.
- Undefined driver and MOSFET inputs while a Nano is resetting or being flashed
  with the power stage live ([`pinout.md`](../hardware/pinout.md), pitfalls 3
  and 6).
- A sketch flashed onto the wrong board can energise a pad with no control
  ([`pinout.md`](../hardware/pinout.md#cross-flashing-and-swapped-ports)).

No electrical-safety or EMC assessment exists ([`disclaimer.md`](disclaimer.md)).

## 7. Pre-use checklist

Work through every item, every session. Items marked *(gap)* compensate for a
missing technical protection.

**Before switching on**

1. Confirm local approval, room access and radiation-protection arrangements,
   and that no patient is present. Read [`disclaimer.md`](disclaimer.md),
   this document and [`known-issues.md`](known-issues.md).
2. Inspect the rig:
   - frame secured, phantom and pads mounted, fasteners tight;
   - cables strain-relieved and routed clear of all H, V and R travel and of
     couch motion;
   - no damaged insulation.
3. *(gap)* Identify the means of disconnecting driver power and heater power,
   and keep it within the operator's reach for the whole session. Until an
   emergency stop is fitted it is the only way to stop motion (G1).
4. *(gap)* Check that each pad's DS18B20 is firmly attached to its pad (G8).
5. *(gap)* Check that the USB cables are labelled and connected to the ports
   named in `terminal.py:30-39` (G7).

**After switching on, before sending any command**

6. *(gap)* With both slides away from their switches, the on-board LED of the
   axis Nano (D13) must be dark. If it is lit, do not home (G3;
   [`pinout.md`](../hardware/pinout.md), pitfall 1).
7. *(gap)* Start the terminal and read the console. Both
   "…verbunden (&lt;port&gt;)" ("connected") lines must be present
   (`terminal.py:453`, `:548`). Neither "Erzwungene Simulation!"
   (`terminal.py:455`) nor "Heiz-Simulation aktiv." (`terminal.py:551`) may
   appear (G6).
8. *(gap)* Check the pad temperatures in the status bar. They should read near
   room temperature. Stop if they read:
   - ≈2.99 °C: swapped ports (G7);
   - exactly the setpoint with "STABIL" at once: simulation (G6);
   - ≈−105.6 °C: a disconnected sensor.
9. *(gap)* Treat all positions as unreferenced (G10). Home V and H, and **watch
   each homing finish at the working zero**; the terminal cannot tell a failed
   homing from a successful one (G5).
10. *(gap)* Turn R to its physical zero mark and zero it with `h r` or
    `set r zero` (G2). The mark still has to be defined; see
    [`hardware/assembly.md`](../hardware/assembly.md).
11. If the measurement requires it, switch backlash compensation on
    explicitly with `backlash on`. It is off after every reset (`axis:45`).
12. Make the session's first move on each axis small and slow. Confirm the
    direction and that the readout matches the motion.

**During operation**

13. Keep everyone out of reach of moving parts whenever the driver supply is on.
    STOP ALL does not stop a move (G1).
14. Do not use `set h zero` or `set v zero` on a homed axis (G3).
15. After pressing STOP ALL, do not type further commands: they will run up to
    60 s later. To end a blueprint, use `exit bp`. To stop motion, remove driver
    power (G1).
16. Never leave heated pads unattended (G8).

**After use**

17. Set both pads to 10 °C with `t a 10` and `t b 10`, then switch off the heater
    supply and the driver supply. Closing the terminal does neither (G8).

## 8. Recommendation: fit a hardwired, latching emergency stop

Fit an emergency stop before further use. Design it to ISO 13850, with stop
categories chosen per IEC 60204-1, and meet at least the following.

- **Latching device.** A red-on-yellow mushroom-head device with
  positive-opening contacts (IEC 60947-5-5) that stays latched until released by
  hand, within reach of the operator position.
- **Independent of the PC.** It must remove the energy for motion without
  relying on the PC, the USB link, the Python process or the firmware. Open the
  DC supply to all three drivers through a suitably rated contactor or safety
  relay. Pulling the drivers' ENA inputs is not enough as the only channel:
  today ENA is driven by firmware.
- **Stop category.** Because the firmware cannot execute a controlled stop
  (G1), a category 0 stop (immediate removal of power) is the realistic choice.
  **First establish whether V, or an unbalanced R, back-drives when
  de-energised** (§6.1). If it does, add a brake or mechanical support.
- **Heaters too.** Include the heating-pad supply in the stop circuit. Also fit
  an independent over-temperature cutout on each pad, wired in series with that
  pad's supply, so that a detached sensor or a failed MOSFET cannot overheat it
  (G8).
- **Releasing the stop must not restart motion.** The firmware currently
  executes whatever arrives, and the terminal may be holding queued commands
  (G1). Wire an auxiliary contact to a free input on the axis Nano (A2–A5; see
  [`pinout.md`](../hardware/pinout.md)). Change the firmware to refuse motion
  until the axes are re-homed after a stop, and clear the terminal's queue.
- **Positions are lost after a stop.** A de-energised driver does not hold its
  axis. Re-home before continuing.
- **Test it.** Before each session, trip the stop during a move at the highest
  speed the session will use.

Related changes that would close further gaps are tracked in
[`known-issues.md`](known-issues.md). They include:

- a switch or hard stop at the negative end of H and V;
- a reference switch for R;
- an alarm input for the R driver;
- reporting move and homing failures to the PC;
- displaying the alarm bits;
- identifying each board by handshake.
