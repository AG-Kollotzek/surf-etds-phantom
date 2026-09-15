# Toolchain

What this release was built and validated with. Before this document, none of
these versions were recorded anywhere in the project.

A caveat that applies to the whole page: versions were read from the
**development machine** (macOS) on 2026-09-15. The archived campaigns were
recorded on a separate **Windows measurement laptop**, and firmware may have
been flashed from either machine. Where the laptop's versions could differ,
that is stated.

## Measurement terminal (Python)

| Component | Validated version | Constraint | Source |
|---|---|---|---|
| CPython | 3.13.0 | `requires-python >= 3.11` | `.venv/pyvenv.cfg` |
| PySide6 | 6.11.2 | `>=6.5,<7` | `requirements.lock.txt` |
| matplotlib | 3.11.1 | `>=3.7,<4` | `requirements.lock.txt` |
| pyserial | 3.5 | `>=3.5,<4` | `requirements.lock.txt` |
| numpy | 2.5.2 | transitive (matplotlib) | `requirements.lock.txt` |
| tkinter | bundled with CPython | — | used only by `software/surf_terminal/tools/backlash_calculator.py` |

- `requirements.txt` gives the supported ranges; `requirements.lock.txt` is the
  exact environment.
- The PySide6 upper bound is deliberate: `terminal.py` uses short-form Qt enum
  access (`QMessageBox.Yes`, `QDialogButtonBox.Ok`) that a major version may
  remove.
- Python 3.11 and 3.12 are declared supported and are exercised by CI
  (`.github/workflows/ci.yml`), but no archived campaign was recorded with them.
- On Linux, `tkinter` is a separate OS package (e.g. `python3-tk`) and cannot be
  installed from PyPI.
- The Python version used on the measurement laptop is **not recorded**.

## Firmware (Arduino)

| Component | Version | Source |
|---|---|---|
| Board | Arduino Nano (both controllers) | `firmware/axis/SURF_nanoAxis_v5/SURF_nanoAxis_v5.ino:4` |
| FQBN | `arduino:avr:nano` | Arduino IDE 2 settings on the development machine |
| CPU / bootloader option | **not determinable** | see below |
| Arduino AVR core | 1.8.7 | `~/Library/Arduino15/packages/arduino/hardware/avr/` |
| AccelStepper | 1.64 | installed `library.properties` |
| OneWire | 2.3.8 | installed `library.properties` |
| DallasTemperature | 4.0.6 | installed `library.properties` |

Library use by sketch:

| Sketch | Libraries |
|---|---|
| `firmware/axis/SURF_nanoAxis_v5` | AccelStepper |
| `firmware/heating/SURF_nanoHeating_v4` | OneWire, DallasTemperature |
| `firmware/tools/rotation_calibration` | AccelStepper |

**CPU option.** Nano clones and older genuine boards need
`arduino:avr:nano:cpu=atmega328old` (legacy bootloader); current genuine boards
use the default `cpu=atmega328`. The IDE settings record `arduino:avr:nano`
with no CPU option, which means either the default was used or the option was
not persisted. Which option the boards need is not recorded.

**Library versions on the measurement laptop are not recorded.** AccelStepper
behaviour relevant to the ground truth (step timing, `currentPosition()`
semantics) has been stable across the 1.6x series, but the version that built
the firmware for any specific campaign cannot be established from the archive.

Build:

```bash
arduino-cli core install arduino:avr@1.8.7
arduino-cli lib install "AccelStepper@1.64" "OneWire@2.3.8" "DallasTemperature@4.0.6"
arduino-cli compile --fqbn arduino:avr:nano firmware/axis/SURF_nanoAxis_v5
arduino-cli compile --fqbn arduino:avr:nano firmware/heating/SURF_nanoHeating_v4
```

Licensing note: AccelStepper is GPL-3.0 (or commercial), which is why
`firmware/` is GPL-3.0-or-later. See `firmware/README.md`.

## MATLAB viewers

| Component | Requirement | Reason |
|---|---|---|
| MATLAB | **R2020a or later** (inferred) | `exportgraphics` was introduced in R2020a |
| Toolboxes | none identified | only base-MATLAB functions are called |

Features used by `matlab/ETDCombinedJSONCSVViewerApp.m`: `uifigure`,
`uigridlayout`, `uitab`, `uiaxes`, `jsondecode`, `readtable`, `exportgraphics`.
`matlab/tests/test_connection.m` uses `functiontests`.

The MATLAB release actually used is **not recorded**. The R2020a floor is
inferred from the newest function called, not from a test run.

`matlab/TestUnitApp.m` and `matlab/start_app.m` are early scaffolding. They
speak an ASCII protocol (`writeline`, `"STAT?"`) that no firmware in this
repository implements, so they cannot talk to the current hardware.

## Continuous integration

| Workflow | Checks |
|---|---|
| `ci.yml` | Install on Python 3.11/3.12/3.13, byte-compile, import under `xvfb`, `ruff` correctness lint |
| `arduino-build.yml` | Compile all three sketches for `arduino:avr:nano` |
| `validate.yml` | Every JSON parses; blueprints validate against `blueprints/schema/blueprint.schema.json`; protocols carry no un-pseudonymised operator names; `CITATION.cff` is valid |

The workflows were written during release preparation and **have not yet run
on GitHub**. Their first run will be the first time this project is built from a
clean checkout.
