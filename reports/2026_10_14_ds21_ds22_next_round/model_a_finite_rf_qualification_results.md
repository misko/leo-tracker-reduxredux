# A035/A053: finite LO hypotheses with exact calibration-function preservation

Both fixed-LO alternatives worsen the native training likelihood at the saved states and fixed candidate banks. The qualification itself passes exactly at the recorded mapping and preserves the additive calibration function at every native row under each finite mapping. This is **conditional fixed-bank sensitivity**, not evidence that the external hardware used the recorded split LO, and not a new position result. No fits, reference/held access, RF collection, mapping selection or algorithm promotion occurred.

[Complete receipts and numeric summary](model_a_finite_rf_qualification_results.json) bind frozen source `4fe3b8431`, the actual [recording metadata](model_a_rf_mapping_metadata.json), all six mapping states, the successful derivative authority and outer wave143. The [prior-art and derivative report](model_a_rf_mapping_prior_art_results.md) explains the unconfirmed physical LO, previous conditional fixed-LO controls and satellite frequency/timing confounding.

## Exactly what changed

Each case retains its own training-selected state, fixed union bank (035:55; 053:59), observation/CFO inventory, candidate order, geography, original disk, absolute satellite shifts, clocks, priors and fitted `c`. RF is reconstructed from the actual saved Pluto IF readbacks plus one of three explicitly conditional references:

- Recorded split: 9.75 GHz for CH1–4, 10.6 GHz for CH5–8.
- Both 9.75 GHz: CH5–8 RF changes by −850 MHz; CH1–4 is unchanged.
- Both 10.6 GHz: CH1–4 RF changes by +850 MHz; CH5–8 is unchanged.

`PositionObservations.rf_center_hz` is recomputed as the native mean of unique RF values, and the original five-column design is rebuilt by the unchanged `PositionObjective`. Receiver lines use **raw receiver intercepts**, while the learned `SequentialShift` uses **uncentered high-group offsets**. Final A has `group_count=0` and an empty centered `GroupCalibrationFrame`; no centered contrast/high-fraction coefficient is substituted for that shift.

For group RF changes ΔL/ΔH and centers f0/f0′, the exact functional transport is:

```
c′ = c
a′_r = a_r + c * ((f0′ − f0) − ΔL) / 1e9
h′_r = h_r − c * (ΔH − ΔL) / 1e9
```

Receiver drift, common clock, original baseline, geography and timing stay exactly fixed. The original uncentered high shift is removed from the baseline, and the transported uncentered shift is added once. Every native row's additive correction is checked directly. No optimizer, calibration refit, clipping, alias rebranch or initializer projection is used. This deliberately isolates finite **orbital RF scaling** from arbitrary changes in the additive calibration function; it is not an optimized fit under each RF mapping.

Both fixed alternatives have the same centered RF design here, although their absolute carrier labels differ by 850 MHz. For 035, each raw receiver intercept changes by +259.274726 Hz and each uncentered high offset by −518.549451 Hz. For 053 those changes are +294.363155 and −588.726311 Hz. These are changes of representation that preserve the correction, not newly learned offsets.

## Qualification and accounting

Five component tests and Ruff pass. Tests include actual native orbit/likelihood evaluation, exact identity full-gradient/posterior nesting, all-row correction transport, finite RF scaling, explicit alias-bound rejection and public two-case end-to-end serialization. The successful scientific audit took **3.972 s**; outer wave143 took **7.618 s**, within 120/135/140 seconds internal/TERM/KILL.

There were **eight objective evaluations and six explicit native predictions**, plus eight native predictors internal to the objectives. All are counted. There were zero optimizer, reference or held calls. Original and transported states are source checked before/after; all 32 recording metadata files are hash checked and pinned. Failed RF derivative v1 receipts remain unchanged in their separate namespace.

| Certificate | Result |
|---|---:|
| Recorded mapping: objective, full vector/nuisance gradients, NLL and responsibilities | **Exact zero difference**, both cases |
| Maximum additive correction error, every native row | 1.456e−11 Hz |
| Maximum finite orbital scaling closure error | 1.165e−10 Hz |
| Visibility changes | 0 |
| Original timing/clock prior-cost change | 0 |
| Projection / alias rebranch / geography or timing changes | None |

The native Doppler prediction closes to `D_new = D_old × RF_new/RF_old`. That test is finite, rather than extrapolating the earlier infinitesimal derivative across 850 MHz.

## All conditional outcomes

Likelihood NLL and posterior RMS describe frequency evidence. Signal mass is the sum of original marginalized satellite probabilities, not a count of confirmed physical identities. The RMS can change with association/mass and is not a position-accuracy metric.

| Case / RF hypothesis | Training NLL | NLL change | Signal mass | Posterior RMS, Hz |
|---|---:|---:|---:|---:|
| 035 recorded split | 35268.898440 | 0 | 2186.952 | 85.132 |
| 035 both 9.75 GHz | 38015.851016 | +2746.952577 | 1518.950 | 109.557 |
| 035 both 10.6 GHz | 39535.598042 | +4266.699603 | 1143.694 | 129.890 |
| 053 recorded split | 23213.121098 | 0 | 1299.061 | 85.727 |
| 053 both 9.75 GHz | 24318.757758 | +1105.636660 | 1015.875 | 99.318 |
| 053 both 10.6 GHz | 26285.661488 | +3072.540390 | 515.750 | 134.012 |

The prior cost stays **373.920812** for 035 and **285.542637** for 053. Thus these objective differences equal likelihood differences and do not arise from changing timing/clock penalties.

For both-9.75, unchanged low-group signal mass is exactly retained, while changed high-group mass falls **866.016→198.015** (035) and **364.016→80.830** (053). For both-10.6, unchanged high-group mass is retained, while changed low-group mass falls **1320.936→277.678** and **935.045→151.734**. This confirms that the RF intervention affects the intended group's orbital evidence after calibration-function preservation.

Among windows with majority signal support in both states, dominant candidate IDs change in **145/209** windows for 035 and **46/115** for 053 under both-9.75/both-10.6. Mean full candidate-posterior L1 changes are **0.354/0.527** and **0.231/0.569**. All alternative states remain reported; there is no best-hypothesis selector.

One existing constraint is explicit: 053's saved RX1 high shift is exactly **+ALIAS_HZ/2 = 113636.363636 Hz**. The identity preserves that endpoint; both finite transports move it **588.726311 Hz** inside the same allowed branch. The check does not jump branches or interpret this active bound as measured hardware behavior.

## What this does and does not resolve

The previous local derivative signs were not a test of discrete fixed LO hypotheses; this finite check fills that gap at the current states. Neither alternative is a small, unnoticed relabeling under the unchanged bank and assignments: losses increase substantially and signal support changes. The observed poor conditional scores do **not** reject a physical fixed LO. These banks and basins were discovered under the original labels, and a finite carrier change can require different associations or candidate search support. No fresh association search or nuisance optimization under the alternatives was authorized or performed.

Both recordings still explicitly call the split references hypotheses and record no physical LNB switching. The physical LNB make/model, per-receiver topology, actual LO/state/lock and frequency authority remain missing from the inspected metadata. A recording-bound hardware answer can determine the scientifically meaningful next RF mapping; successful algebra or lower in-sample loss cannot supply that authority. No additional RF-model fit is promoted from this check.
