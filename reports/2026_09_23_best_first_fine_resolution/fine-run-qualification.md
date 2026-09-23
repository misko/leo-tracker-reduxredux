# 6.25 km bounded-search qualification

`fine-run-qualification.json` compares exact-centre `100 → 50 → 25 → 12.5 →
6.25 km` runs under 400- and 800-point budgets. Both use the identical frozen
34-track evidence receipt, fixed position-independent masks, source snapshot,
and capped all-track objective. The objective recomputes exactly at every
reported finalist.

For each city, the first 400 evaluated coordinates and objectives of the
800-point run exactly match the 400-point run. Sacramento shares 1,079 initial
trace events; its final terminal scheduling event differs only because the
800-point run continues. Reno shares all 1,044 400-point trace events. The
same final-level points are therefore reached in the common 400-evaluation
prefix.

| City | 400-point 6.25 km final RMS | 800-point 6.25 km final RMS | 12.5 km 400-point global RMS |
| --- | ---: | ---: | ---: |
| Sacramento | 205.52 Hz at `(-340.625, 365.625)` | 183.09 Hz at `(-78.125, -71.875)` | 184.78 Hz at `(-75, -75)` |
| Reno | 182.40 Hz at `(-240.625, -190.625)` | 182.40 Hz at the same point | 184.51 Hz at `(-243.75, -181.25)` |

Each local exact reference has winner match, top-15 coordinate recall 1.0,
and zero objective gap. Sacramento's reference remains the 141-point northwest
100 km parent selected at the 400-point boundary, while the 800-point global
winner lies elsewhere. This validates that local reference calculation; it does
not certify the global basin.

All four searches are budget-bounded and incomplete. A larger budget improves
the global incumbent monotonically within a fixed run sequence, but a 6.25 km
schedule at a fixed budget need not dominate a 12.5 km schedule because it
allocates the frontier differently. A lower selected residual objective is not
evidence by itself of a better location; no truth data is used in this
qualification.
