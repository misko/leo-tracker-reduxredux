# Transferring a reduced waveform frequency-rate correction

**Donor-calibrated shrinkage recovers a small pooled prediction gain, but does not resolve DS8 degradation.** Keep this as an experimental candidate, not a replacement for the constant-frequency estimator or a demonstrated subkm improvement.

The [unrestricted rate experiment](../2026_09_29_waveform_chirp/README.md) worsened pooled mean prediction by 0.002015 NMSE. This follow-up chooses how much of that correction to apply using only earlier frames from the other datasets. It improves pooled mean prediction by **0.000864 NMSE**, with 97/160 targets improving and 63 worsening. All three DS8 visits still worsen on average. This is mixed transfer evidence, not a generally reliable correction.

| Target dataset | Donor-selected correction strength | Constant mean NMSE | Selected mean NMSE | Mean paired gain | Targets improved |
|---|---:|---:|---:|---:|---:|
| DS7 | 0.50 | 0.785334 | 0.782136 | +0.003198 | 42/60 |
| DS8 | 0.50 | 0.835734 | 0.838196 | −0.002463 | 28/60 |
| DS9 | 0.25 | 0.753813 | 0.751458 | +0.002355 | 27/40 |

Lower NMSE is better; positive paired gain favors the correction. Equal-dataset mean gain is +0.001030, while the pooled mean above weights the 160 receiver-frame targets equally. Neither is an absolute frequency-error measurement.

| Visit | Mean paired NMSE gain |
|---|---:|
| DS7 S02 | +0.005067 |
| DS7 S31 | +0.002389 |
| DS7 S32 | +0.002136 |
| DS8 S13 | −0.003020 |
| DS8 S28 | −0.001885 |
| DS8 S29 | −0.002483 |
| DS9 middle | +0.003105 |
| DS9 first | +0.001605 |

## What was selected and what was held out

The [protocol](PROTOCOL.md) fixed strengths 0, 0.25, 0.5, 0.75 and 1 before this run. Zero reproduces constant frequency; one reproduces the unrestricted intercept/rate fit. Both intercept displacement and rate are multiplied by the selected strength. No target frequency estimate is used to calibrate its forecast. Each target's early symbols calibrate complex gains only, with later disjoint symbols supplying the scored residual.

Calibration uses blocks starting at relative frames 0, 10 and 20 in each of eight existing visits, both receivers: 48 blocks and 96 forecast targets. Every block fits its first eight frames and forecasts the next two, with the same waveform estimator as the parent experiment.

For each target dataset, completely exclude its calibration data. Select strength using the other two datasets with equal dataset weight, equal visit weight within each dataset, and equal target weight within visit. Exact ties choose smaller strength. Freeze the selection and evaluate the target dataset's blocks starting at frames 30, 40, 50, 60 and 70. The three selections are separate transfer fits, not one globally fitted deployable rule.

| Target excluded | Donor calibration NMSE at 0 | At 0.25 | At 0.50 | At 0.75 | At 1 |
|---|---:|---:|---:|---:|---:|
| DS7 | 0.779424 | 0.777861 | **0.777327** | 0.777827 | 0.779359 |
| DS8 | 0.741795 | 0.740515 | **0.740367** | 0.741350 | 0.743453 |
| DS9 | 0.794234 | **0.793508** | 0.793782 | 0.795055 | 0.797320 |

All 128 calibration/evaluation fits qualified; no fallbacks or exclusions. All 160 evaluation endpoints at strengths zero and one reproduce the preceding experiment within 1e-10 NMSE. Two tests pass: target-dataset and future-data mutation isolation; equal-dataset weighting and conservative exact-tie handling. Parent source and cache hashes verify. The bounded run completed successfully within 120 seconds.

## Interpretation and decision

The improvement after reducing correction strength is compatible with noisy rate estimation over short intervals. It does not isolate physical Doppler, receiver drift, acquisition error or a transmitter effect. DS8's consistent adverse mean results across its three visits remain a concrete obstacle to promotion. Sample rate alone does not explain the sign: DS9 also includes 10-MS/s excerpts and improves here; these convenience visits do not provide a controlled rate comparison.

Do not choose a DS8-specific zero correction after seeing its evaluation outcome and present that as validation. A useful next discriminating step would measure training-only rate stability across separate carrier or time subsets and test whether that predicts the failure, with both carrier geometry and signal support explicitly accounted for. Further tuning on this corpus cannot establish blind generalization.

These data and the parent outcomes have already been inspected. This follow-up separates calibration and evaluation computationally but is explicitly posthoc research, with dependent receivers and frames. Acquisition is inherited from the recorded waveform. No geographic fit, independent Doppler truth, absolute timing or satellite identity is evaluated. Reliable short-window subkm accuracy remains unverified.

No new RF, archive export, production edit or remote publication occurred. The report and evidence are local.

## Reproduce

```sh
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_rate_transfer -p 'test_*.py'
OPENBLAS_NUM_THREADS=1 timeout 120 uv run --no-project --with numpy --with scipy python reports/2026_09_29_rate_transfer/run.py
```

The numerical writer uses exclusive creation: replay in a fresh output context. [results.json](results.json) contains every calibration/evaluation target at every fixed strength, fit diagnostics, selections and dependency hashes. `evidence.sha256` seals the local report, protocol, code, tests and results.
