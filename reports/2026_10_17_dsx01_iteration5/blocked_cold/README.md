# Original production: alternating20s cold interpolation

The original TRAIN-only production pipeline associates 795/1909 held original winners (41.64%) and 1088/2073 training winners (52.48%). Requested held-window support is 66/80. This is one predeclared S03 parity0 interpolation pilot, not a result at new receiver positions.

Membership is determined by integer sample intervals in alternating20-second blocks from the original session-counter origin. Parity0 trains; parity1 is held. Every probe crossing a block boundary is excluded completely. No candidate CFO, score, gate, epoch, candidate identity or location enters membership. Global source-group IDs preserve the original capture authority. Three tests plus actual perturbation of every excluded CFO/score/gate yield identical derived training bytes and preparation evidence.

Raw groups: 3974 train, 3516 held, 10 boundary. The fixed source cohort contains 2073 train, 1909 held, 6 boundary winners, totaling3988. The full frozen challenge693 denominator is 58 train + 80 held + 0 boundary + 555 untested from other sources. The full20084 denominator retains 16096 other-source observations as untested. Boundary observations are reported separately and receive no training or held credit. 

Exactly one public `leo.cli.shared_fast_position.run(...maximum_seconds=480,tle_root=...)` completed in 147.784 seconds. The unchanged policy is `generic-cold24-shape3-fresh-six-ab-v1`; source `A-5` passes strict KKT 0.000167863415. All discovery, shape, bootstrap, A/B and shared stages are newly computed from the derived training source. No saved full-recording bank, position or calibration is an initializer. No v6/short-segment replacement, recording, production publication, retry or additional model fit occurred.

Causal archive: space-track, `sha256:d07c22e355ffbe4699bc4be9de9f330c0eef3e44b74f6d200b1cb14502dffbe7`, collected 1792181063706395625 UTC ns, strictly before origin minus505seconds. The TRAIN-only regional bank has 845 candidates and production selects 45 IDs. Only these IDs enter prediction. Selection remains training-derived even though timing metadata spans the full recording.

Training spans both recording ends. Its native learned residual-clock nodes cover0…300s, so held gaps need no clock extrapolation or added knots. Every clock coefficient is learned using training measurements only. The public frozen sequential correction retains all learned affine terms, RF dependence and band offsets. Training correction closure is 3.64e-12 Hz and training frequency NLL replays exactly. Predictions are persisted before held CFO or descriptive full-fit labels enter scoring. The original125Hz maximum-satellite-posterior>clutter classifier is unchanged.

| Cohort | Associated | Assigned RMS Hz | Frequency NLL | Original full-fit new/lost |
|---|---:|---:|---:|---:|
| Train | 1088/2073 | 158.56 | 24228.43 | +227/−706 |
| Held | 795/1909 | 179.88 | 23241.17 | +132/−857 |
| Boundary | 2/6 | 78.92 | 72.66 | +1/−3 |

| Fixed requested window | Train associated | Held associated | Boundary associated |
|---|---:|---:|---:|
| DSX01-007 | 28/28 | 20/26 | 0/0 |
| DSX01-008 | 20/22 | 20/28 | 0/0 |
| DSX01-009 | 8/8 | 26/26 | 0/0 |

Original full-fit descriptive winner IDs are absent from the TRAIN-selected bank for 175/1520 originally associated held rows. Among 857 lost original held assignments, 151 have an absent original winner. These are model-label coverage diagnostics, not verified identity recall, and they never influence training. Selected candidates have positive model visibility on 1909/1909 held rows. Visibility alone cannot establish correct-emitter bank coverage.

The contiguous half-forecast baseline is separate:1571/2006train and165/1982held with25train-selected IDs and constant boundary-clock extrapolation. Alternating blocks change the selected bank, temporal support and held cohort. A difference between these pilots cannot be attributed exclusively to clock behavior, a single prior, or candidate discovery.

The fitted position is (37.851722,-122.386132), 8.752 km from the matching configured reference. Its survey uncertainty is unknown. The reference is measurement-only, after prediction freeze; better frequency fit alone is not localization accuracy.

Cost: 11376 exact A/B/shared calls across 26 fits, plus 6 prescreens. Discovery: 24 points/72 receipts, 18865 reported solver evaluations, 30.500 summed fit seconds; shape attempts 3, bootstrap stages 18. These cost scopes remain separate; terminal `cost_exact` is not a whole-algorithm objective counter. Every counted fit respects its public source2000/20s or shared5000/65s allowance and the entire original run stays below480s. No hidden held fit occurs in evaluation or replay.

The original production discovery fits c throughout. No whole-pipeline c=0 comparison or fitted-c localization advantage is claimed. Any later matched downstream c=0 sensitivity is conditional. No train-profile/age-model experiment is launched automatically.

![Fixed interpolation cohorts](blocked-coverage.png)

Artifacts include immutable derived input/provenance, original stage receipts, prediction/evaluation arrays, a strict no-fit replay, and source hashes. `training_context.py::load_training_context()` rebuilds only the derived training observations, their selected causal bank and strict endpoint; `predict_original(context,vector,nuisance,metadata)` provides a metadata-only frozen original prediction port. That port exactly reproduces all3988 saved predictions and is invariant to every held CFO perturbation without mutating seeds. Changed-model residual corrections require an explicit adapter, not silent omission. Entrypoints are `run_blocked.py --run`, `score_blocked.py`, `score_blocked.py --verify`, and `report_blocked.py`; attempted namespaces cannot be silently reused.
