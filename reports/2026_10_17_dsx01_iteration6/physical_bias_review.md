# RF-scaled satellite bias: physically conditional, too small to explain the failed prediction

Do not launch a fractional-bias fitting campaign from the present evidence.
An RF-scaled offset is dimensionally appropriate **if** a satellite has one
fractional frequency error shared by the relevant carriers. That premise is not
established by these recordings. At the frozen estimates, changing constant-Hz
bias to RF-scaled bias leaves 39/40 temporal conditional tests worse than their
zero-bias baseline. Every challenge window is single-RF, so this change cannot
repair a fixed candidate's time curvature within that window.

No new model was implemented or fit. This review uses existing frozen states,
exact likelihood algebra and known RF metadata. No station/reference coordinates,
manual satellites, extra observations or held-based parameter selection enter
the calculation. Original full-data labels below are descriptive, not truth.

## What the alternative means

Use the fixed metadata-only reference **f_ref = 11.7 GHz**, the center of the
16 distinct actual RFs across all five recordings. It was declared before the
frozen-state likelihood calculation. Compare constant `b_s` with
`b_s * actual_RF / f_ref`, retaining every saved coefficient, physical state,
clock, band calibration, q and visibility. No coefficient is optimized or chosen.

The existing audited Doppler kernel already predicts
`-actual_RF * radial_velocity / 299792.458` with velocity in km/s. Thus orbital
Doppler already scales with RF; the proposal changes only the additional bias.

| Mechanism or model | First-order form | What remains unproved |
|---|---|---|
| Fractional satellite transmitter reference error | `epsilon_s * carrier_RF` | One shared fractional error across these nominal carriers; their actual transmitter architecture is unknown here. Actual receiver RF is a proxy for nominal carrier RF. |
| Orbit velocity error | `-RF * delta_radial_velocity_s(time) / light_speed` | The projected velocity error generally depends on time and line of sight. A constant fractional offset is only a possible local approximation. |
| Existing shared receiver RF calibration c | `c * (RF - RF_center) / 1e9` | This empirical term is not proof of a particular LNBF or oscillator cause. It is shared across receivers/candidates. |
| Receiver band constant | `delta_RX * high_band` | A receiver/channel-group step is not satellite-specific fractional error. |
| Existing empirical satellite bias | `b_s` Hz | Its cause and temporal stability were never established. |

At 11.7 GHz, 1000/4000 Hz correspond to fractional errors of 0.0855/0.3419 ppm,
or equivalent constant projected velocity errors of 25.62/102.49 m/s. These are
unit conversions, not measured transmitter or orbit errors. No assumption about
Starlink clock architecture or Doppler compensation is needed or claimed.

There is also an exact calibration gauge: adding the same reference bias d to
every RF-scaled satellite term can be absorbed by adding `d/11.7` Hz/GHz to
common c and `d*RF_center/f_ref` Hz to both receiver intercepts. Proper population
regularization/gauge declarations would be necessary in a future joint model.
RF scaling alone cannot distinguish satellite error from shared calibration.

## Actual RF leverage

All 20,084 observations use one of two eight-frequency plans. S01/S03/S05 have
an RF center of 11.5846875 GHz; S02/S04 use 11.8153125 GHz. Relative to the fixed
11.7 GHz reference, the overall range is **0.915358–1.084642**. Therefore the
largest literal scaled-minus-constant change is **84.64 Hz at b=1000 Hz**, or
**338.57 Hz at b=4000 Hz**. Negative b reverses the signs, not the bounds.

Choosing a recording's own center as the reference would reduce the fractional
range to ±7.553% or ±7.406%. Reference frequency is a unit convention only if
amplitudes and priors are transported consistently; it is not a knob to choose
from held performance. The calculation here uses only the fixed 11.7 GHz rule.

All 15 frozen windows are single-frequency. The signed changes below assume
positive reference b; denominators remain the original 693 winners.

| Window | N | Actual RF GHz | RF/f_ref | Change at b1000 Hz | Change at b4000 Hz |
|---|---:|---:|---:|---:|---:|
| 001 | 86 | 11.4596875 | 0.979460 | −20.54 | −82.16 |
| 002 | 35 | 10.9596875 | 0.936725 | −63.27 | −253.10 |
| 003 | 27 | 10.9596875 | 0.936725 | −63.27 | −253.10 |
| 004 | 44 | 10.9403125 | 0.935069 | −64.93 | −259.72 |
| 005 | 33 | 11.4403125 | 0.977804 | −22.20 | −88.78 |
| 006 | 72 | 11.1903125 | 0.956437 | −43.56 | −174.25 |
| 007 | 54 | 11.4596875 | 0.979460 | −20.54 | −82.16 |
| 008 | 50 | 11.4596875 | 0.979460 | −20.54 | −82.16 |
| 009 | 34 | 11.7096875 | 1.000828 | +0.83 | +3.31 |
| 010 | 46 | 11.9403125 | 1.020540 | +20.54 | +82.16 |
| 011 | 43 | 11.4403125 | 0.977804 | −22.20 | −88.78 |
| 012 | 66 | 11.4403125 | 0.977804 | −22.20 | −88.78 |
| 013 | 28 | 11.2096875 | 0.958093 | −41.91 | −167.63 |
| 014 | 39 | 11.4596875 | 0.979460 | −20.54 | −82.16 |
| 015 | 36 | 10.9596875 | 0.936725 | −63.27 | −253.10 |

## Half-band composition, including per-object checks

Recording-wide early-to-late high-band proportions change by −3.85, −0.11,
−2.61, +2.12 and +0.13 percentage points for S01–S05. Mean RF changes imply
mean prediction differences of −12.76, +0.29, −8.43, +9.28 and +12.46 Hz even
if b=4000 Hz everywhere. These global means can hide per-satellite changes,
so the following calculations are performed per object before aggregation.

For each frozen conditional fit, compute its unchanged constant-b all-candidate
responsibilities on both halves, then each object's responsibility-weighted
RF means/ranges. Require at least five summed signal responsibilities on each
half for the support summary. This yields 576 object-fit cases over 126 distinct
recording/satellite pairs; repeated fits are not independent objects.

The weighted RF mean ranges are 10.861–12.364 GHz on training halves and
10.793–12.645 GHz on held halves. Absolute per-object mean RF changes have
median 0.244 GHz, 90th percentile 0.626 GHz and maximum 1.050 GHz. RF spans
among rows with responsibility >0.05 have median 1.5 GHz in each half, range
0.25–1.75 GHz. Thus per-object band composition does change appreciably.
However, **using each actual frozen b**, `abs(b*(mean_RF_held-mean_RF_train)/f_ref)`
has median **3.43 Hz**, 90th percentile **29.29 Hz**, maximum **286.14 Hz**;
only 5/576 cases exceed 125 Hz and none exceed 375 Hz. Supported |b| has median
199 Hz and 90th percentile 1111 Hz, explaining why most effects are small.

Responsibility support can disappear when a failed trajectory misses its line.
As a separate descriptive oracle, repeat the object calculation using unchanged
original full-model assigned labels, requiring five original rows in each half.
There are 448 object-fit cases over 56 recording/satellite pairs. Mean RF shifts
have median 0.307 GHz, 90th percentile 0.774 GHz and maximum 0.923 GHz. At each
actual frozen b, resulting mean correction changes have median **3.16 Hz**,
90th percentile **41.30 Hz**, maximum **197.69 Hz**; only 4/448 exceed 125 Hz.
These labels are never used to modify a coefficient or choose a model.

A constant-b estimate is naturally referenced to its training RF mix, not
necessarily 11.7 GHz. The analytical mean-preserving transport
`b*(mean_RF_held/mean_RF_train - 1)` gives similar results: posterior-weighted
median/90th/max **3.53/29.18/307.60 Hz**, original-label **3.16/42.45/191.48 Hz**.
These are additional magnitude diagnostics, not refits or an alternative arm
chosen by its held score. RF composition can explain some modest discrepancies;
it is insufficient as the broad explanation of the temporal failure.

## Uniform frozen-state residual/likelihood check

Reconstruct the same saved baseline using public read-only source/orbit/replay
APIs, with no configured station reference. Replay all 40 saved zero-bias and
constant-b held NLLs within 1e−7, then replace only the frozen prediction term
with `b*RF/11.7GHz`. Preserve wrapped residuals, 125 Hz density, visibility, q,
normalizer and original classification. Both directions pooled count every
original observation once per arm/width. The baseline is already full-data
conditioned; this is conditional residual diagnosis, not clean cold validation.

| Existing c arm / bias prior width | Constant held ΔNLL | RF-scaled held ΔNLL | Constant→scaled assigned /20,084 |
|---|---:|---:|---:|
| fitted /300 Hz | +15,175.05 | +15,137.42 | 10,789→10,799 |
| fitted /1000 Hz | +24,388.50 | +24,446.38 | 8,307→8,282 |
| zero /300 Hz | +7,353.15 | +7,309.66 | 8,380→8,378 |
| zero /1000 Hz | +13,582.27 | +13,540.29 | 6,456→6,460 |

ΔNLL is relative to the unchanged zero-bias baseline in that arm; positive is
worse. Both the original constant test and this scaled calculation worsen held
NLL in **39/40** cases. Changes of tens of NLL do not resolve deficits of
thousands. No width or reference is selected from these results. The zero-c
label means the existing common receiver c was fixed zero; the diagnostic now
contains an explicitly RF-scaled satellite term and is not an all-RF-effects-off
ablation.

For fitted-c/1000 Hz, 6,746 held rows have constant-model nearest visible
candidate residual >1000 Hz. Even allowing the full |b|≤4000 Hz scaling bound,
9,986 held rows cannot reach any visible candidate within 375 Hz by this literal
transformation. These include original clutter/unassigned observations: they
are frequency-proximity diagnostics, not verified lost emitters or an assignment
criterion. The actual unchanged likelihood check above is the stronger result.

On TRAIN halves, literal scaling worsens NLL relative to the frozen constant
estimate by +11.63/+137.95 for fitted-c widths 300/1000 and +146.63/+366.69 for
zero-c widths 300/1000. It is not an optimized fractional coefficient; the
training-mean-preserving magnitude check above addresses the reference-frame
mismatch analytically without fitting or selecting another held-scored arm.

This does not prove that a newly refit fractional model could never improve
another basin. It shows that RF scaling of the frozen estimates, including
measured per-object RF composition shifts, does not rescue this failed temporal
prediction. The constant-b in-sample eight-window result remains descriptive.

## Evidence and proposed stopping point

Use [frozen conditional receipts](../2026_10_17_dsx01_iteration4/frequency_bias/conditional_results/),
[the existing likelihood implementation](../2026_10_17_dsx01_iteration4/frequency_bias/conditional.py),
and [fixed source membership](../2026_10_16_dsx01_fast_association_losses/membership.csv).
The metadata export SHA256 is
`ddf587ed93815f911ddaf7cc0984a6df5b70ea8f8906944dae67a919418e781b`;
membership SHA256 is
`e5e8c7c7244dba6aa53c565f741092615b46e6a2c4cac673b626f171cb92fe86`.
Physics/units follow the pinned public `regional_position_score.py` RF design
and `_regional_orbits.cpp` factor `RF/299792.458`; no unsupported transmitter
architecture or literature claim is imported. The complete no-fit calculation
took 88.34 seconds; all scientific endpoints and sealed files remain unchanged.

Keep fractional satellite bias as an unvalidated mechanism hypothesis, not the
next campaign. Stronger independent evidence for a stable within-object
RF-normalized residual would be needed before fitting it. Any eventual model
must retain proper prior/gauge treatment, exact zero-bias nesting and q
normalization, and explicitly define the RF-dependent degrees left in c=0.
Neither frequency fit nor a plausible unit scaling establishes localization or
the physical origin of a residual.
