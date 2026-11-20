# Causal track-time null

The frozen permutation rule detected genuine time alignment at two simulated sites but did not reliably distinguish an offered 25 km square from its surroundings. On two archived recordings from one measured roof, it suppressed all three previously published false fixes and both legitimate publications. There was no exterior winner on the roof data. Results were identical for zero and fitted RF calibration because the new score removes a constant offset separately from every arc.

| Cohort | Scheduled | Native smooth published | With regional gate | Independent gate outcomes |
|---|---:|---:|---:|---|
| New synthetic, containing | 4 | 0 | 0 | 1 inside, 3 ambiguous |
| New synthetic, omitted | 4 | 0 | 0 | 1 outside, 3 ambiguous |
| Measured roof, containing | 4 | 2 | 0 | 2 ambiguous, 2 overlap with null |
| Measured roof, omitted | 4 | 3 false | 0 false | 2 ambiguous, 2 overlap with null |
| Synthetic peak lists shifted within RF lanes | 2 | 0 | 0 | 2 insufficient for permutations |

Each site or capture contributes four related offers. The shuffled controls reuse the two new synthetic peak-list populations. These denominators describe the specific experiment and cannot estimate a population false-fix rate.

All eight synthetic offers exceeded all 19 shuffled maxima. The interior-minus-exterior score had the correct sign on eight offers, with enough separation to decide only one center and one 15 km omission. Both 1.5 km omissions remained ambiguous. The original smooth fit withheld seven synthetic queries on position geometry and one on weak held support. Even the centered synthetic offer that cleared the new gate had no publishable position from the base receiver.

For DS26-0102, all four geographically distinct offers beat their shuffled maxima and none reached the one-orbit score separation. The smooth receiver published on the original containing offer, the near-inside offer and the near omission. For DS26-0070, none of the four offers exceeded its strongest shuffled maximum, including its two false publications. The initial roof errors among published containing offers ranged from 2.82 to 4.55 km at `c=0` and 2.54 to 4.63 km with fitted `c`. The three false publications ranged from 4.55 to 14.55 km and 4.68 to 14.96 km, respectively. No gated position errors are defined because it published no estimates.

The ordinary in-sample RF RMS fell from 208 to 200 Hz median for the synthetic offers and from 225 to 199 Hz for the roof offers when fitting RF calibration. Ordinary held RMS was 2244 versus 3063 Hz for synthetic offers and 1663 versus 1645 Hz for roof offers. Those diagnostics use the frozen smooth receiver's held evaluation. The new permutation score reuses the same arc curves under randomized times. The two shuffled peak-list controls each left four eligible arcs and too few distinct within-lane schedules. They exercise no-support abstention and do not calibrate the null when coherent but geographically ambiguous curves survive.

| Complete queries | Whole wall P50 / P95 (s) | Gate CPU P50 / P95 (s) | Peak RSS (MiB) | Peak address space (MiB) |
|---|---:|---:|---:|---:|
| 8 new synthetic offers | 14.63 / 19.86 | 2.48 / 2.99 | 197.0 | 431.5 |
| 8 exact archived roof offers | 12.26 / 17.69 | 3.99 / 4.81 | 190.3 | 425.6 |
| 2 shuffled peak-list controls | 12.12 / 12.37 | 0.002 / 0.002 | 137.3 | 374.3 |

Wall time includes streaming GLRT, anonymous Graph, the full smooth fit and the new gate in a single worker. The scientific gate evaluates an equal number of inside and outside nodes, using the same arc nuisance and orbit nomination rule on both and in every permutation. Distinct satellite nominations cap repeated evidence from one orbit. They do not guarantee independent errors when orbital predictions are correlated. The coarse grid and free arc offsets leave similar candidate curves within and just beyond an edge, while within-band timing exchangeability can fail under changing visibility and track selection. The matched roof audit therefore weighs against using this rule for publication.

## Evidence and reproduction

- [Predeclared study](PROTOCOL.md) · [Source lock](source-lock.json) · [Prediction lock](prediction-lock.json) · [Native roster](roster.json) · [Result lock](result-lock.json)
- [Independent-null scatter](null-evidence.png) · [PDF](null-evidence.pdf) · [Both calibration arms and matched position charts](charts/README.md)
- [Per-offer scores](scores.csv) · [Distributions including withheld rows](summary.json) · [Evaluator labels revealed after sealing](evaluator.json)
- [Negative control repair](shuffled-control-lock.json) · [Serialization-only requests](shuffled-control-requests.json)

Both shuffled controls initially hit the native archive reader's compact-JSON format check. The original failed attempts remain in the primary prediction lock. A separate hashed repair re-encoded the same decoded objects in the accepted compact form and reran those two controls with the original solver, catalogue, tiles and schedule. The 16 geographic predictions were untouched.

Regenerate the results and charts from the sealed study and roof archive without rerunning inference.

```sh
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.region_null_results
.venv/bin/pytest -q tests/pipeline_eval/test_region_null.py
```
