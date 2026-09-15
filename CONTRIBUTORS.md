# Contributors

## Open item — must be resolved before this repository is made public

The git history of this repository contains commits from **three people**. A
public release under the licences named in the [README](README.md#licensing)
requires each of them to agree to that release.

| Contributor | Contribution | Release consent |
|---|---|---|
| Tim Buck | Firmware, measurement terminal, blueprints, hardware, most measurement campaigns | — (author) |
| S. Kollotzek | Measurement data, including the **2026-03-10 campaign used in the paper**; one change to the measurement terminal | ☐ **not yet obtained** |
| A. M. Schneider | Early control scripts (`hellyeah.py`, `fuckyeah2.py`, `Linac_beam_sync_check.py` — all removed from the current tree, retained in history) | ☐ **not yet obtained** |

Record the answers here, with date, before flipping repository visibility.

This is not only a licensing question. The 2026-03-10 campaign is the dataset
the paper reports, so its contributor is also an authorship question for the
paper itself.

## Operator pseudonymisation

Measurement protocols (`data/raw/**/*_log.json`, `*_log.txt`) originally recorded
the first names of the staff present. These were replaced with role codes
`QMP1` and `Student1` to `Student3` before release. The mapping is intentionally not
published and is not held in this repository.
