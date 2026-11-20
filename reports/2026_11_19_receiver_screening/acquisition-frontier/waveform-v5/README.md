# Original v5 compared with compact on generated waveforms

The archived no-repair v5 numerical worker and installed compact phase release received the same stock GLRT native factors from generated dual CI16 waveforms. Both used the original schedule, the same 35 causal TLE snapshots per site, exact TrackConfig, explicit screening center and the same 25 km offer. Each numerical call reported separately optimized `c = 0` and fitted-`c` arms. These measurements start at native factors. The parent studies record IQ generation and compiled GLRT separately. [Original plan](PROTOCOL.md) · [Prospective holdout method](HOLDOUT.md) · [First waveform and detector audit](../../track-recovery/waveform-site/README.md)

## Reference and geographic handling

The private regional adapter supplies the true offered tile to the frozen worker after validating the public request with its required roof presentation frame. It uses the established endpoint renderer and the complete original no-repair numerical path. This accepts both generated site locations within the solver's regional coordinate domain. The independent archived DS29-0082 positive control for this adapter was reproduced exactly for both endpoints, conditional RF values, preparation and association counters and all 18 stage names. Each original run here had a 330 s service deadline, one numerical thread, a 3 GiB cgroup ceiling and zero swap. The compact measurements used the installed release under 512 MiB and zero swap. [Roof parity and original input audit](../../receiver-core/v5-regional-reference/README.md) · [Retrospective execution lock](retrospective/source-lock.json) · [Prospective original method lock](holdout-method-lock-v2.json)

## First site, retrospective comparison

Both receivers completed both offers. On the containing offer, original v5's errors differed from compact's by 16 m with zero calibration and 13 m with fitted calibration. Both ordinary methods published false fixes on the nearest face of the near-omitted offer in both arms. The existing independently replayed compact 20 m interior policy withheld both omitted fixes. [Original terminal prediction seal](retrospective/prediction-lock.json) · [Zero-calibration chart](retrospective/charts/c0/waveform-v5-retrospective.png) · [Fitted-calibration chart](retrospective/charts/fitted_c/waveform-v5-retrospective.png) · [Independent interior result](../../track-recovery/waveform-site/interior-profile/scores.json)

| Offer and receiver | Position error, zero / fitted | Conditional RF RMS, zero / fitted | Factor-to-position wall | CPU |
| --- | ---: | ---: | ---: | ---: |
| Containing, original v5 | 1.033 / 0.764 km | 15.538 / 15.307 Hz | 73.54 s | 69.77 s |
| Containing, installed compact | 1.017 / 0.751 km | 15.536 / 15.306 Hz | 20.89 s | 20.46 s |
| Near omitted, original v5 | 1.587 / 1.538 km | 15.631 / 15.451 Hz | 139.55 s | 134.87 s |
| Near omitted, installed compact | 1.580 / 1.534 km | 15.631 / 15.451 Hz | 20.82 s | 20.58 s |

Original v5 prepared 724 observations, retained 24 tracks and associated 517 observations in every arm. The two services charged peaks of 1.098 and 1.102 GiB. For the original containing fit, fitting `c` reduced error by 0.269 km, conditional RF RMS by 0.231 Hz and the conditional frequency objective by 26.558. The original omitted fit's objective fell by 23.897 and both arms still published false fixes. Compact's matched conditional objectives differed from the original by less than 0.003 in all four fits. [Fit, frequency and resource ledger](retrospective/scores.csv) · [Paired calibration changes](retrospective/calibration.csv)

## Independent holdout

The detector seal fixed all three opaque offers before the original results. The first local preflight rejected the clock match because the scheduled anchor is at the midpoint of the native bracket, 5 ms after its leading edge. It started no service. Before labels were available, the corrected check authenticated the recorded midpoint and retained the leading edge as the strictly causal archive cutoff. The methods, offers, waveform samples and numerical settings stayed fixed. [Initial method lock](holdout-method-lock.json) · [Clock match correction](holdout-method-lock-v2.json) · [Parent detector seal](../waveform-holdout/detector-lock.json)

All three original services completed before the 330 s deadline. The peer scorer released the second site's location after sealing the six compact and the three original outcomes. On the containing offer, the matched methods were within 8 m of each other in position error in either calibration arm. Both ordinary methods issued false fixes on both omitted offers. The compact 20 m policy reproduced the phase-release numerical fits, published both containing arms, and withheld all four omitted arms. [Holdout original prediction seal](holdout/prediction-lock.json) · [Independent truth release](../waveform-holdout/score-lock.json) · [Zero-calibration chart](holdout/charts/c0/waveform-v5-holdout.png) · [Fitted-calibration chart](holdout/charts/fitted_c/waveform-v5-holdout.png)

| Offer and receiver | Position error, zero / fitted | Conditional RF RMS, zero / fitted | Factor-to-position wall | CPU |
| --- | ---: | ---: | ---: | ---: |
| Containing, original v5 | 0.642 / 1.086 km | 17.213 / 17.199 Hz | 77.44 s | 73.07 s |
| Containing, installed compact | 0.650 / 1.093 km | 17.213 / 17.199 Hz | 20.94 s | 20.14 s |
| Near omitted, original v5 | 1.718 / 1.658 km | 17.319 / 17.348 Hz | 153.97 s | 146.55 s |
| Near omitted, installed compact | 1.728 / 1.668 km | 17.317 / 17.345 Hz | 20.15 s | 19.52 s |
| Far omitted, original v5 | 44.255 / 44.255 km | 40.794 / 40.329 Hz | 133.38 s | 129.11 s |
| Far omitted, installed compact | 44.255 / 44.255 km | 44.078 / 43.773 Hz | 21.85 s | 21.47 s |

Original v5 prepared 594 observations and 26 tracks on every offer. Both calibrations associated 412 observations for the containing and near-omitted offers and 269 for the far-omitted offer. Its cgroup peaks ranged from 1.021 to 1.029 GiB, with zero swap. On the containing offer, fitted `c` lowered the original conditional RF RMS by 0.014 Hz and raised geographic error by 0.443 km. On the far-omitted offer, the original conditional objective fell by 59.810 and both arms returned the same false fix. [Fit and resource ledger](holdout/scores.csv) · [Paired calibration changes](holdout/calibration.csv)

Across the two sites, the original and ordinary compact receivers each published all four containing calibration-arm outcomes and all six omitted calibration-arm outcomes. Those ten outcomes come from five offers at two generated sites. The ordinary compact factor-to-position calls took 20.15–21.85 s wall across those five offers, and the original numerical calls took 73.54–153.97 s. The distinct service caps and the separate IQ stages delimit this latency comparison. [First-site detector receipt](../../track-recovery/waveform-site/detector-lock.json) · [Holdout detector receipt](../waveform-holdout/detector-lock.json)

Re-score the terminal seals and render the canonical charts from the repository root.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.waveform_v5_results retrospective
.venv/bin/python -m tools.pipeline_eval.qualification.waveform_v5_results holdout
.venv/bin/pytest -q tests/pipeline_eval/test_waveform_v5.py tests/pipeline_eval/test_v5_regional_reference.py
```
