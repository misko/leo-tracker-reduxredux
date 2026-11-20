# Position error across the seven DS26 recording dates

On the full DS26 roster, compact v5 with a retry for diagnosed failures returned 154/159 fixes and original v5 returned 143/159. Both returned positions on 142 of the same recordings. The same roof and receiving installation supplied every dated input. Each recording's UTC date comes from its sealed orbit-catalogue cutoff. DS26-0172 has no timestamp or native input and stays in every leave-one-date-out denominator. [Per-date, full-roster and leave-one-date-out scores](by-date.csv) · [Scoring and input hashes](receipt.json)

| UTC date in October 2026 | Offered | Original fixes | Compact with retry fixes | Original P95 (km) | Compact with retry P95 (km) |
| --- | ---: | ---: | ---: | ---: | ---: |
| 24 | 10 | 10 | 10 | 2.665 | 2.669 |
| 25 | 28 | 27 | 28 | 4.167 | 4.488 |
| 26 | 27 | 26 | 27 | 2.354 | 1.890 |
| 27 | 24 | 20 | 24 | 1.970 | 2.053 |
| 28 | 26 | 22 | 22 | 3.317 | 4.072 |
| 29 | 27 | 24 | 27 | 1.920 | 2.552 |
| 30 | 16 | 14 | 16 | 2.323 | 2.162 |
| Unknown | 1 | 0 | 0 | — | — |

The table uses fitted calibration and each method's returned positions. Dropping one date at a time gave a compact/original P95 ratio of 1.060–1.344 with fitted calibration and 1.054–1.217 with zero calibration. The median ratios were 1.015–1.049 and 1.009–1.033. The larger tails accompany a change in which recordings receive positions.

Restricting each calculation to recordings where both methods returned a position gave P95 ratios of 0.993–0.999 with fitted calibration and 0.894–0.998 with zero calibration. This check describes dependence on the sampled days at one roof. The separate holdout changed the site geometry. [Three-site edge results](../edge-holdouts/README.md) · [Original four options and both compact methods](../failed-only/README.md)

Rebuild the table from the checked-in evidence with `python -m tools.pipeline_eval.qualification.roof_day_sensitivity --out /tmp/roof-day-sensitivity`.
