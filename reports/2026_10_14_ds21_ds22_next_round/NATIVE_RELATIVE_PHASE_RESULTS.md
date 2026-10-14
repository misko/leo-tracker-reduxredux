# Isolated native relative-phase qualification

The native implementation passed all **nine actual saved-state** comparisons in
41.553 seconds, including 32.596 seconds of training preparation. It used zero
optimizers and introduced no new position estimate. At the original CH1–8
training winner, its full objective evaluates **3.388× faster** than the frozen
Python phase oracle, with unchanged numerical results.

The same nine states are retained: original all/low/high training winners and
both original relative-phase endpoints per view, including failed fits. Six
timed evaluations per path/state alternated order after one untimed equivalence
check. The host also ran six discovery jobs and a DS22 slice; these timings are
descriptive under that concurrent load, not a universal speed guarantee.

| View / saved state | Python median ms | Native median ms | Speedup |
| --- | ---: | ---: | ---: |
| All / original training winner | 124.003 | 36.604 | 3.388× |
| All / original-view phase endpoint | 119.412 | 36.911 | 3.235× |
| All / refined-all phase endpoint | 148.213 | 40.051 | 3.701× |
| Low / original training winner | 86.160 | 33.538 | 2.569× |
| Low / original-view phase endpoint | 87.962 | 33.315 | 2.640× |
| Low / refined-all phase endpoint | 89.067 | 28.945 | 3.077× |
| High / original training winner | 52.387 | 19.322 | 2.711× |
| High / original-view phase endpoint | 47.738 | 18.925 | 2.522× |
| High / refined-all phase endpoint | 46.286 | 19.775 | 2.341× |

Across every state and every timed repeat, maximum differences are:

| Quantity | Maximum absolute difference |
| --- | ---: |
| Objective / NLL | 0 / 0 |
| All physical vector gradients | 4.547e-13 |
| Group nuisance gradients | 0 |
| Satellite / clutter posteriors | 0 / 0 |
| Prediction gradients / residuals | 0 / 0 |
| Frequency prediction | 0 Hz |
| Spatial derivative | 1.137e-13 Hz/km |
| Common / relative time derivative | 0 / 0 Hz/s |
| Visibility masks | 0 mismatches |

All six stored phase endpoint objectives and NLLs replay exactly; all three
original receive-epoch objective/NLL oracles also replay exactly. Original
likelihoods, native times, candidate inventories, receiver correction frames,
timing bases and priors are retained. Neither numerical equivalence nor faster
evaluation establishes the physical phase mechanism or improved localization.

The pre-preparation freeze pins the original scientific closure, added native
sources/binary and ancestry inputs. The historical exact module-closure guard
passed before training preparation; after the explicitly declared new import,
original live/archive byte guards and added/input bindings passed again. The
new exclusive build namespace preserves the earlier exploratory build and does
not invoke or modify published `setup.py`. All four frozen scientific source
files remain unchanged. Thirty-seven owned tests and Ruff pass.

The run retained the 180-second internal whole-slice limit and external
195-second TERM / 200-second KILL bounds. Counts are 3 receive-epoch, 69
Python-phase and 63 native-phase objective calls, plus 9 explicit orbit-port
comparisons per implementation. No held observations, reference lookup, new RF,
fit, or calibration model extension entered this qualification.

The next authorized experiment is a new, separately frozen DS21-039 matched
implementation control: the same twelve receive-epoch versus native-phase
calls, two original physical seeds per view, original 20-second / 600-iteration
limits and original priors. Increased evaluations may result from faster
implementation; wall budgets do not increase. Both conditions must be sealed
before held/reference evaluation, and earlier rejected Python-phase outcomes
remain unchanged.

DS21-023 remains the other worst case in the consistent original C version
(4.899 km versus 4.291 km for 039). Its genuine shared-six parent has 33
satellites and an all-view training winner at cold-1/start 1; the 039 seed-5
authority cannot be copied onto it. A corresponding warm-refinement donor has
not been established for 023. Its next protocol must bind actual original
seeds and select an explicitly supported donor policy, retaining that gap and
both half-band comparisons. No reference-derived initialization or forged
refinement compatibility is permitted.

The [hash/scalar audit](NATIVE_RELATIVE_PHASE_AUDIT.json) binds every result and
timing row without new scientific evaluations. The [protocol](NATIVE_RELATIVE_PHASE_PROTOCOL.md)
and [qualification recipe](relative-phase-native-audit.py) describe the source
and execution gates. Full evidence is in `local/relative-phase-native-audit-v1`
and the exclusive binary build in `local/relative-phase-native-build-v2`.
Result SHA-256 is
`e51636996cd417f08d87417aa7db035243ea56db83b6e4a7c5ed3e605a4d992b`.
