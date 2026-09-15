# Changelog

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased] — release preparation

Restructuring and documentation pass ahead of the first public release. **No
functional change to the firmware or to the measurement path.**

### Added
- Licence set: MIT (default), GPL-3.0-or-later (`firmware/`, required by
  AccelStepper), CC-BY-4.0 (`data/`). `CITATION.cff`, `CONTRIBUTORS.md`,
  `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`.
- Documentation that did not previously exist anywhere: serial protocol,
  blueprint DSL specification and JSON Schema, data dictionary and dataset
  README, hardware pinout, a bill-of-materials skeleton and assembly notes,
  safety and disclaimer, toolchain, a known-issues register (23 entries), and
  the design rationale for the 3-DOF kinematics.
- `docs/calibration/reference-geometry.md`: the phantom geometry missing from the
  kinematic model (tilt-axis yaw ≈ 2.1°, rotation-axis offset ≈ 1.3 mm), the
  documented phantom setup, and the sensitivity of kV cross-validation at each
  imaging position.
- `data/raw/2026-03-10/runs.csv` — the run-to-condition mapping for the paper
  campaign, which previously existed only as a hard-coded dict in the analysis
  repository.
- `data/etds_qa_2026_config.json` — the validated 20-entry run/ExacTrac linkage
  table, replacing a truncated 8-entry copy that was not valid JSON.
- `pyproject.toml`, pinned `requirements.txt` and `requirements.lock.txt`,
  `.gitattributes`, CI workflows.
- `main()` entry point in the measurement terminal (packaging only; the
  script-invocation behaviour is unchanged).

### Changed
- Repository restructured: `firmware/{axis,heating,tools}/`,
  `software/surf_terminal/`, `blueprints/{qa,pop,heating-off}/`, `data/raw/`,
  `matlab/`, `hardware/`, `docs/`.
- Measurement data moved from `firmware/measurement_pc/data/` to `data/raw/`.
  **The terminal still writes `data/<YYYY-MM-DD>/` relative to its working
  directory** — this was not changed, to avoid altering behaviour mid-campaign.
- Operator names in measurement protocols replaced with role codes (`QMP1`, `Student1` to `Student3`).
- Six protocol files re-encoded: UTF-8-through-latin-1 mojibake repaired.
- Line endings normalised to LF across all text and data files.
- Shell-hostile data filenames (spaces, parentheses, umlauts) renamed.

### Removed
- Superseded firmware (`oldDrives/`, 11 sketches) and superseded terminals
  (`ancient_terminals/`, 3 scripts). Retained in git history.
- The nested duplicate `matlab_app/matlab_app/`.
- `data/2026-03-10.zip` (a byte-identical duplicate of the adjacent directory
  plus `__MACOSX` resource forks), tracked `plot_*.png`, tracked `.idea/`,
  the empty `config.h`, scaffolding scripts, and 18 `.gitkeep` placeholders.
- `docs/PoPargumentation&blueprints.txt` — replaced by
  `docs/design-notes/kinematics-rationale.md`.
