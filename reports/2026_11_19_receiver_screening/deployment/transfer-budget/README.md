# Compact transfer with a staged recovery budget

The support rule preserved the full compact position and RF endpoints on all three containing synthetic comparisons. It stopped two archived omitted-region deadline cases before recovery and stopped a far omitted offer at a new simulated site that otherwise published a position 75 km from truth. The near omission at that same site still published in both arms. A separately sealed terminal guard withheld the equivalent false fix on a second new site and preserved both legitimate offers, including one 1.63 km inside the edge. The measured roof query with its tile shifted 7 km east also completed through the bounded route, publishing 1.261/1.197 km error at zero/fitted calibration. [Protocol](PROTOCOL.md) · [Paired predictions](prediction-lock.json) · [Position-level scores](scores.json) · [Independent terminal interior guard](interior-guard/README.md)

## Conservative recovery entry

The five exact earlier requests used the previously sealed detector factors, clocks, causal TLE histories and offers. Their original secant initial fits retained 84.6% and 74.4% of nominated points on the two containing simulated offers and 95.6% on the authentic shifted offer. The two distant omitted offers retained 48.7% and 34.2%. Only one omitted fit reached a compact tile face. The other was about 0.78 km inside its fitted square, so a face-only early stop would have missed it. [Sealed diagnostic requests and outputs](development-initial-diagnostics.json) · [Diagnostic source receipt](development-initial-source-lock.json)

The staged receiver passes the unchanged initial `c = 0` nomination to conservative recovery when a strict majority of its nominated observations satisfy the original compatibility tests. The guard therefore executes before either later calibration-arm fit. Accepted requests use the original recovery, family, signed and cavity policy, with a 55 s wall timer on conservative recovery. Neither a failed compatibility check nor a recovery timer exit publishes a partial fit.

## Prospective site and matched runtime

The first new holdout draws one receiver and uses the same 300 s simulated GLRT factor, archive history and blind input envelopes for both method executions. The two errors in a cell follow zero/fitted calibration. Each row is a separate offer to the same simulated site. The combined processing uses authentic preceding TLE history and empirical residual and visit-gap windows. [Fresh sources and history](policy-lock.json) · [Fresh input seal](fresh-input-lock.json) · [Released draw](fresh-draw.json)

| Offer | Initial compatible points | Recovery-budget receiver | Original compact secant | Worker wall, bounded / original |
|---|---:|---|---|---:|
| Containing | 100% | 1.651 / 1.251 km | 1.651 / 1.251 km | 34.90 / 35.28 s |
| Near omission, 1.61 km outside | 100% | False fix, 2.227 / 1.990 km | False fix, 2.227 / 1.990 km | 36.86 / 37.65 s |
| Far omission, 49.13 km outside | 41.9% | Withheld before recovery | False fix, 75.093 / 75.147 km | 27.52 / 52.77 s |

Containing conditional RF was 81.391/81.513 Hz in both methods. The false near-edge fit had 81.336/81.433 Hz, and the stock far omission measured 98.879/98.928 Hz. Both near-omission estimates lie at the compact search's actual constrained box boundary. RF residuals alone would not distinguish the near omission from the containing case. No request in this batch exercised the internal time-limit exit. The separate study below checks a terminal requirement for geometric interiority.

## Earlier cases and authentic shifted tile

On the two earlier synthetic locations, the new route published both original containing fits with identical coordinates and RF in both arms. It withheld the two archived far-omission timeouts before entry at 26.22 and 32.72 s. The 7 km shifted authentic DS26-0036 request completed in 67.66 s and had RF RMS of 74.760/74.682 Hz. Its original matched run stopped at the 225 s external deadline on a different shared-host session. The archived timings establish earlier dispositions. They do not measure a same-host speed ratio for the admitted containing or authentic cases. [Earlier matched study](../../redesign/compact-transfer/README.md) · [Archived authentic replay](../../redesign/compact-transfer/measured-retry/prediction.json)

[Zero-calibration figures](figures/c0/transfer.pdf) · [Fitted-calibration figures](figures/fitted_c/transfer.pdf) · [Independent terminal interior guard](interior-guard/README.md)
