# DSX01 S01: tracks, associated GLRT and unassociated GLRT

These views use the latest curved-only phase-repair **fitted-c** association
at the supplied GPS. They do not refit curves or change satellite assignments.

| Subset | GLRT points | Polynomial fragments | Merged associated tracks |
|---|---:|---:|---:|
| All | 4,797 | 170 | — |
| Satellite-associated | 2,291 (47.76%) | 102 | 73 |
| Unassociated | 2,506 (52.24%) | 68 | — |

The unassociated points comprise 2,195 points on retained polynomial fragments
and 311 without a retained polynomial. Those 311 include the isolated T009
endpoint. Every raw GLRT point is present in the all view and exactly one subset.

![All, associated and unassociated tracks](overview.png)

Dots are original GLRT CFO measurements. Coloured lines are the empirical
polynomial fits, not predicted satellite Doppler. Colours are consistent across
views; associated fragments sharing a merged track share a colour. Grey crosses
have no retained polynomial. Each receiver keeps its original CFO branches and
vertical scale; no receiver-offset alignment is applied. Lines break at native
alias changes and gaps greater than five seconds.

Each detailed view has CH1–CH8 down the rows and RX1/RX2 in the columns, with
fragment IDs labelled. Associated means compatibility with the frozen model at
the supplied position; it does not authenticate the satellite identity.

- [All GLRT and polynomial tracks](all_by_channel.png)
- [Associated GLRT and polynomial tracks](associated_by_channel.png)
- [Unassociated GLRT and polynomial tracks](unassociated_by_channel.png)

`panel_counts.json` records per-receiver/channel counts. `protocol.json` binds
the exact scientific inputs, source and point-accounting checks. The initial
unlabelled rendering is preserved in the sibling `_initial_render` directory.
