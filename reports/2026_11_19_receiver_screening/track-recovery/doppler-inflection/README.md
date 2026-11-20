# Timing the steepest descent of measured Doppler

All four real archive requests supplied enough bracketed inflections to test a regional position. The time-only receiver **withheld all four** in both calibration arms. On the two containing requests, forced errors were **17.14 and 16.47 km**, versus **8.19 km** for both tile centres. Each forced winner lost to a separated alternative on held timing. The two new simulated captures supplied only two and one distinct measured landmarks, below the four-event gate for a position attempt. [Timing and geometry figure](inflection-support.png) · [Real position charts](charts/manifest.json) · [Full scores](scores.csv)

## Measured and injected timing

Each event is a negative-to-positive curvature crossing, where an otherwise descending CFO trace steepens and then flattens. The receiver fits a local cubic on alternating measured GLRT points and checks the root on the disjoint interleaved measurements. Each fit requires observed points near the root and on both shoulders, first-to-last span of at least 16 s, third derivative at least 1.5 Hz/s³, timing uncertainty at most 1.25 s and fit RMS at most 350 Hz. The two roots must agree within 1.25 s. Repeated times within 3 s across lanes merge into one candidate event. An affine CFO term, including the constant RF calibration term on each fixed carrier, leaves the curvature and both calibration outcomes unchanged. [Prospective rule](PROTOCOL.md) · [Source closure](source-lock.json)

The 432 retained anonymous arcs across six unique captures included 388 spanning at least 20 s. Eighty arcs supplied at least one replicated root, giving 40 distinct candidate events after duplicate suppression. The four real records accounted for 37 of these, with median per-recording root precision estimates of 0.72–0.92 s. These estimates measure internal precision across disjoint native samples and a residual-noise floor. They carry no independent orbit identification guarantee. In positive controls on the same captured timestamps, the detector recovered **58/72** planted roots within 1.25 s at 2 Hz/s³ curvature slope and **70/72** at 12 Hz/s³. Both injections use 75 Hz sample noise and a free affine term. [Arc, event and injection traces](positions.jsonl.gz)

## Causal geometry and position

| Real query | Distinct observed events | Held identities meeting model threshold | Held likelihood lead | Tile centre error (km) | Forced error (km) |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0122 | 8 | 4 | −0.404 | 8.19 | 17.14 |
| DS29-0247 | 12 | 4 | −0.277 | 8.19 | 16.47 |
| DS26-0070, omitted | 8 | 4 | −0.443 | 51.23 | 42.86 |
| DS29-0316, omitted | 9 | 1 | −1.016 | 55.19 | 64.17 |

The receiver ranked nine generic in-tile sites on alternate event times, using a soft distribution over causal visible orbit timings, a 35% no-match mixture and a 2 s orbital timing uncertainty. The remaining events compared the selected site with separated inside and exterior hypotheses. An “identity meeting model threshold” is a held posterior association above 30% under that mixture. None of the four real site choices beat its held alternative, let alone the required 0.35 lead. All forced coordinates are retained. The four original v5 roles are shown on the authenticated containing requests only. No-repair v5 published those two at 0.75/1.32 km with c0 and 0.75/1.46 km with fitted c. [Both-arm geographic panels](charts/manifest.json) · [Decision and likelihood detail](scores.json)

The causal TLE calculation found 24–58 stable modeled events per offer whose named trajectories could be re-evaluated at the generic centre and the four 10 km offsets. The median linearized strongest-direction timing shift over 25 km was **3.64–3.70 s**. The maximum was 3.73 s. With perfectly known identities, exact orbital phases and independent equal timing errors on **all** modeled events, the most weakly determined horizontal direction has these local one-sigma bounds:

| Assumed single-event RMS (s) | Optimistic worst-axis standard deviation across offers (km) |
| ---: | ---: |
| 0.3 | 0.42–0.70 |
| 1 | 1.41–2.32 |
| 3 | 4.23–6.97 |
| 8 | 11.29–18.60 |
| 18 | 25.40–41.84 |

These bounds use the local Jacobian of the named satellite times, an optimistic reference for the tested geometry. Real capture candidates supplied fewer events, and their site decisions also had to resolve orbit identities and phase uncertainty. The measured roots establish a receiver-affine-invariant timing observable. The held position results show that timing alone, with this soft association and grid, failed to distinguish the offered site from nearby alternatives. Independently constrained orbit ownership remains the specific open variable. [Timing derivatives and exact geometry traces](positions.jsonl.gz) · [Stage plot](inflection-support.pdf)

All eight bound jobs completed with 1.64 s median CPU, 2.75 s median elapsed and 190 MiB maximum RSS. The simulated offers replay the same two independent captures under two geometries; their empirical events and injections reproduce exactly across offers. The stage and position receipts were sealed before scoring truth. [Prediction seal](prediction-lock.json) · [Stage artifact seal](stage-lock.json) · [Simulated source and acquisition labels](synthetic-truth.json)
