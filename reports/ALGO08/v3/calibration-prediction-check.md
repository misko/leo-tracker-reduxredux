# Predictive RF error flags the translated DS30-0016 fix

Fitting `c` cut conditional RMS on the translated DS30-0016 proposal
from **154.682 to 147.984 Hz** while increasing its predictive-role mean
squared error **242.156×**. The same 23 predictive and 92 conditional
observations, satellite owners, roles and order were present in both
arms. In the correct offer the increase was **1.104×**. This distinguishes
the two published 20/8 outcomes using one runtime result at a time,
without a site reference or another search. Fit error on the translated
offer was **183.656 km at c = 0 and 176.717 km at fitted c**. Reverting
to the fixed arm would still return a distant false fix.
[Qualified original pair](history-risk-0016-omitted.md)

The frozen RF-only warning passed all six evaluable valid publications.
It also passed a known South false fix and could not score three other
false fixes. Keep it as evidence of calibration instability. A
geographic withholding policy would still miss those failures.
[Frozen rule](calibration-prediction-check-protocol.md)

## Observable and coverage

For each arm, subtract the conditional sum of squared residuals from
the all-owner sum, then divide by the predictive count. The rule flags
when fitted `c` lowers conditional RMS and more than doubles predictive
mean squared error. The 3 dB threshold was fixed before the new
readback. Require the same ordered owner and role rows and nonempty
conditional and predictive partitions. A runtime wrapper can sum the
existing raw predictive residuals from `linear_raw_prediction_residual_hz`
at the solver-to-publication handoff. This assay derives the same role
statistic from the saved terminal and standard figure manifest already
linked to the same input. It ran no further orbit projection, solve or
render. Predictive-role measurements can share tracks, candidate
selection and fitted nuisance parameters. The ratio has no independent
sample confidence interpretation.
[Standard residual source](../../../src/leo/presentation/localization_v3.py)

| Existing publication | Geography after readback | Conditional / predictive rows per arm | Fitted ÷ fixed predictive MSE | Readout |
| --- | --- | ---: | ---: | --- |
| DS30-0016 containing, 20/8 | Valid | 92 / 23 | 1.104 | Pass |
| DS30-0016 translated, 20/8 | False fix | 92 / 23 | **242.156** | Suspect |
| DS30-0016 containing, named v3 | Valid | 90 / 19 | 0.949 | Pass |
| DS30-0016 translated, named v3 | False fix | 90 / 0 | — | Unavailable |
| North containing, 20/8 | Valid | 323 / 19 | 1.268 | Pass |
| North far, 20/8 | Correct withhold | — | — | Existing withhold |
| North containing, continued receiver | Valid | 304 / 0 | — | Unavailable |
| North near, continued receiver | False fix | 304 / 0 | — | Unavailable |
| South containing, 20/8 | Valid | 285 / 19 | 0.209 | Pass |
| South near, 20/8 | False fix | 285 / 19 | 0.208 | Pass |
| South containing, named finish | Valid | 266 / 0 | — | Unavailable |
| South near, named finish | False fix | 266 / 0 | — | Unavailable |
| DS30-0169, original 20 ms | Valid | 1,782 / 454 | 0.469 | Pass |
| DS30-0004, original 20 ms, independent readback | Valid | 2,418 / 1,012 | 0.866 | Pass |

This is **zero warning flags on six evaluable valid publications**,
with two further valid runs unavailable. One of two evaluable false
fixes flagged, while three other false fixes had no predictive rows.
Withholding solely because predictive support is empty would also
reject the valid North continued and South named results.
The archive is five recordings or simulation waveforms, with repeated
offers and methods within site. It does not establish a false-withhold
rate. The India external pair has 506 conditional and 11 predictive
observations, but the saved numerical package lacks the corresponding
standard all-owner residual and exact ordered role witness. Its false
fix is outside this comparison denominator.
[North and far control](history-risk-raw.md) · [North continuation](raw-cfo-north.md) · [South 20/8 pair](eight-ms-south-transfer.md) · [South named pair](named-south-transfer.md) · [India regional diagnosis](india-regional-diagnostic.md)

The independent control was the already saved, length-enrolled
DS30-0004 physical acquisition. The feature-only readout was sealed
before joining its archived location evidence. The new statistic
passed at 0.866 and its prior correct fixed-zero/fitted errors were
184.741/103.808 m. The recording is independent of the weak 20/8
development waveform and uses the same physical site. DS30-0169 is
corroborating retrospective evidence under the same roof. Neither is
an independently surveyed new geography.
[DS30-0004 enrollment and sealed fit](history-risk-0004.md) · [DS30-0169 fit](history-risk-held-0169.md)

## Why the region remains unresolved

The recorded 0016 regional proof already compares the independent
receiver likelihood sums. The original 96-point lattice's unique far
winners disagreed by **25.495 km** and the extra eight frozen points
increased separation to **102.133 km**. Both receivers scored better
at the site only when given that location as a post-seal diagnostic.
The extra scout therefore supplies no candidate for the original
workflow. The South near omission is more restrictive. Its known bad
and good offers have the same ordered owners, and predictive MSE
improves under fitted `c` in both. The fixed rule cannot distinguish
these valid and invalid outputs. The archived geographic jackknife
also left both 100 m omissions unresolved, and a simple hard-face
condition could reject valid North fits while keeping the South
result. This test provides no grounds to promote a new withholding
gate or claim a speed/accuracy qualification.
[Physical exterior scout](history-risk-0016-exterior-scout.md) · [Geographic jackknife](geographic-jackknife.md) · [South face clearance](exact-named-south-omitted.md)

The reducer read only small, pinned saved publication records on
tmpfs. The first extraction stopped on the persisted `ok` enum
before producing any RF screen output. Correcting the extractor
preserved the frozen rule. Four component tests cover the RF
arithmetic, absent or unmatched evidence, and saved owner binding.
The [receipt](measurements/calibration-prediction-check.json.gz)
contains both independent sealed feature sets and every product pin.
