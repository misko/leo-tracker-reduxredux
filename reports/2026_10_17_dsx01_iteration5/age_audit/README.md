# Object element age and fitted orbital timing

Read-only audit of the same 215 original selected recording–satellite pairs
across DSX01's five recordings. No fits, RF acquisition, production changes,
station coordinates or candidate selection occur in this script. Exact source
and timing input hashes are recorded in `summary.json`.

Element age uses each object's element epoch at the recording midpoint, rather
than the snapshot collection time. Both signed and absolute ages are retained.
The original, matched b0, b300 and b1000 fitted-c endpoints use identical IDs.
Fewer than five original assignments are marked × in the plot.

| Original fitted-c audit | Result |
|---|---:|
| Recording–satellite pairs | 215 |
| Element age range | 5.07–44.25 hours |
| Median element age | 17.70 hours |
| Absolute relative timing >10 seconds | 71/215 |
| Same, original assignment support ≥5 | 56/182 |
| Pearson age vs absolute relative timing | −0.0068 |
| Same, support ≥5 | −0.0371 |
| Valid native 10-second state propagations | 215/215 |
| ECEF displacement over 10 seconds, min/median/max | 72.60 / 73.39 / 77.64 km |

These fitted shifts show no linear age trend in this selected sample. They are
not measured physical orbital errors: geography, calibration and identity errors
can all influence them. Repeated satellites, provider differences, original
candidate selection and narrow age coverage also limit interpretation. This
audit neither calibrates an age prior nor establishes that age is irrelevant.

A 10-second trajectory shift corresponds to approximately 73 km of orbital
motion here. This does not mean 73 km of observer position error and does not
prove such shifts impossible; it motivates investigating their physical basis.

![Age versus fitted relative timing](age-vs-timing.png)

The b1000 comparison is descriptive only. Its separate conditional prediction
test worsened excluded-half likelihood in 39/40 fits; reduced in-sample timing
or greater assignment coverage is not evidence of physical correctness.

Historical prior calibration is owned separately by `../age_timing/`, using
archive snapshots before the earliest DSX recording. A newer TLE is a
consistency reference, not orbital truth. Recording common-clock uncertainty
must remain separate from per-satellite relative timing priors.

Validation: two component tests cover signed epoch age and integer timestamp
precision. The actual-data audit asserts four endpoints ×215 pairs and records
all per-object propagation results. Run with the pinned scientific environment
documented in the previous iteration's protocol.
