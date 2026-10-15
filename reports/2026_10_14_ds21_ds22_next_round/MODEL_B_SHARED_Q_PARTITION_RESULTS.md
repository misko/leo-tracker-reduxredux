# Repaired shared B ranking: high-band signal/clutter and calibration modes

The repaired full-origin states beat the retained old low-origin incumbents mainly through **high-band likelihood and modelled signal support**, in both B081 and B115. On B115 the selected state actually loses low-band NLL by 264.725, but wins high by 3094.546. Complete correction functions in the same full target frame differ by tens of kilohertz on high-band rows, while low-band differences are much smaller. This supports a coupled calibration/association/selection hypothesis; neither raw group coefficients nor posterior confidence verify hardware offsets, satellite identities or the configured reference.

This audit adds exactly **four objective evaluations, zero fits**, no reference or original held/locked reads. Roles are the sealed shared-model training winner and the original accepted shared-model training incumbent. They are not chosen by geographic error. All original and newly repaired scientific outcomes remain unchanged.

| Selected minus old incumbent | B081 | B115 |
|---|---:|---:|
| Training J | −2603.695385 | −2655.718849 |
| NLL | −2495.122234 | −2829.821127 |
| Total prior | −108.573151 | **+174.102279** |
| Low-band NLL | −83.485182 | **+264.724902** |
| High-band NLL | **−2411.637052** | **−3094.546029** |
| Exact conditional log-normalizer contribution, all rows | −19.978203 | +31.926370 |
| Unnormalized mixture NLL contribution, all rows | −2475.144031 | −2861.747497 |

Negative favors the selected state. The conditional normalizer contribution is small relative to the full gap and opposes the selected state on B115. Prior costs also oppose it there. This comparison does not isolate one calibration term: geography, complete clock/timing, group correction and q all differ.

| Case / RX-band | Windows | Selected minus incumbent NLL | Signal mass selected / incumbent | Clutter mass selected / incumbent |
|---|---:|---:|---:|---:|
| B081 RX0 low | 883 | −173.481292 | 565.749 / 526.038 | 317.251 / 356.962 |
| B081 RX1 low | 334 | +89.996109 | 245.479 / 253.795 | 88.521 / 80.205 |
| B081 RX0 high | 637 | **−2037.310092** | **500.684 / 88.423** | 136.316 / 548.577 |
| B081 RX1 high | 200 | −374.326960 | 150.913 / 70.939 | 49.087 / 129.061 |
| B115 RX0 low | 1072 | +207.611291 | 853.878 / 875.512 | 218.122 / 196.488 |
| B115 RX1 low | 621 | +57.113611 | 474.631 / 477.472 | 146.369 / 143.528 |
| B115 RX0 high | 766 | **−2382.889922** | **527.391 / 87.364** | 238.609 / 678.636 |
| B115 RX1 high | 323 | −711.656107 | 209.193 / 49.150 | 113.807 / 273.850 |

Of B081's high windows, 536 have signal MAP at the selected state and clutter MAP at the incumbent; those rows contribute −2371.423738 NLL. The corresponding B115 group contains 658 windows and contributes −3133.317323. These MAP-attributed sums are descriptive, not causal allocation or verified emitter evidence. High-band selected/incumbent signal totals are 651.596/159.363 and 736.584/136.515. No window is removed or downweighted.

Channel gaps selected minus incumbent are:

| Case | CH1 | CH2 | CH3 | CH4 | CH5 | CH6 | CH7 | CH8 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| B081 | +6.063 | −23.516 | −237.820 | +171.789 | −381.709 | −938.454 | −817.068 | −274.406 |
| B115 | −143.209 | −151.429 | +162.471 | +396.892 | −735.437 | −1011.805 | −910.612 | −436.693 |

Every one of B081's 12 retained 20-second blocks favors the selected state. On B115, 9 of 12 favor it; blocks 3/5/14 oppose it by 99.444/126.690/233.172 NLL. Blocks 10/11 favor it by 331.264/229.989. Thus the current ranking is broad across high channels and time, not one isolated row. This does not prove independent observations or identify the signal source.

## Physical correction comparison in one frame

All rows use the same original full frame and model. The complete correction is original affine/RF design plus fixed baseline, original group function and common clock. On high rows the selected-minus-incumbent total means/RMS are:

| Case / RX | High correction mean, Hz | High correction RMS, Hz | Low correction RMS, Hz |
|---|---:|---:|---:|
| B081 RX0 | −17505.478 | 17587.469 | 2103.584 |
| B081 RX1 | +39600.286 | 39602.758 | 564.832 |
| B115 RX0 | −24439.302 | 24440.891 | 446.344 |
| B115 RX1 | +37508.992 | 37510.117 | 432.217 |

These totals are function comparisons, not raw coefficient copying. Component ledgers are retained but remain gauge-dependent. To avoid confusing static RF calibration with the group contribution, compare low/high at the same time and each RX's training-median actual RF: contrast = group offset + fitted c × RF difference in GHz. Common time/clock and receiver intercept cancel at matched time.

| Case / RX | Median RF difference, GHz | Selected matched-time total contrast, Hz | Incumbent matched-time total contrast, Hz |
|---|---:|---:|---:|
| B081 RX0 | 1.000 | −19590.827 | −595.007 |
| B081 RX1 | .750 | +39664.348 | +135.023 |
| B115 RX0 | .750 | −24121.222 | +17.584 |
| B115 RX1 | 1.000 | +37272.357 | −533.845 |

Selected fitted c is −144.332/−584.074 Hz/GHz, versus incumbent −187.328/−688.709. The RF term is therefore hundreds of hertz here and does not cancel the tens-of-kilohertz contrast. Nevertheless different fitted geography, timing and assignments can induce different calibration functions. These values are not an independent LNB/oscillator measurement. The saved input provenance itself labels RF mapping as hypothesis-dependent. A tighter group prior chosen to prefer the closer point would be reference tuning and is not justified.

## Prior art and next discriminator

The [older B115 revisit audit](DS22_B115_REVISIT_RESULTS.md) found coherent fitted support and no reversal even under favorable common passing-peak choices; it did not verify an emitter. [Empirical clutter CV](MODEL_B_EMPIRICAL_CLUTTER_CV_RESULTS.md) and [uniform-model restarts](MODEL_B_UNIFORM_BASIN_RESULTS.md) separated background-density effects from initialization and did not provide an independent predictive reason to promote that density. The [full-data control](MODEL_B_BACKGROUND_FULL_RESULTS.md) did not improve selected locations. The [current detectability control](MODEL_B_BAND_Q_RESULTS.md) and [numerical repair](MODEL_B_SHARED_Q_REPAIR_RESULTS.md) also do not fix the geographic ranking. Generic temporal-persistence assumptions or another solver repeat would duplicate rejected leads.

An actually different question is **acquisition/selection conditioning**, including unsuccessful assessments and competition among recorded alternatives. It requires an exposure inventory first, not treating missing selected windows as physical non-detections. Public TrackingInput retains candidate pass/fail flags but research_fast_scan_tracking.py explicitly drops fast-score-skipped windows and incomplete fractional candidates. A zero-candidate retained probe can therefore reflect incomplete assessment, not a clean physical absence. The existing input provenance records B081 3394 fast skips among 6763 original windows, and B115 3229 among 6752. Those are full-recording metadata counts, not original-training-only event counts or usable empty exposures. No count likelihood is fitted here.

A defensible next protocol must use bound public assessment products to distinguish valid fully assessed, fast-skipped, incomplete and invalid windows; retain the original training-only counter/block partition; and avoid counting correlated alternative peaks as independent emitters. The current frozen TrackingInput alone is insufficient to establish that complete exposure. Public sealed GLRT results and product bindings may support a narrow metadata export, with no raw RF collection or private storage-path construction. Only after that inventory should a normalized, matched predictive test of detection/selection conditioning be specified. No ad-hoc margin-to-probability rule, reference-chosen prior, or new model fit is authorized by this report.

## Reproducibility

Source `529647b9a`; [protocol](MODEL_B_SHARED_Q_PARTITION_PROTOCOL.md), three owned tests pass in 1.52 seconds / Ruff pass. Same genuine GroupB + SmoothVisibilityModel, both original group offsets free, same full bank/frame/candidates/priors, original complete endpoints and own 25 km domains, fitted c only. J/NLL/KKT replay uses the same two objectives per case. Generic posterior comparison is reused with a singleton auxiliary axis for folded catalogue probabilities; no native detector branch or native likelihood is invented. All partition families conserve every original training window and NLL gap. No extra explicit predictor calls, localization fits, original held/locked measurements or position/reference reads.

Bulk namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-shared-q-partition-v1`. Two single-thread slices complete .846172 / 16.505762 seconds including preparation, within 120-second completion / 135-second TERM / 140-second KILL. Protocol `sha256:315af7f83400c725eec5acd24500ce729b7cec7621b0accaa3e1f6f23be67c96`; B081 terminal `sha256:f665aa5939ba642214d1e1b4d9b89224c4c4948f0e1d37f266d812b6b94ce1c8`; B115 terminal `sha256:bb8c18708a67dff11ac5d1d5d6801d5484b02f1dba58a947e38a0c971eaf506a`. Existing reports, plots, original science and frozen receipts remain unchanged.
