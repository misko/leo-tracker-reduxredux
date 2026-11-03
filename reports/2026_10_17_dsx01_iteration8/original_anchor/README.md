# Original cold prediction versus the iteration8 outcomes

The new independent-point fit assigns 806/1,909 held observations and 73/80 requested held observations, compared with the original training-only cold endpoint's 795 and 66. The coherent fit assigns 803 and 70. Both comparisons use the **same original shared-q classifier** on frozen complete predictions, without replacing it with the new model's native posterior definition.

| Outcome | Held /1,909 | New/lost vs original | Retained-pair RMS original→new Hz | Requested /80 | Requested new/lost |
|---|---:|---:|---:|---:|---:|
| Original fitted-c cold endpoint | 795 | — | — | 66 | — |
| Independent, fitted c | 806 | 46/35 | 175.19→161.17 | 73 | 8/1 |
| Coherent, fitted c | 803 | 59/51 | 175.27→157.45 | 70 | 5/1 |
| Independent, conditional c=0 | 670 | 146/271 | 180.95→195.19 | 53 | 6/19 |
| Coherent, conditional c=0 | 812 | 231/214 | 177.92→194.83 | 47 | 5/24 |

The original fitted-c baseline is used for every row; it is not an independently optimized cold c=0 pipeline. Native posterior classifications and the matched independent-versus-coherent comparison are in the adjacent pilot report. Associated frequency RMS is evaluated on the same retained observations in each pair, and model-identity changes are retained in `summary.json`. These are model assignments, not verified emitter labels.

| Held window | Original | Independent fitted c | Coherent fitted c |
|---|---:|---:|---:|
| DSX01-007 /26 | 20 | 23 | 20 |
| DSX01-008 /28 | 20 | 25 | 24 |
| DSX01-009 /26 | 26 | 25 | 26 |

This original-versus-new table is descriptive. The new fits change the density, free the receiver-band constants, receive additional optimization, and use the broad regional domain without the original production endpoint's extra local disk. It cannot attribute gains to the density or coherence alone. The independent/coherent pilot's own matched comparison rejects broadening: fitted-c coherence worsens excluded prediction and loses requested support, and its strict stationarity check fails. No original-versus-new advantage overrides that result. The other four sources and 555 requested observations remain untested here.

No orbit queries, new fits or station-reference reads occur. The original saved prediction is rescored once through the public original shared density; every association, identity and residual reproduces the original saved evaluation, as does its full 47,542.258819 NLL. Old NPZ files omit observation IDs: source ordering, exact timestamps and role masks, plus the exact classification/identity/residual replay, bind them to the current frozen observation IDs. Both new outcome and metadata-prediction seals are verified before measurement access. Original prediction/evaluation/input authorities are checked against the older 164-file manifest.

Two component tests cover loss debit, identity switches, retained-intersection RMS and alignment rejection. `summary.json` records every source digest, role/window denominator and complete comparison; `audit.py` contains the read-only reconstruction. The sole additional normalized-density call is disclosed. No prior report or persisted contract is changed.
