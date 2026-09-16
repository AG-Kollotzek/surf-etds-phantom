# Contributors

| Contributor | Contribution |
|---|---|
| Tim Buck | Firmware, measurement terminal, blueprints, hardware, most measurement campaigns |
| S. Kollotzek | Measurement data, including the 2026-03-10 campaign used in the paper; one change to the measurement terminal |
| A. M. Schneider | Early control scripts (removed from the current tree, retained in history) |

All contributors agreed to the release of their contributions under the licences
named in the [README](README.md#licensing).

## Operator pseudonymisation

Measurement protocols (`data/raw/**/*_log.json`, `*_log.txt`) originally recorded
the first names of the staff present. These were replaced with role codes
`QMP1` and `Student1` to `Student3` before release. `QMP` stands for Qualified
Medical Physicist; the number tells people with the same role apart. The mapping
is not published.
