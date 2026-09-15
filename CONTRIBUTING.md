# Contributing

This is research software for a specific piece of laboratory hardware. Patches
are welcome, but the constraints below are not negotiable — this code moves a
mass inside a radiotherapy treatment room.

## Before you open a pull request

- **Anything touching `firmware/` or the motion path in `software/` must be
  bench-validated on the actual hardware before it is merged.** Say in the PR
  what you tested, on which axes, and what you observed. A change that only
  compiles is not a tested change.
- Read [`docs/known-issues.md`](docs/known-issues.md) first. Several known
  defects are deliberately left unfixed pending bench time; if you are fixing
  one, reference its ID.
- Do not change the on-disk data formats without also updating
  [`docs/data-dictionary.md`](docs/data-dictionary.md). The archived campaigns
  are a published dataset and downstream analysis depends on the schema.

## Language

- Documentation, code comments, identifiers and commit messages: **English**.
- Operator-facing GUI strings and blueprint `checkpoint` prompts: **German**,
  deliberately. These are read at the console by clinical staff mid-measurement
  in a German-speaking department. Do not translate them.

## Measurement data

Do not commit measurement data that has not been through the release checks:
the `personal` field in `_log.json` and `Messteam` in `_log.txt` must carry
operator codes, not names. See [`CONTRIBUTORS.md`](CONTRIBUTORS.md).

Do not commit generated plots (`plot_*.png`) — they are regenerable from the
raw CSV and are git-ignored.

## Reporting a problem

Open an issue. For anything with a safety dimension, say so in the title and
describe the hardware state you observed it in.
