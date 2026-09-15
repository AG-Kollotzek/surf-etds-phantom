# SURF Test Unit

**A low-cost 3-DOF motion phantom for surface-guided radiotherapy QA.**

Three motorised axes — a horizontal slide (H), a vertical slide (V) and a
rotation stage (R) — move a phantom through scripted trajectories while the
controller logs the commanded pose at ~9.3 Hz. Two PI-controlled heating pads
bring the phantom surface to a skin-like temperature. The logged pose serves as
ground truth for evaluating the tracking accuracy of a surface-guidance system.

This repository is the **acquisition** half of the project: firmware,
measurement software, hardware documentation, the measurement-sequence
definitions, and the phantom-side ground-truth data. The evaluation chain and
the tracking-system exports live in the companion repository
[`SURF_DataAnalysis`](https://github.com/tim-buck/SURF_DataAnalysis).

> **Neither repository alone contains a complete measurement.** The phantom
> ground truth is here; the tracker output is there.

---

## ⚠️ Read before use

This is **research hardware and research software**. It is **not a medical
device**, has not been assessed under Regulation (EU) 2017/745, and carries no
CE mark. It must not be used in patient treatment, for clinical
decision-making, or on patient-bearing equipment.

It drives three stepper axes and two heated pads. **There is no hardware
emergency stop**, and the rotation axis has no endstop. Read
[`docs/safety.md`](docs/safety.md) and [`docs/disclaimer.md`](docs/disclaimer.md)
before powering anything on.

Several failure modes in the current acquisition chain are **silent** — a move
rejected by the firmware limit check is still reported to the PC as completed,
and a disconnected controller causes the software to log plausible-looking but
fabricated data. These are catalogued in
[`docs/known-issues.md`](docs/known-issues.md). Anyone reusing the archived
data should read that file first.

---

## Repository layout

| Path | Contents | Licence |
|---|---|---|
| `firmware/` | Arduino sketches: axis control, heater control, a calibration tool | GPL-3.0-or-later |
| `software/surf_terminal/` | PySide6 measurement terminal — runs blueprints, logs data | MIT |
| `blueprints/` | Measurement sequences (JSON DSL) + schema | MIT |
| `matlab/` | MATLAB viewer apps for inspecting tracking and telemetry data | MIT |
| `hardware/` | Pinout, bill of materials, assembly notes, thermal calibration | MIT |
| `data/raw/` | Ground-truth measurement campaigns, 2025-12 – 2026-08 | CC-BY-4.0 |
| `docs/` | Protocol, data dictionary, safety, design notes, known issues | CC-BY-4.0 |

## Documentation

| Document | What it covers |
|---|---|
| [`docs/safety.md`](docs/safety.md) | Hazards, existing protections, and the gaps in them |
| [`docs/disclaimer.md`](docs/disclaimer.md) | Research-use statement, trademark/non-affiliation |
| [`docs/known-issues.md`](docs/known-issues.md) | Defect register for the acquisition chain |
| [`docs/blueprint-format.md`](docs/blueprint-format.md) | The measurement-sequence DSL |
| [`docs/serial-protocol.md`](docs/serial-protocol.md) | PC ↔ Arduino wire protocol |
| [`docs/data-dictionary.md`](docs/data-dictionary.md) | Every column of every file family |
| [`docs/toolchain.md`](docs/toolchain.md) | Python, Arduino and MATLAB versions |
| [`docs/design-notes/kinematics-rationale.md`](docs/design-notes/kinematics-rationale.md) | Why 3 DOF, and what 3 DOF cannot support |
| [`docs/calibration/reference-geometry.md`](docs/calibration/reference-geometry.md) | Geometric imperfections the kinematic model lacks, and how sensitive the kV cross-validation is at each position |
| [`data/README.md`](data/README.md) | Campaign inventory and dataset reuse notes |

## Quick start

### Measurement terminal

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m surf_terminal            # from the software/ directory
```

Serial ports are currently **hard-coded per platform** near the top of
`software/surf_terminal/terminal.py` and must be edited for your machine
(see `KI-16` in the known-issues register).

The terminal writes `data/<YYYY-MM-DD>/` **relative to its working directory**.
The campaigns archived here were moved to `data/raw/` during release
preparation; the write path in the code was deliberately left unchanged.

### Firmware

```bash
arduino-cli compile --fqbn <board-fqbn> firmware/axis/SURF_nanoAxis_v5
arduino-cli upload  --fqbn <board-fqbn> -p <port> firmware/axis/SURF_nanoAxis_v5
```

See [`docs/toolchain.md`](docs/toolchain.md) for the board FQBN and library
versions.

## Axis envelope

| Axis | Range | Max speed | Resolution | Notes |
|---|---|---|---|---|
| H (horizontal) | −45 … +25 mm | 50 mm/s | 800 steps/mm | NC endstop, homed |
| V (vertical) | −35 … +50 mm | 50 mm/s | 800 steps/mm | NC endstop, homed; couples Z-shift with pitch |
| R (rotation) | −30 … +120° | 90 °/s | 16.156 steps/° | **No endstop.** Zeroed in place; 1:2 bevel gear with backlash |

Limits are enforced in firmware only — the PC applies no limit check to
blueprint moves.

## Licensing

The repository is deliberately **not** under a single licence:

- **MIT** — default for everything, including `software/`, `blueprints/`, `matlab/`, `hardware/`.
- **GPL-3.0-or-later** — `firmware/`. The axis sketch links **AccelStepper**, which is GPL-or-commercial; the free option makes the derived work GPL.
- **CC-BY-4.0** — `data/` and `docs/`. Measurements and documentation, not software.

Full texts are in [`LICENSES/`](LICENSES/).

"ExacTrac", "Brainlab" and "Varian" are trademarks of their respective owners
and are used nominatively. Neither vendor endorses or is affiliated with this
work.

## Citing

See [`CITATION.cff`](CITATION.cff), or use GitHub's "Cite this repository".

## Contributing

See [`CONTRIBUTING.md`](CONTRIBUTING.md). Changes to the firmware or the motion
path require bench validation on the actual hardware.

Documentation and code are in English; operator-facing GUI strings and
blueprint prompts are deliberately kept in German, because they are read at the
console by clinical staff during a measurement.
