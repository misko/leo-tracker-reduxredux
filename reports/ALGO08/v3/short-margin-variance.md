# Short-verifier margin as conditional measurement variance

The frozen margin rule produced complete fixes on both saved 12 ms packets. It lowered horizontal error by **26 m fixed-zero and 38 m fitted** on physical DS30-0016. North moved by less than 5 m in either calibration arm, and its fixed-zero error remained **289 m above named ALGO08v3**. That exceeds the frozen 250 m allowance by 39 m. The joint gate failed and the study ended with these two cases. [Frozen rule and gate](short-margin-variance-protocol.md) · [Paired receipt](measurements/short-margin-variance.json.gz)

| Saved input and calibration | Named v3 error (km) | Unit → weighted 12 ms error (km) | Unit → weighted RF RMS (Hz) |
| --- | ---: | ---: | ---: |
| Physical DS30-0016, fixed zero | 1.644 | 1.311 → 1.285 | 121.526 → 121.593 |
| Physical DS30-0016, fitted | 1.661 | 1.694 → 1.656 | 120.291 → 120.366 |
| North containing, fixed zero | 0.106 | 0.390 → 0.394 | 69.401 → 69.742 |
| North containing, fitted | 0.141 | 0.121 → 0.121 | 70.860 → 71.235 |

Position errors use the archived reference coordinates after the four publications were sealed. RF RMS rose in all four comparisons even though the physical positions improved. The corresponding fixed-zero and fitted changes on North were **+4.73 / +0.13 m** and **+0.341 / +0.375 Hz**. The two c arms used the same variance rule and original support.

## What the trial changes

The released solver already fits a radio-only `floor + strength / fractional_margin` model from active Graph-polynomial residuals. It chooses that law or the common scale through BIC and uses the selected scales in controlling both curved and predictive likelihoods. The margin-gradient and deployed-margin trials retained this fitted model and studied numeric changes to its inputs or optimization. The earlier 12 ms margin experiment changed only Graph rewards. The held-continuation study obtained no independent forecasts for its unsupported class and stopped before running a weighted fit. [Installed noise law](../../../src/leo/analysis/localization_v3/noise.py) · [Margin arithmetic audit](../single-core-2x/solver-deployed-margin-recovery.md) · [Graph reward](discovery-margin-12ms.md) · [Continuation variance study](continuation-quality.md)

This trial starts at the selected incumbent sigma for each row and multiplies short-row variance by `1 / max(0.5, 1 - 0.025/m)`, using the original 600 Hz upper limit on sigma. The earlier frozen excess-margin fraction gives the relative-information hypothesis. The half-information floor retains every row and bounds the variance ratio to at most two. The 20 ms scheduled anchors keep their original sigmas. The rule uses the original signed short packet's stored exact and rolled control scores with the original acceptance arithmetic. Its weights require neither paired longer measurements nor site references.

The weighted scale enters after unweighted Graph, cold discovery and ordinary support selection. It feeds the original per-observation sigmas and log volume in the signed curved solve and the original predictive scale and Gaussian normalization. The predictive model still uses the original Gamma prior factor `sqrt(2)` and curve-bias covariance. The same scales are used to reconstruct the elected endpoint likelihood and complete map. The accepted signed refit keeps the original group powers, phase prior and support. [Model binding](short_margin_variance.py) · [Curved position likelihood](../../../src/leo/analysis/localization_v3/history_position.py) · [Predictive likelihood](../../../src/leo/analysis/localization_v3/predictive_linear.py)

| Saved input, per calibration arm | Curved rows changed / total | Predictive rows changed / total | Largest curved / predictive variance ratio | Complete grid points |
| --- | ---: | ---: | ---: | ---: |
| Physical DS30-0016 | 80 / 93 | 21 / 23 | 1.307 / 1.068 | 179 |
| North containing | 251 / 287 | 52 / 60 | 1.632 / 1.028 | 137 |

The Graph and frozen candidate-support digests match within each pair. Both weighted arms reached the original signed acceptance gate and preserved the original number and roles of all owners, **116 per arm on physical and 347 on North**. No NORAD changed. All endpoint objective replay errors were zero. Both unit runs reproduced the archived scientific terminal, grid, path and owner rows. Every run published eight standard PNGs, verified as files and decoded RGBA arrays. The unit figures match their archived hashes. Weighted position sidecars bind the corresponding new position figure.

## Saved process clocks

| Saved input | Unit → weighted solve CPU (s) | Unit → weighted process CPU (s) | Unit → weighted process elapsed (s) |
| --- | ---: | ---: | ---: |
| Physical DS30-0016 | 2.729 → 2.712 | 5.609 → 5.592 | 5.611 → 5.596 |
| North containing | 3.650 → 3.585 | 6.903 → 6.845 | 6.905 → 6.848 |

These single pairs charge both the scientific solve and the full saved publication through process exit. The early bootstrap attempt imported scientific modules before the release's lazy package binding. The retained fresh workers initialize that binding first. All four retained launches used the single low-priority Gauss slot, original signed inventory and read-only saved packets. No waveform processing ran. [Runner](short_margin_variance_trial.py)

## Reproduce

Use a fresh private tmpfs output root and an account permitted to read the sealed regional library. The parent scorer uses the repository's read-only storage API. Each fresh worker uses the installed numerical solver.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$PWD/src:$release/src:$release" \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs reports/ALGO08/v3/short_margin_variance_trial.py run "$output"
```

Thirty-eight component and adjacent tests passed. [Tests for bounded row variance and Gaussian normalization](../../../tests/pipeline_eval/test_short_margin_variance.py)
