# S03 cold forecast failure: candidate inventory dominates

The faithful training-first-half pipeline assigns 1571/2006 training observations
and 165/1982 held observations. Its strict training projected stationarity is
0.000223. The largest measured confound is the changing candidate inventory:
84.4% of observations assigned on the held half by the original full-data model
have an original winner satellite absent from the training-selected bank.
These original labels are descriptive oracles conditioned on all measurements,
not satellite-identity truth. No fit or parameter selection was performed here.

## Candidate coverage versus positive visibility

The training bank has 25 satellites, the original full-data bank 40, and their
intersection has 19. Six training-selected satellites are absent from the
original bank; 21 original satellites are absent from the training bank. Positive
visibility of all 25 selected satellites throughout the capture does not imply
coverage of the emitter actually responsible for a measurement.

| Original full-model assignment accounting | Train | Held |
|---|---:|---:|
| Original full-model assignments | 1681 | 1410 |
| Original winner present in cold bank | 1585 | 220 |
| Original winner absent from cold bank | 96 | 1190 |
| Original assignments lost by cold prediction | 226 | 1267 |
| Lost; original winner present | 172 | 161 |
| Lost; original winner absent | 54 | 1106 |

Thus 87.3% of lost original held assignments have absent original winner IDs.
The original full-state classifier restricted to the 19 overlapping satellite
columns assigns 1595 training and 267 held observations, versus 1681/1410 before
restriction. This classifier-only oracle preserves original predictions,
visibility and q. The signal-versus-clutter comparison cancels the common
posterior denominator. The subset is **not** a scored model with a renormalized
full-bank q budget, and these counts are not credited as predictive recovery.
Nor is subtracting these counts a causal attribution: identities can change and
the full-data model itself can be wrong.

`candidate-support.csv` retains every satellite in the union of the two banks.
For example, original winner 66435 has eight original train assignments but 271
held assignments; original winner 68701 has 49 train and 124 held assignments.
Missing selected IDs are not exclusively satellites with zero early evidence.
Training discovery may discard weak early evidence, and original full-data
identity substitutions are another possibility. This audit cannot distinguish
those causes without independent labels.

## Same candidate, calibration and physical prediction

Among original assignments whose original winner is in the cold bank, the
median absolute residual against that **same candidate** is 138.87 Hz on 1585
training observations and 735.60 Hz on 220 held observations. Only 45/220 held
residuals are within 375 Hz, versus 1268/1585 training residuals. This comparison
does not choose a different candidate to improve proximity.

The unchanged cold correction minus the original full-data correction has these
medians across all observations in each receiver/band lane:

| Receiver (contract labels) | Band | Train Hz | Held Hz |
|---|---|---:|---:|
| 0 | low | +121.01 | −1157.17 |
| 0 | high | +126.73 | −1131.46 |
| 1 | low | +252.10 | −526.70 |
| 1 | high | +114.86 | −693.09 |

The cold learned common affine receiver slopes are −3.768 and −4.342 Hz/s;
the original full-data model's slopes are +0.675 and +0.769 Hz/s. Their centered
intercepts are not directly comparable without transporting the centering
frame. The row-by-row correction difference above performs that transport
exactly, including the residual clock, actual RF/c and frozen band corrections.
The cold residual clock is constantly extended after 150 s while its affine
slopes continue; this was the declared prediction policy, not a transport bug.
The original public evaluation proves training correction closure 3.64e−12 Hz.

For the same 220 held observations, the signed median physical orbital prediction
difference (cold minus original, including location and orbital timing) is
+323.98 Hz, while calibration difference is −486.93 Hz. These terms can cancel;
their medians must not be added as if they refer to the same median observation.
The total signed median difference is −111.91 Hz, despite large absolute errors.
`point-decomposition.csv` preserves signed row-level differences and original
labels. Large tails include possible identity mistakes and are not removed.

## Local dependence, not a posterior covariance estimate

At the strict cold endpoint, conditioned on its 1571 assigned training winners,
an unregularized linear projection of frequency Jacobian columns gives:

| Target direction | Fraction explained |
|---|---:|
| East-position derivative by calibration columns | 92.02% |
| North-position derivative by calibration columns | 44.23% |
| East-position derivative by calibration + independent satellite timing | 99.84% |
| North-position derivative by calibration + independent satellite timing | 99.61% |
| Common-timing derivative by calibration columns | 96.61% |

The design includes actual calibration intercept/drift/c and residual-clock
columns; timing uses one independent derivative column per selected satellite.
This is a local frequency-only dependence diagnostic. It omits priors,
assignment uncertainty, visibility derivatives and a full Hessian. It cannot be
interpreted as a posterior variance, a calibrated confidence interval or proof
that any chosen satellite is correct. It does explain why a strict training KKT
result alone cannot establish stable geometric/calibration extrapolation.
Relative timing RMS is 8.34 s cold versus 6.80 s at the full-data original endpoint.

## Next direction

The immediate justified assay is deterministic alternating 20 s whole-probe
training/held blocks spanning the full known capture. Re-run discovery and all
calibration only on training probes; preserve complete metadata for propagation.
This tests missing-segment interpolation while separating it from new-satellite
forecasting. It must be labelled as interpolation, retain all original held
denominators, and be matched with c=0 before a fitted-c comparison is interpreted.
No result of that separate assay is used by this diagnosis.

If a forecasting model is required, the single structural change supported by
the inventory evidence is **time-covered candidate support with a population
detection prior**: retain candidates eligible from causal TLE/RF/full known time
metadata even when training discovery gives them little or no evidence; learn
existing timing/calibration from training and shrink unsupported candidates to
declared population timing/detection priors. Hard training-only selected-ID
pruning cannot forecast an absent ID. This is a proposed model, not a measured
recovery, and must face the original clutter/normalizer and false-assignment
cost. Another geographic or timing search does not repair that structural
absence. Interpolation evidence should be obtained before adding this complexity.

## Reproducibility and limits

`diagnose.py` reads frozen receipts and replays original full and cold models
through public read-only source/preparation/orbit/selection APIs. It records
input hashes, exactly checks original point labels/residual replay and strict
cold acceptance, and performs no optimization. Station reference coordinates
are not used to seed, choose or compare any state. The prior remains unchanged.
This diagnostic addresses one fitted-c early→late run; it is not a new matched
c0 scientific comparison or an all-five predictive result. No RF or production
changes, no sealed output changes, no held-data fit.

Three hardware-free tests verify disjoint accounting, mask conservation and
local linear-dependence calculations. `report.py` only plots saved arrays.
