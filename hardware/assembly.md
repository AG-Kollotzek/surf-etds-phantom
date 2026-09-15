# Assembly and commissioning

> **No CAD model, drawing, schematic, wiring diagram or photograph of the SURF
> Test Unit exists in this repository.** Before release preparation, the
> `hardware/` tree held placeholder directories for schematics, PCB, wiring,
> pinout, enclosure, suppliers and safety, and every one of them contained only
> a `.gitkeep` file (`git ls-tree -r 270cdf5 -- hardware`).

This document is therefore a **skeleton**. It fills in everything that the
firmware, the terminal, the calibration files and the lab notebook actually
establish. Everything else is marked **TODO**, stating the evidence needed to
close it. Read [`../docs/safety.md`](../docs/safety.md) before building or
powering anything.

**Citations:**

| Short form | File |
|---|---|
| `axis:<line>` | [`firmware/axis/SURF_nanoAxis_v5/SURF_nanoAxis_v5.ino`](../firmware/axis/SURF_nanoAxis_v5/SURF_nanoAxis_v5.ino) |
| `heat:<line>` | [`firmware/heating/SURF_nanoHeating_v4/SURF_nanoHeating_v4.ino`](../firmware/heating/SURF_nanoHeating_v4/SURF_nanoHeating_v4.ino) |
| `calib:<line>` | [`firmware/tools/rotation_calibration/rotation_calibration.ino`](../firmware/tools/rotation_calibration/rotation_calibration.ino) |
| `terminal.py:<line>` | [`software/surf_terminal/terminal.py`](../software/surf_terminal/terminal.py) |
| `notebook:<line>` | [`docs/calibration/backlash-measurement-raw.txt`](../docs/calibration/backlash-measurement-raw.txt), translated from German |
| `270cdf5:<path>:<line>` | superseded file in git history, read with `git show 270cdf5:<path>` |

Pins are in [`pinout.md`](pinout.md); parts in [`bom.csv`](bom.csv).

---

## 1. Machine layout and conventions

**Established:**

- **Axes.** H = 0, V = 1, R = 2 (`axis:22-26`). H and V are in mm, R in degrees
  (`terminal.py:46-50`).
- **Firmware software window.** H −45…+25 mm, V −35…+50 mm, R −30…+120°
  (`axis:55-70`).
- **Positive V is up.** This is inferred, not stated: the V limit comments read
  "Example: larger range at the top" / "Example: must not go down deep"
  (`axis:61-62`), and `h all` homes V first to "drive V up, to avoid
  collisions" (`terminal.py:1238`), with homing moving in the positive
  direction (`axis:83`). Confirm on the rig.
- **V is not a pure vertical translation.** A removed design discussion states
  that the V slide produces a coupled Z shift and pitch/yaw motion
  (`270cdf5:docs/PoPargumentation&blueprints.txt:9`). The geometry that causes
  this is not documented.

**TODO:**

- **Kinematic chain.** Which axis carries which, and where the phantom mounts.
  Needed: photo or drawing of the assembled rig.
- **Positive directions of H and R**, relative to the rig and to the room.
  Needed: a labelled photo, plus a check with a small move (§8, step 10).
- **V geometry.** Slide angle or mechanism, and the resulting Z/pitch/yaw per mm
  of V travel. Needed: a dimensioned drawing, or a measurement of the forward
  kinematics.

## 2. Frame

**TODO**, nothing is documented. A rebuild needs:

- materials and cross-sections;
- overall dimensions, with a dimensioned drawing or CAD export (STEP);
- where each axis is mounted;
- how the rig is secured to the treatment couch, which it rides on during couch
  rotations (`blueprints/qa/ETsurface_easyQA_wcouch_T32_new.json:125`);
- total mass and centre of mass;
- guarding of pinch points (none is documented; [`../docs/safety.md`](../docs/safety.md) §6.1).

## 3. Linear axes (H and V): slides, screws and couplings

### 3.1 What the firmware establishes

| Quantity | Value | Source |
|---|---|---|
| Steps per mm (H and V) | 800 | `axis:39`, `terminal.py:68` |
| Resolution | 1/800 mm = 1.25 µm per step | derived |
| Decomposition of 800 steps/mm | 200 full steps/rev × 16 microsteps ÷ 4 mm lead | `270cdf5:firmware/arduino/src/oldDrives/firsttry_mitebox.ino:62-65` (superseded sketch) |
| Implied driver setting | 3 200 pulses per motor revolution, **if** the lead is 4 mm | derived from the row above |
| Acceleration | 80 mm/s² | `axis:86`, `:263-264` |
| Speed cap (firmware) | 50 mm/s | `axis:42`; not the binding limit, see [`../docs/safety.md`](../docs/safety.md) G9 |
| Observed speed in the move loop | ≈5.1 mm/s with 20 mm/s commanded | [`../docs/safety.md`](../docs/safety.md) G9 |
| Homing switch | one normally closed (NC) switch per axis, at the positive end | `axis:30`, `:33`, `:82-83`; [`pinout.md`](pinout.md) |
| Switch trigger point in axis coordinates | H +33.0 mm, V +62.0 mm | `axis:80-81`, `:231` |
| Backlash compensation | 0 steps on H and V | `axis:46` |

### 3.2 Minimum free travel implied by the firmware (derived)

After homing, the axis must be able to move from the switch trigger point to
the negative software limit without meeting a mechanical end:

- **H:** 33 + 45 = **78 mm**
- **V:** 62 + 35 = **97 mm**

On top of that it needs:

- **Switch overtravel.** The switch is accepted only after reading "triggered"
  for 30 ms (`axis:79`, `:195`). At the commanded homing speeds that is up to
  10 mm/s × 30 ms = 0.3 mm in the fast search and 0.06 mm in the fine approach,
  plus mechanical overrun. The switch must tolerate this without damage.
- **A margin beyond the negative limit.** There is no switch there
  ([`../docs/safety.md`](../docs/safety.md) G3). TODO: decide on a hard stop or
  a second switch.

The positive software limits stop 8 mm (H) and 12 mm (V) short of the switch
trigger point (derived: 33 − 25 and 62 − 50).

### 3.3 Backlash: horizontal axis (lab notebook, 09.03.26)

**Setup.** The session used firmware `nanoAxis_v5` and `nanoHeating_v4`
(`notebook:1`). It started from the state after homing, and the first move was
in the negative direction "so that it continues in the same direction"
(`notebook:3`). The dial gauge was brought into contact with the carriage,
clamped, preloaded and zeroed (`notebook:5`). One division is 0.01 mm: the
notebook calls half a division "5 µm" (`notebook:20`).

Commands have the form `m <axis> <target> <speed>` (`terminal.py:1210-1224`).
Readings are dial divisions, magnitude only.

| Line | Command | Reading | Note |
|---|---|---|---|
| 7 | `m h -0.5 0.5` | 54 | |
| 8 | `m h 0 0.5` | 2 | |
| 9 | `m h 0.1 0.1`, `m h 0 0.1` | — | gauge set to 0 |
| 10 | `m h -0.5 0.1` | 52 | |
| 11 | `m h 0 0.1` | 2 | gauge zeroed again |
| 12 | `m h -0.3 0.1` | — | no reading recorded |
| 14 | — | — | "Assumption: readings too large (gauge valid only up to 0.4 mm because of its arc motion; beyond 0.4, cosine error because the measurement is linear)" |
| 16 | homing repeated | — | |
| 17 | `m h -0.3 0.1` | 30 | |
| 18 | `m h 0 0.1` | 0 | |

The notebook concludes (`notebook:20-21`): "no relevant backlash measurable on
the horizontal axis (half a division was the largest observation = 5 µm
error); moves are extremely precise, even 0.1 mm is approached perfectly."

Read the evidence accurately:

- Both 0.5 mm out-and-back runs returned with a 2-division (0.02 mm) residual.
- The notebook blames the over-reading on the gauge's range.
- The H conclusion rests on the single in-range run after re-homing
  (0.3 mm out, return to 0).

**TODO:**

- **V backlash has never been measured**; the notebook has no V entries.
- **H backlash needs repeating.** Repeat with several in-range runs in both
  approach directions and record every gauge re-zeroing.

### 3.4 TODO for the linear axes

- **Slides.** Guide type, stroke, carriage, and how the V load is supported.
- **Screws.** Type (trapezoidal or ball), diameter, length, nut, preload, end
  bearings. The 4 mm lead is recorded only in a superseded sketch; measure it.
- **Couplings.** Motor-to-screw coupling type. A closed-loop driver corrects the
  motor shaft; coupling wind-up, screw backlash and nut play lie outside that
  loop.
- **Endstops.** Switch model, mounting and adjustment. Record how the switch
  position is fixed: moving it moves the working zero (§7.2).
- **Gravity.** Whether V back-drives when unpowered. This is needed for the
  emergency-stop design ([`../docs/safety.md`](../docs/safety.md) §8).

## 4. Rotation stage (R): 1:2 bevel gear

### 4.1 Steps per degree: 16.156 vs 16.1599

| Value | Where | Used for |
|---|---|---|
| **16.156** steps/° | `axis:40` (firmware), `terminal.py:69` (terminal) | commanding R (`terminal.py:728`, `:1222`), limits (`axis:69-70`), and converting logged R positions to degrees (`terminal.py:478`) |
| **16.1599** steps/° | `calib:9`, under the heading "calibrated values" (`calib:8`) | the bench calibration sketch only |
| 17.78 steps/° (nominal) | 200 steps/rev × 16 microsteps × gear ratio 2.0 ÷ 360 (`270cdf5:firmware/arduino/src/oldDrives/firsttry_mitebox.ino:68-73`) | superseded first sketch |

**Size of the discrepancy (derived).** 16.1599 − 16.156 = 0.0039 steps/°,
i.e. 0.024 %. One step is 1/16.156 = 0.062°. At the +120° limit the two values
differ by 0.47 steps (0.029°); at 95°, the largest R target in any blueprint,
by 0.37 steps (0.023°). The difference is below one step anywhere in R's range.

**Provenance, from git history:**

| Date | Commit | Change |
|---|---|---|
| 2025-12-17 | `1f6ab9a` | Terminal value changed from 16.515 to 16.156. Commit message: "rotation axis calibrated over 10 revolutions ±2°". |
| 2026-01-26 | `2d68ed1` | Axis firmware changed to 16.156. |
| 2026-03-25 | `2406ae3` | 16.1599 first appears, in the calibration sketch, after the notebook sessions of 09-10.03.26. |

16.1599 was never propagated to the firmware or the terminal. Two consequences:

- **The 10-revolution calibration cannot separate the two values.** A ±2°
  uncertainty over 10 revolutions (3 600°) is ±0.056 %, larger than the 0.024 %
  between them. Neither the 16.1599 measurement nor its uncertainty is
  recorded.
- **Between 2025-12-17 and 2026-01-26 the terminal and firmware held different
  values** (16.156 vs 16.515, 2.2 % apart). Anyone reusing R data recorded in
  that window must first establish which firmware was flashed at the time.

**The calibrated value is about 9 % below the nominal 17.78 steps/°.** The
nominal 1:2 ratio (`GEAR_RATIO_R = 2.0`, superseded sketch; "bevel gearbox 1:2",
`270cdf5:docs/PoPargumentation&blueprints.txt:44`) with 3 200 pulses/rev does
not reproduce the calibrated value. The actual tooth counts and microstep
setting are not recorded. 360 × 16.156 = 5 816 steps per output revolution.

**TODO:**

- Count the gear teeth and read each driver's microstep setting, then explain
  the 9 % gap.
- Re-measure steps/° with a documented method and uncertainty, over several
  revolutions, using the calibration sketch. **That sketch has no software
  limits** (`calib:30-70`), so remove the phantom and free all cables first.
- Decide whether 16.156 or 16.1599 is correct and propagate the result.

### 4.2 Backlash: rotation axis (lab notebook, 09.03.26 and 10.03.26)

The gauge was placed 15 mm from the rotation axis. This lever arm appears at
`notebook:36`, at `calib:12` and as the default in
[`software/surf_terminal/tools/backlash_calculator.py`](../software/surf_terminal/tools/backlash_calculator.py)
(line 64), which converts with x = r·tan θ (line 31). The notebook does not
record every re-zeroing of the gauge. The readings are consistent with the
gauge being zeroed at the start of each out-and-back pair.

| Line | Command | Reading (divisions) | mm | Expected r·tan(Δθ) (derived) |
|---|---|---|---|---|
| 26 | R to 2.5°, then "set zero" | — | — | — |
| 27 | `r 4 0.5` (+1.5°) | 41 | 0.41 | 0.393 |
| 28 | `r 2.5 0.5` (return) | **6** | **0.06** | 0 |
| 30-31 | `r 0 0.5`, then `r 1 0.5` (+1.0°) | 25 | 0.25 | 0.262 |
| 32 | `r 0 0.5` (return) | **5** | **0.05** | 0 |
| 35-37 | "10.03.26 corrected": 4-step compensation active; homing | — | — | — |
| 38 | `m r -1,2 0.5` (−1.2°) | 31 | 0.31 | 0.314 |
| 39 | `m r 0 0.5` (return) | **0** | **0** | 0 |

**Interpretation.** Without compensation, the return residual was 5-6
divisions (0.05-0.06 mm) at 15 mm. That corresponds to atan(0.05/15) to
atan(0.06/15) = 0.19° to 0.23°, or 3.1 to 3.7 steps at 16.1599 steps/°. The
calibration sketch comments: "0.06 mm at a 15 mm lever arm corresponds to
approx. 3.7 steps → we use 4" (`calib:12-13`). With 4 steps of compensation
(0.248°), the return residual was 0. The outbound readings agree with
r·tan(Δθ) to within 2 divisions, which is far too coarse to test a 0.024 %
difference in steps/°.

**Unit slip in the notebook.** `notebook:36` gives the backlash as "6mm at
15 mm from the rotation axis". The notebook's own readings (6 and 5 divisions
of 0.01 mm) and `calib:12` both give **0.06 mm**; 6 mm at 15 mm would be about
22°.

**How compensation is applied:**

- **Axis firmware.** On a reversal of R, it first moves 4 extra steps in the new
  direction at 50 steps/s, then restores the logical position, so logged
  positions are unaffected (`axis:46`, `:334-361`).
- **Off after every reset.** `backlash_on` defaults to false (`axis:45`).
  Enable it with `backlash on` (`terminal.py:1290-1295`).
- **Calibration sketch.** It always applies compensation (`calib:46-55`).

### 4.3 Motion parameters and reference

- **Acceleration** 40 °/s² (`axis:87`, `:267`).
- **Speed.** Maximum 20 °/s at start-up (`axis:266`), replaced by the commanded
  speed on every move (`axis:365`). Cap 90 °/s = 1 454 steps/s (`axis:43`,
  `:51`).
- **No endstop and no physical homing.** `HOME_AXIS` and `SET_ZERO` only zero
  the counter wherever R stands (`axis:392-396`, `:420-423`).

**TODO:**

- **Physical zero reference for R.** Define one (a scribed mark, a dowel, or
  preferably a reference switch) and the procedure for zeroing to it. Needed:
  a photo of the mark and a repeatability measurement.
- **Stage details.** Gear type (bought or printed), module, tooth counts,
  material, output bearing, how the phantom mounts, any mechanical hard stops,
  and whether cables limit rotation.

## 5. Driver wiring and current setting

**Established** (details in [`pinout.md`](pinout.md)):

- **Driver.** One CL57T closed-loop driver per axis (`axis:4`, `:29-35`).
- **Step and direction.** PUL and DIR are driven by AccelStepper in `DRIVER`
  mode with no pin inversion (`axis:90-92`, `:259-261`).
- **Enable.** ENA is written LOW once at start-up under the comment "Enable
  Drivers" and never changed (`axis:256-257`).
- **Alarms.** ALM from the H and V drivers goes to A0 and A1 with
  `INPUT_PULLUP`; LOW = alarm (`axis:246`, `:249`, `:273`). There is no ALM
  input for R.
- **Pulse width.** `setMinPulseWidth()` is never called, so AccelStepper's
  default of 1 µs applies (`AccelStepper.cpp:202`, AccelStepper 1.64), plus
  `digitalWrite` overhead.

**TODO**, all needed before a rebuild can be commissioned:

- **Driver identity.** Manufacturer and hardware revision; the model
  designation alone does not identify them.
- **Microstep setting for each driver.** Record the DIP-switch positions. It
  must give 800 steps/mm on H and V together with the screw lead (§3.1), and it
  enters the steps/° of R (§4.1).
- **Current setting for each driver**, and the motor's rated current.
- **Closed-loop settings and encoder wiring.**
- **Signal wiring.** How PUL, DIR and ENA are wired to the opto inputs (to 5 V or
  to GND), which fixes whether ENA LOW really means "enabled"; and how the ALM
  output is wired and what polarity it has.
- **Signal timing.** Verify the step pulse width and the DIR set-up time with an
  oscilloscope against the driver's input timing specification.
- **Supply.** The supply voltage is **not determinable from the repository**
  ([`../docs/safety.md`](../docs/safety.md) §6.3). Also record supply current,
  fusing and wire gauges.

## 6. Temperature sensors and heating pads

### 6.1 Sensor placement

**Established:**

- **One sensor per pad, on its own bus.** One DS18B20 per pad, pad A on D2 and
  pad B on D3 (`heat:19-20`, `:45-48`). Only the first sensor on each bus is
  read (`heat:117-118`).
- **Internal sensor, external reference.** The DS18B20 measures an *internal*
  temperature; the surface is the *external* one. The calibration plot legend
  reads "Intern (DS18B20)" and "Extern (Testo 925)"
  ([`calibration/heating-pad-calibration.png`](calibration/heating-pad-calibration.png)),
  and the terminal converts between "inner" and "outer" temperatures
  (`terminal.py:53-64`).
- **The gradient grows with temperature.** The internal-minus-external gradient
  in the calibration session was 0.4 K at a 25.0 °C sensor reading and 4.7 K at
  51.3 °C (`calibration/heating-pad-calibration.csv`, rows 2 and 13).
- **The bus needs an external pull-up.** The OneWire library sets the data pin
  to plain `INPUT` ([`pinout.md`](pinout.md), pitfall 4).

**TODO:**

- **Sensor position.** Exact position and depth of each sensor relative to the
  pad and the phantom surface, and the thermal coupling (paste, adhesive,
  clamp). Needed: a sectional sketch or photo.
- **Which physical pad is A and which is B** (front or rear). The calibration
  was done on the front pad only ([`README.md`](README.md#thermal-calibration-provenance)).
- **Wiring.** Cable routing, strain relief and pull-up resistor value.
- **Fault response.** Verify that a detached sensor is noticed. The firmware
  cannot notice it ([`../docs/safety.md`](../docs/safety.md) G8).

### 6.2 Heating-pad mounting

**Established** (control, not construction):

| Parameter | Value | Source |
|---|---|---|
| Switching | MOSFET per pad, gate driven HIGH-active from D5 / D6 | `heat:21-22`, `:150-156` |
| Time-proportioning window | 1 000 ms | `heat:25` |
| PI gains | KP 0.15, KI 0.0025 (header comment says 0.005) | `heat:27-28`, `:3` |
| Integral clamp | 0…0.25 | `heat:29`, `:85` |
| Integration window | error below 10 °C | `heat:69` |
| Update rate | 1 Hz | `heat:116` |
| Cutout | sensor reading > 65 °C | `heat:24`, `:61` |
| Setpoint in use | 32 °C surface (33.94 °C at the sensor) in 8 blueprint heat steps | `blueprints/`; conversion `terminal.py:58-60` |

**TODO:**

- **Pads.** Type, size, voltage, power and maximum rated temperature.
- **Mounting.** Position on the phantom, adhesive or fixation, surface finish
  (the pads form part of the tracked surface), electrical connection and strain
  relief.
- **MOSFET stage.** Part, heat-sinking, gate resistor, and a gate pull-down
  ([`pinout.md`](pinout.md), pitfall 6).
- **Independent over-temperature cutout** on each pad, in series with its
  supply (recommended in [`../docs/safety.md`](../docs/safety.md) §8).

## 7. Homing and setting the working zero

### 7.1 Homing sequence for H and V

Implemented in `doHomingAxis()` (`axis:204-241`). Both axes home towards
positive (`HOMING_SIGN_H = HOMING_SIGN_V = +1`, `axis:82-83`).

| Phase | Motion | Speed | Ends when | Source |
|---|---|---|---|---|
| 0. Clear the switch | Only if the switch already reads triggered: move 8 mm away from it (`BACKOFF_MM + 5.0`) | 2 mm/s, 80 mm/s² | distance covered; neither the switch nor the alarms are checked | `axis:206-213`, `:76` |
| 1. Fast search | Towards the switch, constant speed with no ramp (`runSpeed`) | 10 mm/s | switch reads triggered continuously for 30 ms → next phase; 20 s → **fail** | `axis:215-217`, `:74`, `:78-79`, `:176-202` |
| 2. Fine approach, 2 repetitions | Back off until the switch reads released (30 ms); pause 100 ms; approach until triggered (30 ms) | 2 mm/s | each wait fails after 20 s | `axis:219-228`, `:75`, `:77` |
| 3. Set reference | Current position := +33.0 mm (H) or +62.0 mm (V) | — | — | `axis:230-231`, `:80-81` |
| 4. Go to working zero | Move to position 0 | up to 15 mm/s, 80 mm/s² | target reached; neither the switch nor the alarms are checked | `axis:233-239` |

**Notes:**

- **Alarm checks during the search.** While waiting on a switch (phases 1-2),
  homing fails if **either** the H or the V alarm input is LOW, whichever axis
  is homing (`axis:185`).
- **`BACKOFF_MM` is misleadingly named.** Its value, 3.0 mm, is used only in
  phase 0. The fine approach backs off until the switch releases, not by a
  fixed distance.
- **R is not homed.** `HOME_AXIS` on R zeroes it in place (`axis:392-396`).
- **Order.** `h all` homes V, then R, then H, after the confirmation prompt
  "Phantom aligned and all cables clear of the phantom?"
  (`terminal.py:1228-1245`).
- **The result is not reported.** Success and failure both return
  `COMMAND_DONE` (`axis:384-401`). Watch each homing physically.
- **Homing repeatability has not been measured.** TODO: home 10× with a dial
  gauge on the carriage at the working zero, and record the spread.

### 7.2 Working-zero convention

- **H:** 0 is **33.0 mm on the negative side of the H switch trigger point**
  (`axis:80`).
- **V:** 0 is **62.0 mm on the negative side of the V switch trigger point**,
  i.e. below it if positive V is up (`axis:81`).
- **R:** 0 is **wherever R stands when `h r` or `set r zero` is issued**
  (`axis:392-396`, `:420-423`).
- **Only the switches define the zero.** It is not a physical reference; it is
  "switch trigger point minus offset". Replacing, moving or re-adjusting a
  switch moves the working zero by the same amount.
- **The offsets are tuning values, not design constants.** Superseded sketches
  carry 61.0 mm for both axes
  (`270cdf5:firmware/arduino/src/oldDrives/firsttry_mitebox.ino:84`) and
  41.0 mm (H) / 62.5 mm (V)
  (`270cdf5:firmware/arduino/src/oldDrives/SURF_nanoAxis_v3/SURF_nanoAxis_v3.ino:54-55`).
- **Positions do not survive a reset.** Every reset of the axis Nano loses
  them; re-home after every terminal start
  ([`../docs/safety.md`](../docs/safety.md) G10).
- **Do not use `set h zero` or `set v zero` on a homed axis.** Either one moves
  the software-limit window ([`../docs/safety.md`](../docs/safety.md) G3).

**TODO:**

- **What the working zero means physically.** State where the phantom should be
  at H = V = R = 0: relative to the rig, the couch and the room isocentre or
  lasers. Record the procedure that was used to choose 33.0 and 62.0 mm.
- **How to re-derive the offsets on a rebuilt rig.** The blueprints assume the
  phantom is "correctly mounted and moved to zero position"
  (`blueprints/heating-off/ETD_QA_PoP_SingleCouchRotation.json:6`), but that
  position is defined nowhere.

## 8. First power-on checks

Do these on a new or rebuilt rig, with the phantom removed where noted. Keep
the means of removing driver power within reach throughout: there is no
emergency stop ([`../docs/safety.md`](../docs/safety.md) G1).

1. **Flash and label.** Flash `SURF_nanoAxis_v5` to the axis board and
   `SURF_nanoHeating_v4` to the heating board, with **driver and heater
   supplies off**. Label both boards and both USB cables. The sketches are not
   interchangeable ([`pinout.md`](pinout.md#cross-flashing-and-swapped-ports)).
2. **Trace D11** on the heating board and record its function
   ([`pinout.md`](pinout.md), pitfall 5).
3. **Heater gates in reset** (heater supply off, gate measured): hold the
   heating Nano in reset and check that D5 and D6 do not rise. Release reset:
   they must be LOW after `setup()` ([`pinout.md`](pinout.md), pitfall 6).
4. **Sensors.** Start the terminal and check that both pad temperatures read
   near room temperature. Unplug one sensor: its readout must drop to about
   −105.6 °C (−127 °C converted, `terminal.py:62-64`) and its pad must stay off
   (`heat:61`).
5. **Port assignment.** Before any axis command, confirm that the pad readout
   is not ≈2.99 °C (swapped ports) and that no simulation message appeared
   ([`../docs/safety.md`](../docs/safety.md) G6, G7).
6. **Endstop polarity.** With both slides away from their switches, the axis
   Nano's LED D13 must be dark. Press each switch by hand: D13 must light. If
   it is lit at rest, the wiring is normally open or broken. **Do not home**
   ([`pinout.md`](pinout.md), pitfall 1).
7. **Alarm inputs.** Confirm from the CL57T documentation how an alarm can be
   provoked safely, then verify that each H and V alarm pulls A0 or A1 LOW. The
   terminal does not show alarm bits, so observe the pin directly. An
   unconnected ALM wire reads "no alarm" ([`pinout.md`](pinout.md), pitfall 2).
8. **Enable polarity.** With the driver supply on, compare holding torque while
   the axis Nano is held in reset (pins floating) with torque after start-up
   (ENA LOW). Record which state enables the drivers
   ([`pinout.md`](pinout.md), pitfall 3).
9. **Record the driver data** in this document and in [`bom.csv`](bom.csv):
   supply voltage, driver current and microstep settings.
10. **Direction check, before any homing**, with each slide near mid-travel.
    Moves are accepted before homing, around the power-on position
    ([`../docs/safety.md`](../docs/safety.md) G3). Send `m h 1 1` and
    `m v 1 1`, and confirm the directions against §1. For R, first
    `set r zero`, then `m r 5 2`.
11. **Homing direction.** The fast search must move *towards* the switch. If
    an axis moves away from it, **remove driver power immediately**: the search
    otherwise continues for up to 20 s at 10 mm/s, up to 200 mm at the
    commanded speed (`axis:74`, `:78`). Correct it either with the DIR
    inversion (`setPinsInverted`, `axis:259-261`, which also flips the
    coordinate sign) or with `HOMING_SIGN_H` / `HOMING_SIGN_V` (`axis:82-83`),
    to suit the coordinate convention you want.
12. **Home each axis individually** (`h v`, then `h h`) with hands clear.
    Observe the fast approach, the two slow touches and the travel to zero.
    Then check that the free travel of §3.2 exists by jogging, slowly, to the
    software limits.
13. **Calibrate.** Repeat the backlash measurements (§3.3, §4.2), including V,
    and the steps/° measurement (§4.1), and record the results with dates in
    `docs/calibration/`.
14. **Heating.** Set one pad with `t a 32` and measure its surface with a
    reference thermometer. Compare with the model in
    [`README.md`](README.md#thermal-calibration-provenance), and repeat for the
    other pad; it has never been calibrated.
15. **Emergency stop**, once fitted: test it during a move at the highest speed
    you will use ([`../docs/safety.md`](../docs/safety.md) §8).
