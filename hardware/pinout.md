# Pin assignment

This is the only pinout record for the SURF Test Unit. It was **reconstructed
from the firmware source**, not from the physical wiring: no schematic, wiring
diagram, terminal plan or photograph exists in the repository.

Sources:

- Axis controller: [`firmware/axis/SURF_nanoAxis_v5/SURF_nanoAxis_v5.ino`](../firmware/axis/SURF_nanoAxis_v5/SURF_nanoAxis_v5.ino) (cited as `axis:<line>`)
- Heating controller: [`firmware/heating/SURF_nanoHeating_v4/SURF_nanoHeating_v4.ino`](../firmware/heating/SURF_nanoHeating_v4/SURF_nanoHeating_v4.ino) (cited as `heat:<line>`)
- PC side: [`software/surf_terminal/terminal.py`](../software/surf_terminal/terminal.py) (cited as `terminal.py:<line>`)
- Superseded sketches are cited as `270cdf5:<path>:<line>`. They were removed
  from the working tree during release preparation and remain readable with
  `git show 270cdf5:<path>`.

German source comments are quoted in English translation.

## Boards and host connection

| Board | Sketch | Host port as hard-coded (Windows / macOS) | Serial |
|---|---|---|---|
| Arduino Nano, axis controller | `SURF_nanoAxis_v5.ino` | `COM3` / `/dev/cu.usbserial-120` (`terminal.py:30-39`) | 115200 baud (`axis:254`, `terminal.py:43`) |
| Arduino Nano, heating controller | `SURF_nanoHeating_v4.ino` | `COM4` / `/dev/cu.usbserial-140` (`terminal.py:30-39`) | 115200 baud (`heat:102`) |

Board type: `axis:4` ("Hardware: Arduino Nano, CL57T Drivers") and
[`firmware/README.md`](../firmware/README.md) line 3. Whether the boards are
genuine or clones (which changes the bootloader option) is not recorded; see
[`docs/toolchain.md`](../docs/toolchain.md).

Neither firmware identifies itself to the PC. The axis protocol defines
`HELLO = 0` (`axis:12`) but its handler does nothing (`axis:308`), and the
heating firmware has no identification command. The terminal assigns the boards
purely by port name. **The two boards are not interchangeable** (see
[Cross-flashing](#cross-flashing-and-swapped-ports)): label both boards and both
USB cables.

## Axis controller (`SURF_nanoAxis_v5.ino`)

Axis IDs: H = 0, V = 1, R = 2 (`axis:22-26`).

| Arduino pin | Signal | Direction / mode | Level as coded | Target device | Source |
|---|---|---|---|---|---|
| D0 | Serial RX | input (UART) | — | USB-serial link to PC | `axis:254` |
| D1 | Serial TX | output (UART) | — | USB-serial link to PC | `axis:254` |
| D2 | `PIN_PUL_H` | `OUTPUT` | step pulses from AccelStepper `DRIVER` mode, not inverted | CL57T driver, H axis: PUL input | `axis:29`, `:90`, `:245`, `:259` |
| D3 | `PIN_DIR_H` | `OUTPUT` | not inverted | CL57T driver, H axis: DIR input | `axis:29`, `:90`, `:245`, `:259` |
| D4 | `PIN_ENA_H` | `OUTPUT` | written `LOW` once in `setup()` ("Enable Drivers"), never changed | CL57T driver, H axis: ENA input | `axis:29`, `:245`, `:256-257` |
| D5 | `PIN_END_H` | `INPUT_PULLUP` | `HIGH` = triggered (code; comments disagree, see below) | H endstop switch, normally closed, to GND | `axis:30`, `:126-128`, `:246` |
| A0 | `PIN_ALM_H` | `INPUT_PULLUP` (used as digital input) | `LOW` = alarm | CL57T driver, H axis: ALM output | `axis:30`, `:168`, `:185`, `:246`, `:273` |
| D6 | `PIN_PUL_V` | `OUTPUT` | as D2 | CL57T driver, V axis: PUL input | `axis:32`, `:91`, `:248`, `:260` |
| D7 | `PIN_DIR_V` | `OUTPUT` | as D3 | CL57T driver, V axis: DIR input | `axis:32`, `:91`, `:248`, `:260` |
| D8 | `PIN_ENA_V` | `OUTPUT` | as D4 | CL57T driver, V axis: ENA input | `axis:32`, `:248`, `:257` |
| D9 | `PIN_END_V` | `INPUT_PULLUP` | `HIGH` = triggered | V endstop switch, normally closed, to GND | `axis:33`, `:126-128`, `:249` |
| A1 | `PIN_ALM_V` | `INPUT_PULLUP` (used as digital input) | `LOW` = alarm | CL57T driver, V axis: ALM output | `axis:33`, `:169`, `:185`, `:249`, `:273` |
| D10 | `PIN_PUL_R` | `OUTPUT` | as D2 | CL57T driver, R axis: PUL input | `axis:35`, `:92`, `:251`, `:261` |
| D11 | `PIN_DIR_R` | `OUTPUT` | as D3 | CL57T driver, R axis: DIR input | `axis:35`, `:92`, `:251`, `:261` |
| D12 | `PIN_ENA_R` | `OUTPUT` | as D4 | CL57T driver, R axis: ENA input | `axis:35`, `:251`, `:257` |
| — | *(no R endstop)* | — | — | **none: R has no endstop** | no pin defined; `HOME_AXIS` on R only zeroes (`axis:392-396`) |
| — | *(no R alarm)* | — | — | **none: the R driver's ALM output is not monitored** | no pin defined; alarm checks read only A0/A1 (`axis:185`, `:273`) |
| D13 | `PIN_LED` | `OUTPUT` | `HIGH` while `END_H` or `END_V` reads triggered | on-board LED | `axis:36`, `:130-135`, `:252`, `:278` |
| A2-A5 | unused | — | — | free, digital-capable | not referenced |
| A6, A7 | unused | — | — | free, analogue input only on the Nano (no digital mode, no pull-up) | not referenced |

The endstops are used **only for homing and for the LED**. `MOVE_AXIS` never
reads them (`axis:310-379`), so they are reference switches, not limit
switches: a triggered endstop does not stop a normal move. Each linear axis has
one switch, at the end approached by homing (`HOMING_SIGN_H = HOMING_SIGN_V = +1`,
`axis:82-83`). There is no switch at the negative end of H or V.

## Heating controller (`SURF_nanoHeating_v4.ino`)

| Arduino pin | Signal | Direction / mode | Level as coded | Target device | Source |
|---|---|---|---|---|---|
| D0 | Serial RX | input (UART) | — | USB-serial link to PC | `heat:102` |
| D1 | Serial TX | output (UART) | — | USB-serial link to PC | `heat:102` |
| D2 | `ONE_WIRE_PIN_A` | set by the OneWire library: plain `INPUT`, no internal pull-up (OneWire 2.3.8, `OneWire.cpp:164`) | OneWire bus | DS18B20 sensor, pad A (one sensor on the bus, index 0) | `heat:19`, `:45-46`, `:117` |
| D3 | `ONE_WIRE_PIN_B` | as D2 | OneWire bus | DS18B20 sensor, pad B (index 0) | `heat:20`, `:47-48`, `:118` |
| D5 | `MOSFET_A_PIN` | `OUTPUT`, written `LOW` in `setup()` | `HIGH` = heater on; time-proportioned in a 1000 ms window | MOSFET switch, heating pad A | `heat:21`, `:25`, `:41`, `:62`, `:104-105`, `:150-152` |
| D6 | `MOSFET_B_PIN` | `OUTPUT`, written `LOW` in `setup()` | `HIGH` = heater on; as D5 | MOSFET switch, heating pad B | `heat:22`, `:25`, `:42`, `:62`, `:104-105`, `:154-156` |
| D11 | *(unnamed)* | `OUTPUT`, written `HIGH` in `setup()`, never changed | constant `HIGH` | **undocumented**, no comment in any version | `heat:103` |
| D4, D7-D10, D12, D13, A0-A7 | unused | — | — | free (D13 is the on-board LED) | not referenced |

Notes:

- **Heater polarity.** "HIGH = on" follows from the code: the fault branch
  switches a pad off with `digitalWrite(h.pin, LOW)` (`heat:62`), and the
  soft-PWM writes `HIGH` during the on-fraction of each window (`heat:151-152`,
  `:155-156`). A superseded sketch states it explicitly:
  `MOSFET_ACTIVE_HIGH = true` (`270cdf5:firmware/arduino/src/oldDrives/SURF_nanoHeating_v2.1.ino:31`).
  D5 and D6 are hardware-PWM pins, but the firmware does not use `analogWrite`.
- **Which pad is A and which is B** (front or rear) is not recorded anywhere.
  The thermal calibration was made on the *front* pad; see
  [`README.md`](README.md#thermal-calibration-provenance).
- **Sensor identity.** The sensor type appears in the calibration file header
  (`calibration/heating-pad-calibration.csv`, line 1: `Ist (DS18B20)`) and is
  consistent with the DallasTemperature library (`heat:9`). The firmware reads
  only `getTempCByIndex(0)` per bus (`heat:117-118`), so it assumes exactly one
  sensor per bus. Whether the sensors run in normal or parasite power mode is
  not recorded.

## Contradictions and pitfalls found in the source

### 1. Endstop polarity: the comments contradict the code

| Location | Text (translated where German) | Says |
|---|---|---|
| `axis:5` | "Status: Fixed Homing + Safety Limits + **ActiveLow Endstops**" | LOW = triggered |
| `axis:125` | "IMPORTANT: set to LOW here, because your switches are active low (INPUT_PULLUP)" | LOW = triggered |
| `axis:127`, trailing comment | "LOW = pressed (with switch to GND)" | LOW = triggered |
| `axis:127`, **code** | `return digitalRead(pinEnd) == HIGH;` | **HIGH = triggered** |

**Verdict: the code is correct for the switches actually fitted, and the
comments are stale.** With `INPUT_PULLUP` (`axis:246`, `:249`) and a normally
closed (NC) contact between pin and GND, the pin reads LOW at rest and HIGH when
the contact opens. Two superseded sketches record exactly this wiring:

- `270cdf5:firmware/arduino/src/oldDrives/firsttry_mitebox.ino:23-24`: "Endstops: wired NC: rest = LOW, triggered = HIGH"
- `270cdf5:firmware/arduino/src/oldDrives/SURF_nanoAxis_v3/SURF_nanoAxis_v3.ino:204`: "Since you use NC switches (HIGH = pressed/interrupted), we check for HIGH"

**Pitfall for rebuilders:** anyone who follows the comments and fits normally
open (NO) switches, and any installation with a broken or unplugged endstop
wire, reads HIGH = "triggered" at rest. The quick check is the on-board LED:
with the slide away from the switch, **D13 must be dark**. If it is lit, do not
home. Homing a switch that reads triggered at rest proceeds as follows:

1. It "clears" the switch by moving 8 mm away from it (`BACKOFF_MM + 5.0`, `axis:76`, `:206-213`).
2. The fast search sees "triggered" at once and accepts it after the 30 ms debounce (`axis:79`, `:194-195`, `:216-217`).
3. The fine phase backs away at 2 mm/s, waiting for a release that never comes, until the 20 s timeout (`axis:75`, `:78`, `:221-222`).

Nominally that is 8 mm + 2 mm/s × 20 s ≈ 48 mm towards the negative end, where
there is no switch. No software limit applies during homing, and the terminal
cannot tell the failure apart from success, because `COMMAND_DONE` is sent
either way (`axis:399-401`). See [`docs/safety.md`](../docs/safety.md).

### 2. Driver alarm inputs fail open

`LOW` = alarm (`axis:168-169`, `:185`, `:273`) with `INPUT_PULLUP`, so a
disconnected ALM wire reads `HIGH` = "no alarm". The CL57T's ALM output stage
and its configured polarity are not documented in the repository. A superseded
sketch comments "CL57T ALM is LOW on fault"
(`270cdf5:firmware/arduino/src/oldDrives/SURF_nanoAxis_v3/SURF_nanoAxis_v3.ino:210`),
and an earlier one carries only an "ALM level (autodetect)" placeholder
(`270cdf5:firmware/arduino/src/oldDrives/firsttry_mitebox.ino:101-103`). The R
driver has no ALM input at all (also noted as "R has no
endstop/alarm" at `270cdf5:firmware/arduino/src/oldDrives/SURF_nanoAxis_v3/SURF_nanoAxis_v3.ino:19`).
The firmware reports both alarm bits in its status byte (`axis:166-172`), but
the terminal reads that byte and discards it (`_stat`, `terminal.py:473`).

### 3. ENA is set once and never released

All three ENA pins are written `LOW` in `setup()` under the comment "Enable
Drivers" (`axis:256-257`), and nothing ever writes them again. Neither
`STOP_ALL` (`axis:429-432`) nor a driver alarm (`axis:273-275`) disables a
driver. A superseded sketch uses the same convention,
`ENABLE_ACTIVE_LEVEL = LOW` (`270cdf5:firmware/arduino/src/oldDrives/firsttry_mitebox.ino:79`).
Whether LOW actually means "enabled" depends on how the CL57T ENA input is
wired, and that is not documented. From power-up or reset until `setup()` runs,
all these pins are high-impedance. How the drivers behave with floating
PUL/DIR/ENA inputs has not been checked.

### 4. OneWire buses need an external pull-up that is not documented

The OneWire library sets the data pin to plain `INPUT` (OneWire 2.3.8,
`OneWire.cpp:164`), so each bus needs an external pull-up resistor to work. Its
value and location are not recorded.

### 5. Heating pin D11 is driven HIGH with no explanation

`pinMode(11,OUTPUT); digitalWrite(11,HIGH);` (`heat:103`) has no comment, and
the same two lines appear, also uncommented, in the superseded heating sketches
v2 and v3 (`270cdf5:firmware/arduino/src/oldDrives/SURF_nanoHeating_v2/SURF_nanoHeating_v2.ino:95-96`).
Its purpose cannot be established from the repository.

### 6. Heater gates are undefined while the heating Nano is in reset

From power-up or reset until `heat:104-105` runs, D5 and D6 are high-impedance.
Whether the pads stay off during that interval, and while the Nano is
unpowered, depends on a gate pull-down on the MOSFET stage. None is documented.

### 7. Header comment and code disagree on the integral gain

`heat:3` says "Ki=0.005"; the code uses `KI = 0.0025f` (`heat:28`). This is not
a pin issue, but it is the kind of drift that makes the comments in these
sketches unreliable as documentation.

## Cross-flashing and swapped ports

The two sketches reuse D2, D3, D5, D6 and D11 for unrelated functions.

- **Axis sketch flashed onto the heating board:** D5, the MOSFET A gate, becomes
  `END_H` with `INPUT_PULLUP`. The internal pull-up can raise the gate far
  enough to energise pad A with no temperature control at all; whether it does
  depends on the undocumented gate pull-down (pitfall 6). D6, the MOSFET B gate,
  becomes `PUL_V` and is pulsed whenever V is commanded.
- **Heating sketch flashed onto the axis board:** D5, the H endstop wired to
  GND through a normally closed contact, is driven as an output. Whenever it is
  driven HIGH it is shorted to ground through the closed switch. D6 (`PUL_V`)
  and D11 (`DIR_R`) are driven by the heater logic.
- **Swapped USB ports** (correct firmware on each board, but the boards are on
  each other's port names): the command bytes collide, because `MOVE_AXIS` = 1
  = `CMD_SET_A` and `HOME_AXIS` = 2 = `CMD_SET_B` (`axis:13-14`, `heat:13-14`).
  - An axis move to any positive target of 26 steps or more, sent to the heating
    board, sets pad A's setpoint to the 65 °C clamp.
  - Some heater setpoints, sent to the axis board, decode as homing moves, as
    R zeroing, or as `SET_ZERO` on H.

  Both are worked through in [`docs/safety.md`](../docs/safety.md#g7-swapped-serial-ports-cross-command-the-two-controllers).

Label both boards and both cables, and after any re-cabling check the port
assignment before sending a command.
