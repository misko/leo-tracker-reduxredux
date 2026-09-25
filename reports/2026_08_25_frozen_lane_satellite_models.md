# Strict duration result and relaxed Starlink orbit sweep

## Primary strict answer

**Zero satellite assignments are eligible under the strict >= 1.0 s fully qualified known-pilot-frame gate.** The persisted analyzed inventory contains only 2 isolated qualified windows, each approximately 75 ms. They do not form a one-second coherent-rate run.

Frame evidence is incomplete across the full final-track inventory, so this is a zero-eligible result under the currently persisted strict evidence—not proof that no one-second physical transmission existed.

## Relaxed raw/dealiased trajectory-support surrogate

### Scope

This exploratory run evaluates 11 continuity-supported pieces split from 14 radio-only dealiased branches from `cap-20260824T192531-491832825b97` / `stream-1` / `radio_pluto_19f2` RX1 at 11.190312500 GHz. Satellite choice and nuisance parameters use only an initially chronological 60/40 split. The seeded holdout is then closed globally over shared sample epochs and exact source-observation IDs, leaving an actual global training fraction of 47.7%. The grouped holdout never selects satellites or fitted parameters.

A piece must span at least 1.00 s, contain at least 28 distinct 20 ms probe epochs, occupy at least 70% of the expected 40/s schedule, and have no inter-observation gap over 0.100 s. 71 split pieces failed one or more gates; the JSON accounts for each one.

Grouped-split audit: 0 sample-start overlaps and 0 exact source-ID overlaps between training and holdout.

The causal catalogue contains 10972 objects; 497 were above the 0.0° horizon somewhere in the fitted interval after propagation/plausibility screening.

Observer geometry uses the external Sausalito preset (37.858988, -122.478103, -29 m) with a nominal 50 m uncertainty. The capture does not contain a GPS/site binding, so this is an input assumption, not captured provenance.

### Holdout acceptance against radio-only nulls

| orbit model | zero-penalty K / holdout | oracle-min K / holdout | radio-only holdout | unit | every K fails |
|---|---:|---:|---:|---|---|
| `rate_only` | 8 / 241.6 | 4 / 213.0 | 156.9 | Hz/s | **yes** |
| `cfo_tau` | 8 / 372.4 | 4 / 282.0 | 150.4 | Hz | **yes** |
| `cfo_tau_quadratic` | 8 / 268.7 | 6 / 264.8 | 144.0 | Hz | **yes** |

**Every evaluated training-greedy K state is rejected:** each has larger grouped holdout error than its matched simpler radio-only null. This does not enumerate or reject every possible identity set; the K sweeps below remain diagnostics, not accepted identities.

### Greedy set-size sweep

K=0 pays the fixed unassigned cost; each later row greedily adds the satellite giving the smallest training cost. Holdout never chooses a satellite, K, composite frequency intercept, delay, or quadratic curvature. For the two delay models, every selected physical satellite has exactly one delay shared by all of its assigned pieces. A physical satellite is also forbidden from owning time-overlapping pieces. Exact source-observation identity is also exclusive across all assigned pieces, independent of NORAD; different candidate IDs at one sample epoch remain allowed.

#### `rate_only`

raw/dealiased trajectory-slope proxy; not reset-debiased ramp rate

| K | selected NORAD@tau(s) | active | assigned | train (Hz/s) | holdout (Hz/s) | same state vs K-1 |
|---:|---|---:|---:|---:|---:|---:|
| 0 | — | 0 | 0 | 500.0 | 500.0 | — |
| 1 | 62024 | 1 | 7 | 329.7 | 346.7 | 0.36 |
| 2 | 62024, 57355 | 2 | 9 | 254.9 | 275.9 | 0.82 |
| 3 | 62024, 57355, 67417 | 3 | 10 | 193.2 | 286.2 | 0.64 |
| 4 | 62024, 57355, 67417, 57339 | 4 | 10 | 177.1 | 213.0 | 0.73 |
| 5 | 62024, 57355, 67417, 57339, 58871 | 5 | 10 | 172.9 | 244.1 | 0.73 |
| 6 | 62024, 57355, 67417, 57339, 58871, 57923 | 6 | 10 | 168.9 | 242.3 | 0.91 |
| 7 | 62024, 57355, 67417, 57339, 58871, 57923, 58103 | 6 | 10 | 167.4 | 241.1 | 0.91 |
| 8 | 62024, 57355, 67417, 57339, 58871, 57923, 58103, 67841 | 6 | 10 | 166.1 | 241.6 | 0.91 |

Activation-penalty selection (training objective only):

| penalty / satellite | K | selected NORAD@tau(s) | train (Hz/s) | holdout (Hz/s) |
|---:|---:|---|---:|---:|
| 0.0 | 8 | 62024, 57355, 67417, 57339, 58871, 57923, 58103, 67841 | 166.1 | 241.6 |
| 1.0 | 6 | 62024, 57355, 67417, 57339, 58871, 57923 | 168.9 | 242.3 |
| 2.0 | 4 | 62024, 57355, 67417, 57339 | 177.1 | 213.0 |
| 5.0 | 4 | 62024, 57355, 67417, 57339 | 177.1 | 213.0 |
| 10.0 | 3 | 62024, 57355, 67417 | 193.2 | 286.2 |
| 20.0 | 3 | 62024, 57355, 67417 | 193.2 | 286.2 |
| 50.0 | 1 | 62024 | 329.7 | 346.7 |

#### `cfo_tau`

shared per-satellite delay with per-lane composite frequency intercepts

| K | selected NORAD@tau(s) | active | assigned | train (Hz) | holdout (Hz) | same state vs K-1 |
|---:|---|---:|---:|---:|---:|---:|
| 0 | — | 0 | 0 | 500.0 | 500.0 | — |
| 1 | 62024@-0.30 | 1 | 7 | 311.2 | 354.9 | 0.36 |
| 2 | 62024@-0.30, 57355@+0.30 | 2 | 9 | 232.4 | 301.2 | 0.82 |
| 3 | 62024@-0.30, 57355@+0.30, 57923@-0.15 | 3 | 10 | 178.9 | 306.9 | 0.82 |
| 4 | 62024@-0.30, 57355@+0.30, 57923@-0.15, 58103@+0.30 | 4 | 10 | 172.5 | 282.0 | 0.91 |
| 5 | 62024@-0.30, 57355@+0.30, 57923@-0.15, 58103@+0.30, 58871@-0.30 | 5 | 10 | 167.9 | 373.8 | 0.82 |
| 6 | 62024@-0.30, 57355@+0.00, 57923@-0.15, 58103@+0.30, 58871@-0.30, 67841@+0.30 | 5 | 10 | 167.2 | 372.7 | 0.91 |
| 7 | 62024@-0.30, 57355@+0.00, 57923@-0.15, 58103@+0.30, 58871@-0.30, 67841@+0.30, 67417@+0.30 | 6 | 10 | 166.5 | 370.7 | 0.91 |
| 8 | 62024@-0.30, 57355@+0.00, 57923@-0.15, 58103@+0.30, 58871@-0.30, 67841@+0.30, 67417@+0.30, 55375@-0.30 | 7 | 10 | 166.4 | 372.4 | 0.91 |

Activation-penalty selection (training objective only):

| penalty / satellite | K | selected NORAD@tau(s) | train (Hz) | holdout (Hz) |
|---:|---:|---|---:|---:|
| 0.0 | 8 | 62024@-0.30, 57355@+0.00, 57923@-0.15, 58103@+0.30, 58871@-0.30, 67841@+0.30, 67417@+0.30, 55375@-0.30 | 166.4 | 372.4 |
| 1.0 | 5 | 62024@-0.30, 57355@+0.30, 57923@-0.15, 58103@+0.30, 58871@-0.30 | 167.9 | 373.8 |
| 2.0 | 4 | 62024@-0.30, 57355@+0.30, 57923@-0.15, 58103@+0.30 | 172.5 | 282.0 |
| 5.0 | 3 | 62024@-0.30, 57355@+0.30, 57923@-0.15 | 178.9 | 306.9 |
| 10.0 | 3 | 62024@-0.30, 57355@+0.30, 57923@-0.15 | 178.9 | 306.9 |
| 20.0 | 3 | 62024@-0.30, 57355@+0.30, 57923@-0.15 | 178.9 | 306.9 |
| 50.0 | 1 | 62024@-0.30 | 311.2 | 354.9 |

#### `cfo_tau_quadratic`

shared per-satellite delay with per-lane composite frequency intercepts

| K | selected NORAD@tau(s) | active | assigned | train (Hz) | holdout (Hz) | same state vs K-1 |
|---:|---|---:|---:|---:|---:|---:|
| 0 | — | 0 | 0 | 500.0 | 500.0 | — |
| 1 | 62024@-0.30 | 1 | 7 | 310.1 | 390.6 | 0.36 |
| 2 | 62024@-0.30, 57355@+0.30 | 2 | 9 | 230.9 | 357.1 | 0.82 |
| 3 | 62024@-0.30, 57355@+0.30, 47752@+0.00 | 3 | 10 | 176.4 | 305.0 | 0.73 |
| 4 | 62024@-0.30, 57355@+0.30, 47752@+0.00, 58103@+0.30 | 4 | 10 | 169.9 | 278.5 | 0.91 |
| 5 | 62024@-0.30, 57355@+0.30, 47752@+0.00, 58103@+0.30, 58871@-0.30 | 5 | 10 | 164.4 | 267.6 | 0.82 |
| 6 | 62024@-0.30, 57355@+0.00, 47752@+0.00, 58103@+0.30, 58871@-0.30, 67841@+0.30 | 5 | 10 | 163.6 | 264.8 | 0.91 |
| 7 | 62024@-0.30, 57355@+0.00, 47752@+0.00, 58103@+0.30, 58871@-0.30, 67841@+0.30, 55375@-0.30 | 6 | 10 | 163.5 | 269.0 | 0.91 |
| 8 | 62024@-0.30, 57355@+0.00, 47752@-0.05, 58103@+0.30, 58871@-0.30, 67841@+0.30, 55375@-0.30, 67417@+0.30 | 7 | 10 | 163.4 | 268.7 | 0.82 |

Activation-penalty selection (training objective only):

| penalty / satellite | K | selected NORAD@tau(s) | train (Hz) | holdout (Hz) |
|---:|---:|---|---:|---:|
| 0.0 | 8 | 62024@-0.30, 57355@+0.00, 47752@-0.05, 58103@+0.30, 58871@-0.30, 67841@+0.30, 55375@-0.30, 67417@+0.30 | 163.4 | 268.7 |
| 1.0 | 5 | 62024@-0.30, 57355@+0.30, 47752@+0.00, 58103@+0.30, 58871@-0.30 | 164.4 | 267.6 |
| 2.0 | 5 | 62024@-0.30, 57355@+0.30, 47752@+0.00, 58103@+0.30, 58871@-0.30 | 164.4 | 267.6 |
| 5.0 | 3 | 62024@-0.30, 57355@+0.30, 47752@+0.00 | 176.4 | 305.0 |
| 10.0 | 3 | 62024@-0.30, 57355@+0.30, 47752@+0.00 | 176.4 | 305.0 |
| 20.0 | 3 | 62024@-0.30, 57355@+0.30, 47752@+0.00 | 176.4 | 305.0 |
| 50.0 | 1 | 62024@-0.30 | 310.1 | 390.6 |

### Zero-penalty per-piece nuisance fits

These are the training-selected K fits shown for auditability even though the grouped holdout rejects them. `t_ref` is seconds after capture start. The intercept is a composite receiver/path frequency offset at that reference time, not transmitter CFO.

#### `cfo_tau` K=8

| lane piece | NORAD | shared tau (s) | composite offset (Hz) | t_ref (s) | residual curvature (Hz/s²) | train / holdout RMSE (Hz) |
|---|---:|---:|---:|---:|---:|---:|
| `sha256:9055a61d43d6079d006511c1216354e25aee04bfffcf6c6a48ff8cffa69e5c12#support-00` | 67841 | +0.30 | -27783.6 | 1.681 | — | 65.2 / 143.7 |
| `sha256:31ff12579ffb9004ffee7c01c48d41ed0bf647ff8126cb4c0737ec5b95986c7f#support-02` | 67417 | +0.30 | +127746.5 | 2.761 | — | 32.6 / 59.4 |
| `sha256:f3cb5c4fca726026ff3e6166b790005ad9c05dfcdd11b4e0c107696b14d6ed6c#support-00` | 57923 | -0.15 | -47790.6 | 8.092 | — | 54.4 / 88.3 |
| `sha256:93d392836380eadc719238a7d8e8d8ce0689445e2531ca1f3da5b7d668905640#support-00` | 55375 | -0.30 | +43640.8 | 7.264 | — | 43.1 / 150.3 |
| `sha256:891b2ce6813cf5b6a62c4dc88108c5510eac6d51ef9ebedcbea26362e432d8de#support-00` | 58871 | -0.30 | +78465.9 | 14.702 | — | 116.1 / 1022.7 |
| `sha256:6e751ef20609e2d3ee97aea21014dbfa772c5e23deb79940c265944dc0a208a1#support-00` | 58103 | +0.30 | +11393.5 | 14.811 | — | 52.9 / 148.6 |
| `sha256:88c329e8d19adb67bfa80578d3b384401f50ba53b63e3598bad94fff76110ae8#support-00` | 62024 | -0.30 | -88473.2 | 21.839 | — | 132.3 / 331.2 |
| `sha256:df90e373fef7e203cffe8469f20bc13a32ffe441446696df057822cc4a72ec55#support-00` | 62024 | -0.30 | -87918.0 | 29.463 | — | 59.6 / 107.0 |
| `sha256:21fcac6017b479504c17ec86d2bcf838bf7185f2753bc047d8fbebf9835c5847#support-01` | 62024 | -0.30 | -88212.3 | 37.387 | — | 46.4 / 120.8 |
| `sha256:21fcac6017b479504c17ec86d2bcf838bf7185f2753bc047d8fbebf9835c5847#support-03` | 62024 | -0.30 | -88755.6 | 41.380 | — | 70.6 / 131.1 |

#### `cfo_tau_quadratic` K=8

| lane piece | NORAD | shared tau (s) | composite offset (Hz) | t_ref (s) | residual curvature (Hz/s²) | train / holdout RMSE (Hz) |
|---|---:|---:|---:|---:|---:|---:|
| `sha256:9055a61d43d6079d006511c1216354e25aee04bfffcf6c6a48ff8cffa69e5c12#support-00` | 67841 | +0.30 | -27771.7 | 1.681 | -24.21 | 64.3 / 65.7 |
| `sha256:31ff12579ffb9004ffee7c01c48d41ed0bf647ff8126cb4c0737ec5b95986c7f#support-02` | 67417 | +0.30 | +127751.2 | 2.761 | -200.00 | 32.1 / 50.7 |
| `sha256:f3cb5c4fca726026ff3e6166b790005ad9c05dfcdd11b4e0c107696b14d6ed6c#support-00` | 47752 | -0.05 | +146747.4 | 8.092 | -102.79 | 52.9 / 79.4 |
| `sha256:93d392836380eadc719238a7d8e8d8ce0689445e2531ca1f3da5b7d668905640#support-00` | 55375 | -0.30 | +43634.9 | 7.264 | +200.00 | 41.2 / 201.5 |
| `sha256:891b2ce6813cf5b6a62c4dc88108c5510eac6d51ef9ebedcbea26362e432d8de#support-00` | 58871 | -0.30 | +78500.9 | 14.702 | -98.96 | 101.8 / 172.5 |
| `sha256:6e751ef20609e2d3ee97aea21014dbfa772c5e23deb79940c265944dc0a208a1#support-00` | 58103 | +0.30 | +11399.6 | 14.811 | -17.49 | 52.7 / 106.3 |
| `sha256:88c329e8d19adb67bfa80578d3b384401f50ba53b63e3598bad94fff76110ae8#support-00` | 62024 | -0.30 | -88442.8 | 21.839 | -100.70 | 102.8 / 607.0 |
| `sha256:df90e373fef7e203cffe8469f20bc13a32ffe441446696df057822cc4a72ec55#support-00` | 62024 | -0.30 | -87924.7 | 29.463 | +5.93 | 59.3 / 155.9 |
| `sha256:21fcac6017b479504c17ec86d2bcf838bf7185f2753bc047d8fbebf9835c5847#support-01` | 62024 | -0.30 | -88209.6 | 37.387 | -71.44 | 46.3 / 95.3 |
| `sha256:21fcac6017b479504c17ec86d2bcf838bf7185f2753bc047d8fbebf9835c5847#support-03` | 62024 | -0.30 | -88769.0 | 41.380 | +200.00 | 68.6 / 217.7 |

## Interpretation limits

- These are candidate rankings, not satellite identifications. A scalar Doppler rate is crowded, and a bounded time shift is locally confounded with CFO through `D(t+tau) ~= D(t) + tau D'(t)`.
- The quadratic term is residual Doppler curvature in Hz/s². It is a sensitivity parameter, not a fitted physical orbital acceleration or a TLE correction.
- The reported intercept is a composite receiver/path frequency offset at its stated lane reference time; it must not be interpreted as transmitter CFO. Offset and quadratic terms are fit per lane, while one time delay is shared by all lanes assigned to a selected satellite. No pooled per-satellite CFO is attempted because its gauge against receiver/path resets is not identified here.
- Assignment occurs at frozen radio-lane level. Each lane's existing 20 ms observations inherit its satellite label; this run does not solve independent 20 ms or 1.333 ms probe assignments. No durable 1.333 ms observation product was used.
- Every retained support piece passes the explicit span, distinct-epoch, occupancy, and maximum-gap gates, but that is continuity of CFO observations, not proof of phase coherence for the whole interval.
- `rate_only` uses a raw/dealiased trajectory-slope proxy. It is not the reset-debiased ramp-rate observable used by the stronger continuity reports.
- The lanes were constructed without TLE input, but they were discovered using the whole capture. The grouped split seeded from per-lane 60/40 prefixes therefore protects model selection only conditional on those frozen lanes.
- Equal lane weighting prevents long lanes from dominating, but overlapping radio hypotheses are not statistically independent. Assignment is a deterministic conflict-aware greedy approximation, not a global mixed-integer optimum. The fixed five-sigma unassigned cost is a transparent gate, not a calibrated likelihood.
- The RF frequency is explicitly supplied because the persisted pilot scan labels its frequency reference `uncalibrated_prior`.
- Observer coordinates are an external Sausalito preset with nominal 50 m horizontal uncertainty; the capture has no GPS/site binding.

## Reproduce

```bash
.venv/bin/python tools/evaluate_duration_constrained_satellite_assignment.py --summary-only --output reports/figures/2026_08_25_duration_constrained_satellite_assignment/capture-input-summary.json
.venv/bin/python tools/evaluate_frozen_lane_satellite_models.py --tle /home/mouse9911/.codex/visualizations/2026/08/22/01a02af8-cec4-7703-a883-75760f132c40/radio1-rx1-catalog-search-agent/causal-space-track-ac36512e.tle --output-json reports/figures/2026_08_25_frozen_lane_satellite_models/results.json --output-report reports/2026_08_25_frozen_lane_satellite_models.md --duration-audit reports/figures/2026_08_25_duration_constrained_satellite_assignment/capture-input-summary.json
```

Full machine-readable assignments and fitted parameters: `reports/figures/2026_08_25_frozen_lane_satellite_models/results.json`.
