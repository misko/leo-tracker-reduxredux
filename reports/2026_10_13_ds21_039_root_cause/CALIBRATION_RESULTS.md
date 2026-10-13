# DS21-039: calibration, timing and recorded RF consistency

The completed Direction 2 receipts show no native-time or RF-scaling discrepancy.
They show substantial coupling between c, band contrasts, geography and satellite
timing. They do not establish a physical LNB error or identify a calibration
change that would improve localization.

The complete `diagnostics-v2` common run finished in **38.729 seconds**, with all
13 receipts and pre/post validation of the 319-source closure and input inventory.
All four calibration receipts are **byte-identical** to their v1 counterparts;
the findings below therefore retain their original calibration evidence while
the complete v2 run verifies the full pipeline. It made zero optimizer calls.

The original `diagnostics-v1` run remains an immutable failed attempt. It stopped
after 34.357 seconds with
`ValueError: Aligned normalized native per-window moments required` in the later
weighting stage. Its three calibration receipts and cross-view comparison had
already been written and are hash-bound by its terminal; final source
post-validation was not reached in v1. V2 used a separate freeze and directory,
preserving that failure rather than overwriting or silently resuming it.

All results use the original fitted-c training winners: start 5, `shape-all`, in
all three views. The unchanged bank has 43 satellites. There were zero optimizer
calls, temporal edges, held scores or reference reads. No DS21 predictor or fit
was rerun to produce this report. Complete per-channel/RF/time/block summaries,
timing lists and the cross-view native-ID tables remain in the original receipts.

## Physical port checks

Native IDs, source windows, receiver/channel, recorded RF and candidate receive
times match the public scanner projection. Native time and clock-design errors
are exactly zero. The physical frozen calibration function equals the direct
native model correction exactly in all three views.

At the same geography, receive times and satellite timing shifts, Doppler scales
linearly with each observation's recorded RF. The largest discrepancy against
the fixed 12 GHz reference prediction is 1.16e-10 Hz; relative Doppler, spatial
and timing discrepancies are below 5.5e-16. Visibility is identical. The original
likelihood/posterior and likelihood-only gradient replay gates pass.

Recorded CH1–8 RF anchors are 10.7096875, 10.9596875, 11.2096875, 11.4596875,
11.7096875, 11.9596875, 12.2096875 and 12.4596875 GHz. This checks the model's
use of those recorded hypotheses. It does not attest the physical LNB mode;
existing recording provenance does not establish an independent mode switch.
The results provide no new reason to repeat the previously adverse simple LO
relabeling controls.

## Learned state and residual support

| Training view | Windows / native alternatives | Signal / clutter mass | c (Hz/GHz) | Common timing (s) | Signal-weighted total timing RMS / maximum (s) | RX0 / RX1 residual RMS (Hz) |
|---|---:|---:|---:|---:|---:|---:|
| All | 2,798 / 3,714 | 2,068.05 / 729.95 | −626.58 | −1.465 | 4.888 / 16.117 | 99.02 / 112.38 |
| Low | 1,692 / 2,294 | 1,291.52 / 400.48 | −577.79 | −1.954 | 4.553 / 17.075 | 96.24 / 84.21 |
| High | 1,106 / 1,420 | 749.06 / 356.94 | −589.31 | +0.342 | 5.244 / 17.097 | 74.94 / 108.44 |

The all-band learned high-minus-low receiver contrasts are −23,922.93 Hz for RX0
and +37,741.28 Hz for RX1. Their original training high-band fractions are
0.403127 and 0.381331. These are fitted model terms, not measured hardware
offsets. Half-view contrast columns are absent, and their receiver intercepts
use different time/RF centers; raw intercept comparisons would be misleading.
No recorded coefficient, total timing or radial constraint is active. Every
satellite has some positive posterior mass, which does not imply strong support
for every satellite or a measured identity.

Receiver-wide mean residuals are within 1.1e-5 Hz of zero, as expected with free
intercepts. This is not independent calibration evidence. In the all-band fit,
CH1 has the largest residual RMS, 177.18 Hz, and only 122.89 signal mass among 324
windows; the remaining 201.11 is clutter. Its low-only RMS is 109.24 Hz with
171.73 signal mass on the same 324 windows. The posterior changes with the fitted
state, so improved conditional RMS cannot establish localization accuracy.

All-band channel mean residuals range from −10.29 to +7.37 Hz, while original
20-second block means range from −28.25 to +54.57 Hz. Blocks 7 and 8 have means
−28.25 and −26.65 Hz; block 9 has +54.57 Hz. This suggests examining acquisition
and association composition jointly with the weighting direction. It does not
by itself justify a receiver clock spline or more transmitter slopes. Native
alternatives and acquisition blocks are not claimed to be independent samples.

## Conditional calibration/timing design

The following fractions are retained **squared column norms** in the
fixed-responsibility weighted prediction design, not posterior variances or
identifiability probabilities.

| View | c after RX affine | c after RX affine + band contrasts | c after all other physical columns | c scaled residual Gram |
|---|---:|---:|---:|---:|
| All | 94.16% | 20.50% | 10.55% | 150.615 |
| Low | 97.97% | 97.97% | 34.39% | 70.793 |
| High | 92.21% | 92.21% | 33.12% | 36.233 |

The first two all-band projections show that band contrasts absorb much of the c
direction. Geography and satellite timing absorb further structure. The low and
high models have no band-contrast columns; their further reduction comes from
geography/timing. The c residual remains rank one in every view. Thus this local
design does not diagnose complete loss of c rank, but neither does it justify
treating c as an independently measured hardware property.

The joint all-band c/two-contrast target remains rank three after RX affine,
geography and timing projection. With declared scales 200 Hz/GHz for c and
5,000 Hz for each contrast, its Gram eigenvalues are 150.266, 236,303.343 and
370,268.764, giving condition 2,464.09. That condition depends on the stated units.
The calculation retains the original 159,702 latent rows in numerical rank
tolerances despite joint QR compression. The low/high designs retain 98,642 and
61,060 rows. Priors and assignment uncertainty are excluded; these are optimistic,
unconstrained local design summaries, not observed Fisher information,
confidence limits or evidence of a globally correct mode.

## Physical correction comparison on identical observations

Frozen functions are evaluated on the same native candidate IDs, receive times,
RF anchors and receivers. These are unweighted function differences, not a new
fit or residual likelihood comparison.

| Half versus all | RX | Common native alternatives | Mean half − all (Hz) | RMS difference (Hz) | Maximum absolute difference (Hz) |
|---|---:|---:|---:|---:|---:|
| Low | 0 | 1,499 | −85.01 | 102.08 | 203.64 |
| Low | 1 | 795 | −70.06 | 77.31 | 141.16 |
| High | 0 | 977 | −30.44 | 86.32 | 175.91 |
| High | 1 | 443 | −54.64 | 89.70 | 172.92 |

Every comparison lies within both functions' receiver-specific observed RF/time
domains. Applying the low function to the full inventory would put 1,420 native
alternatives outside its RF domain; applying the high function would put 2,294
outside its RF domain. There are also six/nine full-inventory times outside the
low/high receiver time intervals. Those opposite-band predictions are not made.
The measured function differences show that jointly changing geometry, timing
and association changes the learned correction; they do not measure hardware
instability.

## Recommended next intervention

The complete v2 association factorial results compare the same native
observations and recorded signal/clutter priors. Relative NLLs below use the
full-model geometry/timing **and** full-model correction as zero; lower is better.
“Geometry” includes the entire saved satellite timing state.

| Half-view support | Half correction only | Half geometry/timing only | Both half states | NLL interaction |
|---|---:|---:|---:|---:|
| Low: 1,692 windows | +283.72 | −150.85 | −456.81 | −589.69 |
| High: 1,106 windows | +152.01 | +642.94 | +478.58 | −316.37 |

All original half-view windows and native candidate sets match exactly; none are
excluded. A copied half-view correction worsens NLL on both supports when the
full geometry/timing is retained. At half geometry/timing, however, its associated
half correction improves NLL by 305.97 on low and 164.36 on high. The nonadditive
interactions show that a learned correction is coupled to the fitted physical
state and association. Full-to-half posterior mean total-variation changes are
0.185/0.206, with 310/225 satellite-or-clutter MAP changes. Those are conditional
model changes, not measured identity changes.

These signs persist when original acquisition blocks receive equal weight. On
low support, correction-only, geometry/timing-only and both-state mean NLL
changes are +0.186, −0.056 and −0.255; on high they are +0.142, +0.403 and +0.252.
This is not an effect isolated to one large block, and reweighting the frozen
states does not itself reconcile them. High's own state has lower conditional
native residual RMS (90.10 versus 93.96 Hz) while having worse NLL and less signal
mass (749.06 versus 835.17): residual RMS alone would give a misleading ranking.

The ranked next actions are:

1. **Complete the already declared geography-fixed nuisance profiles.** Use the
   original low, high and all geographic anchors with the same all-band model,
   original observations, six physical starts, bank, fitted c, timing priors and
   bounds. Jointly refit the existing calibration and timing terms at each
   anchor; compare the full objective and per-band likelihood ledger with priors
   counted once. This can distinguish incomplete nuisance optimization from a
   persistent training preference while preserving the existing physical model.
2. **If the profiles retain a cross-band tradeoff, prioritize one declared
   objective-balancing control with Direction 4.** Keep the existing calibration
   functions jointly fitted, all observations, bank and starts. A prespecified
   band/block weighting control must keep the overall likelihood/prior scale
   matched; it must not select weights using position errors. The receipts show
   a tradeoff worth testing, not evidence that a particular weighting scheme
   improves accuracy. Do not substitute independent half-view calibration
   functions, which already fail the fixed-full-geometry comparison.
3. **Defer hardware calibration transfer, RF relabeling and tighter timing or c
   priors.** Neither port closure, conditional Gram rank nor similar learned c
   values provide the missing physical hardware/configuration attestation. A new
   calibration model needs repeatable residual evidence and a separately frozen
   matched control; these receipts do not select one.

Direction 2 currently argues against an RF-scaling correction, another simple LO
relabel or a stronger hardware/timing prior. Large timing shifts may represent
association mismatch rather than physical orbit errors, and the existing 2-second
relative timing allowance was introduced for that mismatch. A later calibration
change needs repeatable residual structure on actual supported observations and
independent hardware/configuration provenance. Better frequency fit alone cannot
claim progress toward the localization target.

## Source bindings

Compact source-bound extraction: [calibration-results-v1-summary.json](calibration-results-v1-summary.json).
Complete-run byte verification and factorial extraction:
[calibration-results-v2-verification.json](calibration-results-v2-verification.json).
Full records remain under the authoritative root study's `local/diagnostics-v1`
and `local/diagnostics-v2`.

- V1 protocol SHA-256: `b7299ac307083da421610c0f4076e1921c7eb8b9e82f9f58b44ad6f1057b7218`.
- Input inventory SHA-256: `27bd4bbb567c6d16a819467f92924b813d5547928dc6c51bcaba743924917356`.
- V1 failed terminal SHA-256: `9c4f682df02185cf374cbf4294eb15d0f2fa18b4a06cf416ba10d9ca4c6a9dee`.
- V2 protocol SHA-256: `d6ac7aa2e9b9fc32c9c1cb1713cc8a4b3ac1b63e167671ba5c56fae138c3fd52`.
- V2 complete terminal SHA-256: `1e082d95de47715ef600d000adb9b89dbd4f722bda7b33754b560aa0388f15aa`.

| Byte-identical v1/v2 calibration receipt | SHA-256 |
|---|---|
| all | `68e4b3f029cc6ae6584119436d5201d3369c87f1567f35af868c3c879f8c1a71` |
| low | `5fd2d93bd4806797b0b6984d07e81f755437bd6a173c0aa9ce42967497207785` |
| high | `2ca2d16790314d5b588ee1a31a97c3e2dd7bb0c3cc9fd5ab863110df99c18302` |
| cross-view | `0bce3bdaf03366db15f7a214c1e4dc5d823aa3c1c1562b7c9fe0c23a9aa5b0a3` |

The compact extraction verifies calibration receipt bytes and hashes against
both terminals, preserves the failed-v1 bindings and adds complete-v2,
association-factorial and weighting receipt bindings. Calibration module hashes
are unchanged. V1 binds its 318-source pre-run closure; v2 binds its complete
319-source pre/post closure and local archives.
