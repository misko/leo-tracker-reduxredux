# C075 same87-bank halves: full still loses to the high band

All eight prescribed half-view fits passed strict independent stationarity. Each half selected original source2 over the best accepted coarse source. The complete87-satellite native models, calibration frames, priors and source receiver lifts were retained. Only likelihood rows changed. The resulting comparison is:

| Native model | CH1–8 km | CH1–4 km | CH5–8 km |
|---|---:|---:|---:|
| Original no-clock | 78.429728 | 79.778706 | 51.081079 |
| Common receiver clock | 80.766346 | 81.157443 | 51.431006 |

Distances use the configured, unconfirmed DS22 station. Full now beats low slightly but remains27.349km/no-clock and29.335km/clock worse than high. This is a new same-bank comparison, not a replacement of the original cohort's different-bank halves. None is near the accuracy target.

Both selected high endpoints lie exactly on their original25km disks. Their low counterparts are interior at8.147km/no-clock and7.944km/clock. The high-band position difference is therefore entangled with a local search boundary; a larger disk requires a training-only outward-derivative trigger before any new optimization. The present result does not justify a reference-centered domain, selecting the high state as a full optimum, or simply averaging the two positions.

| Model/view | Selected objective | Selected NLL | KKT | Coarse-start accepted objective |
|---|---:|---:|---:|---:|
| No-clock low | 22976.059544 | 22718.928421 | 0.000035100 | 24085.617429 |
| No-clock high | 16105.206406 | 15887.927133 | 0.000134605 | 17774.507627 |
| Clock low | 22893.601477 | 22550.322547 | 0.000628820 | 23450.718830 |
| Clock high | 16136.696528 | 15881.154071 | 0.000172973 | 16935.792143 |

Training objectives are selected only within a view/model; different-row counts are not ranked against one another. The full result retains its22-start search; each half uses only two complete full-derived accepted states (original and coarse). These are shared-discovery conditional controls, not independent band-only pipelines or an equal-total-search-budget experiment.

The16-objective zero-fit qualification verified exact legacy raw-native full-mask replay, all physical/nuisance gradients, posteriors, likelihood partition and prior-once gradient accounting. There are no propensity parameters and no conditional normalization change. Fourteen qualification/component tests and the evaluator's pre-reference seal test passed. All eight calls used60seconds/600iterations, with independent final audits; no failed calls were retried. The root four-worker wave completed in151.04seconds and all eight outcomes sealed before reporting.

Source `bec312aca`; post-seal evaluator `bfc2b59f6`. Numerical namespace `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-c075-union-views-v1`; comparison `ds22-c075-union-views-comparison-v1`. All original44 outcomes and20 rejected states are retained. No held or locked observations were used, and no accuracy or cohort promotion is claimed.
