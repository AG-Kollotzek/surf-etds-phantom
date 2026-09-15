# Firmware

Two Arduino Nano controllers, each speaking a small binary protocol to the
measurement terminal over USB serial. See [`docs/serial-protocol.md`](../docs/serial-protocol.md).

| Directory | Sketch | Role |
|---|---|---|
| `axis/SURF_nanoAxis_v5/` | `SURF_nanoAxis_v5.ino` | Motion control for the horizontal (H), vertical (V) and rotation (R) axes |
| `heating/SURF_nanoHeating_v4/` | `SURF_nanoHeating_v4.ino` | PI temperature control of the two heating pads |
| `tools/rotation_calibration/` | `rotation_calibration.ino` | Bench sketch used to determine `STEPS_PER_DEG` and the rotary backlash constant |

## Licence

**This directory is licensed GPL-3.0-or-later**, unlike the rest of the
repository (MIT). The axis firmware links **AccelStepper**, which is offered
under GPL-3.0 or a commercial licence; using the free option requires the
derived work to be GPL as well. See [`LICENSE`](LICENSE) and the licensing
section of the top-level [`README.md`](../README.md).

## Building

Toolchain versions, board FQBN and library versions: [`docs/toolchain.md`](../docs/toolchain.md).

```bash
arduino-cli compile --fqbn <board-fqbn> firmware/axis/SURF_nanoAxis_v5
arduino-cli upload  --fqbn <board-fqbn> -p <port> firmware/axis/SURF_nanoAxis_v5
```

## Before you flash anything

Read [`docs/safety.md`](../docs/safety.md) and [`docs/known-issues.md`](../docs/known-issues.md)
first. This firmware moves a mass inside a treatment room; several of its
failure modes are silent.
