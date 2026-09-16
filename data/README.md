# SURF Test Unit: ground-truth measurement data

This directory holds the phantom side of every measurement made with the SURF
Test Unit, a 3-DOF motion phantom (horizontal slide H, vertical slide V,
rotation R, two heated pads). The phantom was used to validate a Brainlab
ExacTrac Dynamic (ETD) surface-guidance system at Tirol Kliniken / LKI
Innsbruck. For every run, the logging software recorded the axis positions as
counted by the motion controller. From February 2026 it also recorded pad
temperatures and setpoints, and later campaigns add sphere-detection readouts
and a measurement protocol.

> **Neither repository alone holds a complete measurement.** The phantom ground
> truth is here. The tracker output, the ETD exports `TrackingResult_*.json`,
> is **not** in this repository; it lives with the evaluation code (see
> [Where the tracker output is](#where-the-tracker-output-is)).

**Column-by-column documentation, format history and reuse caveats:**
[`../docs/data-dictionary.md`](../docs/data-dictionary.md). Read its §9 before
using any file.

## Layout

| Path | Contents |
|---|---|
| `raw/<YYYY-MM-DD>/` | One recording day, exactly as written by the terminal. |
| `raw/<YYYY-MM>-pilot/` | Development data collected over several days. |
| `raw/2026-03-10/runs.csv` | Run-to-condition index of the paper campaign. |
| `etds_qa_2026_config.json` | Validated linkage of 20 end-position scans to phantom CSVs and ETD exports (2026-07-15, 2026-07-29, 2026-08-06). |
| `LICENSE` | CC BY 4.0 for everything in `data/`. |

## Campaign inventory

"Raw CSV" is the telemetry log of one run (legacy format in the two oldest
folders). Rows exclude headers. "Protocols" counts `_log.json`/`_log.txt` pairs.
Blueprints live in [`../blueprints/`](../blueprints/).

| Campaign | Raw CSV (rows) | `_QA.csv` (rows) | Protocols | Logging prefixes and blueprint family | Notes |
|---|---:|---:|---:|---|---|
| `2025-12-pilot` | 5 legacy (30,827) | – | – | `qa_log`, `manual_*`: command-line logger, no blueprints | Recorded 2025-12-04. Legacy format: raw motor steps, epoch time, ≈20 Hz. Rotation commanded with 16.515 steps/°. Three files renamed from German free text. |
| `2026-01-pilot` | 7 legacy (35,811) | – | – | `qa_log`: command-line logger | Recorded 2026-01-26. Legacy format; `Status_Bits` = 1 marks homing. |
| `2026-02-pilot` | 15 (9,167) | – | – | `ETD_QA_BasicPoP` (10), `pop/`; `messung` (5, manual start) | Recorded 2026-02-10 to 02-19. Logged at ≈2 Hz. The 2026-02-10 temperatures are uncalibrated. Axes constant in 7 files. |
| `2026-02-24` | 11 (12,528) | – | – | `ETD_QA_PoP_SingleCouchOrientation` (10); `messung` (1) | First campaign at ≈9.3 Hz. Pad setpoint 32 °C throughout. No run index. |
| **`2026-03-10`** | **40 (50,424)** | – | – | `ETD_QA_PoP_SingleCouchOrientation` (39), `heating-off/`, `pop/`; `messung` (1) | **Paper campaign**: 32 evaluated runs; see `runs.csv`. |
| `2026-03-25` | 10 (27,173) | – | – | `ETD_QA_PoP_SingleCouchOrientation` | No run index; the motion must be read from the telemetry. |
| `2026-04-08` | 22 (6,665) | – | – | `ETD_ClinTest`, `heating-off/ETD_PoP_ClinTest.json` | Short H-axis runs of 26–39 s. |
| `2026-05-12` | 0 | 1 (1) | – | `ETsurface_easyQA`, `qa/` | Orphan `_QA.csv` without a raw CSV. |
| `2026-05-13` | 4 (12,363) | 4 (12) | – | `ETsurface_easyQA`, `qa/` | Temperature sensor dropouts; placeholder-like sphere values. |
| `2026-07-15` | 8 (57,275) | 8 (35) | – | `ETsurface_easyQA`, `…_T32`, `…_wcouch`, `…_wcouch_T32` in `qa/`; `ETD_QA_BasicPoP`; `ETD_QA_PoP_SingleCouchOrientation` (2) | Linac 1 QA, config entries 1–8. Three header-only `_QA.csv`. One 60-min run (33,688 rows). |
| `2026-07-29` | 2 (8,549) | 2 (10) | – | `ETsurface_easyQA`, `…_T32` in `qa/` | Linac 0 QA, config entries 9–12. |
| `2026-08-06` | 5 (17,260) | 5 (25) | 7 | `ETsurface_easyQA`, blueprint `qa/ETsurface_easyQA_new.json` | Linac 3 and 4 QA, config entries 13–20. One test run with the no-controller signature and `999999` placeholders. Two aborted protocols without a CSV. |
| `2026-08-21` | 1 (508) | 1 (0) | 1 | `ETD_QA_PoP_SingleCouchOrientation`, blueprint `ETD_QA_PoP_SingleCouchRotation.json` | Test run (linac `X`) with the no-controller signature; header-only `_QA.csv`. |
| **Total** | **118 (201,912)** + **12 legacy (66,638)** | **21 (83)** | **8** | | |

A logging prefix does **not** identify a motion profile: 16 different blueprint
files write `ETD_QA_PoP_SingleCouchOrientation` (data dictionary §9.1).

## The paper campaign: 2026-03-10

`raw/2026-03-10/` is the campaign evaluated in the paper. Its 40 raw CSVs cover
32 evaluated runs plus eight files that are not part of the evaluation:

- 20 runs with pads off, in six groups: all axes, horizontal, vertical,
  rotation, variable speed, vertical slide;
- 12 runs with pads at 32 °C, in the same groups except all axes.

[`raw/2026-03-10/runs.csv`](raw/2026-03-10/runs.csv) makes the campaign
self-describing. For every file it lists the run number, group, ROI, pad state,
the ETD export it pairs with, whether it was used, and, where one is recorded,
why it was not. Before this file existed, the mapping lived only in a hard-coded
dict in the analysis code. Its columns are documented in data dictionary §7.2.

Before reusing the campaign:

- **`used_in_analysis` is not "reported in the paper".** It marks runs the
  analysis pipeline evaluates. Two evaluated groups, variable speed and vertical
  slide, are kept in the dataset for completeness but are not part of the
  publication.
- **The variable-speed runs with pads off are not six repeats.** They span four
  ROI configurations, recorded as `PhantomWithBuffer`, `Fitting`, `Fiting` and
  `OnlyFrontSurface` (labels reproduced as recorded). Treat each ROI setting as
  its own condition; the spread across these runs mixes the ROI effect with
  run-to-run reproducibility.
- **Lost tracking frames occur only outside the reported groups.** Four
  vertical-slide scans contain 3–10 lost frames each, and the unassigned ETD
  acquisition at 18:43 (the cold/warm experiment) lost 2379 of 4077 frames. No
  scan in the all-axes, horizontal, vertical, rotation or variable-speed groups
  has a lost frame.

## Where the tracker output is

The `TrackingResult_*.json` exports of the ExacTrac Dynamic are not in this
repository.

- **2026-03-10 (paper campaign):** the 38 exports are in the analysis pipeline,
  [github.com/AG-Kollotzek/surf-etds-analysis](https://github.com/AG-Kollotzek/surf-etds-analysis),
  under `paper_data/full_raw/01_json/`. `runs.csv` names the file for each run.
- **2026-07-15, 2026-07-29, 2026-08-06:** the 20 exports referenced by
  `etds_qa_2026_config.json` are held in the separate clinical-QA repository
  `lki_etds_qa2026`, not in surf-etds-analysis.
- **All other campaigns:** whether tracker exports exist is not determinable
  from the archive.

## Operator pseudonymisation

The protocols recorded the first names of the staff present: field `personal`
in `_log.json`, line `Messteam` in `_log.txt`. Before release, these were
replaced with the role codes `QMP1` and `Student1` to `Student3`. The mapping is
intentionally not published and is not held in this repository. `QMP` stands
for Qualified Medical Physicist; the number tells people with the same role
apart.

## New data from the terminal

The measurement terminal (`software/surf_terminal/`) writes new data to
`data/<YYYY-MM-DD>/` **relative to its working directory**. That path was
deliberately left unchanged. The campaigns archived here were moved to
`data/raw/` during release preparation, from the terminal's former working
directory `firmware/measurement_pc/`. The terminal's `plot_*.png` screenshots
are derived output and are not archived.

## Licence and citation

The contents of `data/` are licensed under
[CC BY 4.0](LICENSE). Other parts of the repository carry their own licences.
To cite the data, use [`../CITATION.cff`](../CITATION.cff).
