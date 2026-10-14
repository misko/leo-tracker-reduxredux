# Model C phase control: diagnose the failed all-band fits before more fitting

The root coordinator reports the completed twelve-call DS21-039 experiment:
10 stationary calls, with both CH1–8 relative-phase calls nonstationary after
their 20-second limits. There is no accepted all-band phase estimate and no
combined-position improvement to promote. The initial all-band phase start
used 164 evaluations in 20.168 seconds with KKT approximately 2,092; the refined
start used 167 in 20.114 seconds with KKT approximately 6,673. This supplement
records the coordinator's receipt summary; it is not an independent replay of
those real-data fits.

| View | Receive-epoch control | Relative-phase control |
|---|---:|---:|
| CH1–8 | 4.072515 km | Unavailable: both starts nonstationary |
| CH1–4 | 3.758515 km | 2.894677 km |
| CH5–8 | 4.163056 km | 2.919883 km |

The high-band control is the current two-start training-selected result. The
earlier 2.556792 km high-band result belongs to the historical selection and
must not be silently substituted into this table. The phase halves improve
against this matched control, but remain above the requested accuracy targets.
All half results still use shared initialization.

The failure does not identify the timing mechanism as physically wrong. The
Python phase predictor may have exhausted the fixed wall-clock budget before
convergence; an actual-state gradient or scaling problem also remains possible.
The 45 passing synthetic tests establish useful mechanics checks, not proof of
all real-data derivative regimes. Existing failed attempts must remain intact;
do not retry them with larger budgets or modify their frozen sources.

The coordinator has now completed the required evaluation-only
[cost and derivative audit](PHASE_COST_AUDIT.md), in 40.322 seconds with no
optimizer, held projection or reference lookup. The frozen source and parent
authority were checked before and after evaluation.

At the identical original all-band winner, alternating six evaluations of each
scorer gave median times of 31.555 ms for receive-epoch and 113.199 ms for
relative-phase: the phase path was **3.587 times slower** on that loaded host.
Two-step central differences checked east, north, fitted c, common timing, one
relative timing coordinate and one group offset at the original winner and
both failed endpoints. Maximum scaled discrepancy was 8.608e-6; no gross
disagreement appeared in those sampled coordinates. This is not an exhaustive
gradient or visibility-boundary proof.

There is now concrete evidence that implementation cost can contribute to the
164/167-evaluation nonconvergence. Do not duplicate this audit merely to obtain
another timing number. The next useful implementation is an isolated faster
phase predictor, with exact value/gradient/posterior checks against the frozen
Python oracle on synthetic and actual saved states. Preserve every candidate,
timestamp, state, prior, frame and fitted-c term. It must use new component
files and a new source closure; no live frozen numerical module may be edited.

Only after equivalent predictions and measured speed improvement should a
separately frozen matched-budget fit control run. Faster computation does not
prove correct geography or a physically true timing mechanism. Retain both
original nonstationary all-band attempts; do not publish their rejected
endpoints as accepted positions.
