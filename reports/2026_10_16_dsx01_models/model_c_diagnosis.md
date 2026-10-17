# DSX-C saved-result diagnosis: shallow alternate basins, no recovery

This is a read-only analysis of the five saved `results/S0*-full-fitted-c-{original,continuation,C}.json` comparisons and the existing S02 production evidence. No model, objective, candidate bank, calibration prior or result was changed. No objective evaluation, predictor call, refit, new recording or production action was run for this diagnosis. These findings concern the full-data fitted-c development arm; they do not substitute for the temporal or c=0 comparisons being run separately.

All five C selections come from the original basin. Their association counts total 11,223/20,084, compared with 11,222/20,084 for the original. The net increase is one point on S02, with two newly associated points and one lost point. It is not evidence of recovered satellite identities, successful excluded prediction or improved geographic accuracy. S02's intersection RMS increases from 169.4649 to 169.5372 Hz, while its assigned-set RMS increases from 169.5947 to 169.9178 Hz. The unchanged maximum-satellite-posterior versus clutter rule defines those assignments.

## Complete budget and acceptance inventory

Each C run reserves six equal quotas of 30 objective evaluations, including the common refitter's seed evaluations, with a 180-evaluation/120-second total cap. Unused quota is not reallocated. The comparator gives one continuation the same 180-evaluation cap; an early solver exit is allowed in both. Evaluation/scoring calls outside inference are separately recorded by the parent harness.

| Scan | C calls | C seconds | Selected basin / strict? | C minus original J | C minus continuation J | Continuation calls / strict? |
|---|---:|---:|---|---:|---:|---|
| S01 | 163 | 7.619 | original / yes | ~0 | 0 | 13 / yes |
| S02 | 180 | 5.784 | original / no | -0.139400 | +4.492467 | 180 / no |
| S03 | 163 | 4.448 | original / yes | 0 | 0 | 13 / yes |
| S04 | 177 | 5.090 | original / no | +7.22e-8 | 0 | 27 / no |
| S05 | 180 | 4.851 | original / yes | +6.31e-8 | 0 | 30 / yes |

C uses 863 objective evaluations overall: 113 in its five original branches and 750 in the 25 alternative branches. The five continuations use 263 evaluations overall. No alternate branch becomes strict. The selected C KKT residuals are respectively 9.60236e-5, 86.1672, 8.11814e-4, .00311328 and .000938144. S04's solver reports successful termination but its endpoint fails the independent .001 KKT gate; no solver-status acceptance is substituted. The tiny S04/S05 objective increases relative to the exact saved original are retained, not rounded into improvements. The common refitter reconstructs its numerical chart and returns its best evaluated iterate; it does not retain the immutable raw original as an independently eligible incumbent outside that chart. This is distinct from altering the published original receipt.

## Every alternate branch is unresolved and worse at its returned point

The following are returned training-objective gaps relative to that scan's selected original branch. Every cell represents 30 actual objective evaluations, `accepted=false`, and termination reason `evaluation-or-wall-budget`.

| Scan | Position NE | Position SW | Calibration + | Calibration - | Relative timing |
|---|---:|---:|---:|---:|---:|
| S01 | +3642.039 | +2586.953 | +3924.787 | +3845.486 | +3544.999 |
| S02 | +4611.894 | +4888.856 | +5032.196 | +4763.627 | +4660.831 |
| S03 | +10309.924 | +9666.129 | +11919.875 | +11873.206 | +4764.572 |
| S04 | +5138.644 | +7239.546 | +8408.947 | +8276.859 | +7146.462 |
| S05 | +7281.204 | +6441.746 | +8583.954 | +8401.988 | +4116.311 |

Alternate branch KKT residuals range from 167.708 to 14550.817, versus the .001 strict gate. Each finishes in roughly .7–1.5 seconds, so these are evaluation-cap failures, not evidence that the 120-second wall allowance was consumed. The seed and solver's initial repeated evaluation are included in each 30-call quota. The reports do not record each alternate seed's initial objective or intermediate trajectory, so the amount of within-branch descent and its eventual attraction basin cannot be reconstructed from these summaries. A bad returned alternate point does not establish the absence of a better stationary point in that basin.

The starts perturb a highly coupled saved state substantially. Spatial starts preserve the original regional prior through a convex construction, but preserve the old calibration and satellite timing rather than preprofiling them at the new geography. Their actual movements are not a uniform 15 km: 15 km is the construction's anchor radius, and contraction of the old location also contributes. Calibration starts shift both existing RX intercepts by ±ALIAS/8 (about 28.409 kHz) and reset the existing common-clock coefficients to zero; q and the fixed band contrast remain unchanged. The relative-timing start shrinks existing absolute satellite shifts toward a small fixed cosine pattern in the unchanged candidate ordering. It does not introduce a new timing parameter.

| Scan | NE / SW movement km | Clock reset coefficient RMS Hz | Absolute satellite timing change RMS s |
|---|---|---:|---:|
| S01 | 29.577 / 2.862 | 389.339 | 2.259 |
| S02 | 16.520 / 14.935 | 453.847 | 1.968 |
| S03 | 21.952 / 8.048 | 234.097 | 1.416 |
| S04 | 7.811 / 23.206 | 567.484 | 1.902 |
| S05 | 22.525 / 7.475 | 459.132 | 1.601 |

The existing timing and narrow frequency likelihood make these meaningful perturbations, rather than small polishing steps. That explains why allocating only 30 evaluations to each is a plausible limitation. It is not a causal proof that more evaluations would recover a useful alternative. The present experiment spends most evaluations on unfinished starts and cannot distinguish an unhelpful proposal from an insufficiently optimized one.

S02 gives a direct allocation counterexample within the original basin: its 30-call C branch reaches J42886.894438 with KKT86.1672, whereas the 180-call continuation reaches J42882.401971 with KKT23.0122. More calls found additional descent there, although neither endpoint is accepted and no successful localization follows. This supports preserving a deeper continuation control in any later allocation experiment. S01/S03/S05 already terminate successfully in their original branches; their unused allocations do not prove alternative branches could never help.

## Why the S02 original audit differs without invalidating production evidence

The saved S02 production endpoint is `shared-all-A-5` in `reports/upper-210123-three-segments-20261016/saved-evidence.json`. Its own options specify a 25 km local disk centered at `[63.02492368625821, -47.2788321924767]`. Its vector begins `[45.84207907489035, -65.43784788887388]`, a distance of 25.000000000008 km from that center: the local disk is active. The saved production audit and exact public replay accept it with KKT .000914500764 and J42887.033838119.

`common.endpoint_status` constructs `_Problem(model, vector, rf_arm=...)` with no local center/radius, retaining only the broad regional prior and original timing/parameter bounds. Removing an active local constraint removes its normal from the projected KKT calculation and admits descent directions that were infeasible in the production problem. On that broader problem, the same raw S02 endpoint is feasible but has KKT9.986869685 and is not stationary. Its J and NLL remain unchanged. The saved production receipt is therefore not refuted: the two audits address different feasible domains. Neither the broad-domain rejection nor the constrained acceptance is a claim about geographic truth.

This also means these research continuations are broader-domain experiments, not a repeat of the exact original production optimization. C's original branch and the equal-budget continuation share this same broader domain, so their allocation comparison remains coherent. Comparisons with the original must disclose this domain expansion.

## Consequence for the next design

Do not promote C or describe this as successful multi-basin recovery. Retain the negative result, all 25 failed alternate endpoints and the two selected nonstationary endpoints. A future separately frozen allocation control could use fewer starts or a prespecified staged budget, with one full-depth original continuation retained, rather than six equal shallow runs. It should keep the same total evaluation cap, score/model/candidate bank and training-only proposal/selection rules, and explicitly retain a requalified immutable incumbent in the matching domain. Any such experiment needs its own approval and cannot be inferred to work from this audit. No new fits or source changes were performed here.
