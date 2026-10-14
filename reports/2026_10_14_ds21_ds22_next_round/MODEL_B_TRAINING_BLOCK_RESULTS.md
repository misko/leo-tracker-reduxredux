# B059 persistent CH3 loss and block-sensitive overall ranking

The source-frozen arithmetic audit completed in1.016s: **0 observation preparations,0 predictions,0 objective/likelihood evaluations,0 fits**. It used only the already sealed updated two-state training-score arrays. Original held and locked observations remain untouched. No position, nuisance, calibration, detector branch or likelihood weight changed.

All2522 windows fall in12 observed20-second support-center bins relative to the prepared origin. Empty bins are not inserted, and these bin labels are not claimed to reproduce probe-start holdout labels exactly. Full additive closure recovers donor-minus-incumbent NLL310.947606 and objective117.247680 with prior gap−193.699925.

| Observed bin, seconds | Windows | Donor NLL gap |
|---|---:|---:|
| 0–20 | 223 | +115.490931 |
| 20–40 | 163 | −67.547181 |
| 40–60 | 180 | −27.023557 |
| 60–80 | 184 | +15.063515 |
| 80–100 | 232 | +45.587177 |
| 160–180 | 205 | +58.914935 |
| 180–200 | 217 | +154.198727 |
| 200–220 | 208 | +337.067132 |
| 220–240 | 203 | +141.692397 |
| 240–260 | 224 | +31.005946 |
| 260–280 | 234 | −134.647426 |
| 280–300 | 249 | −358.854991 |

Eight observed bins favor the incumbent in NLL, four favor the donor. The200–220s bin contributes337.067132, larger than the full310.947606 NLL loss. Subtracting only that saved block while keeping both states fixed would give NLL−26.119526 and objective−219.819452 with the same full priors. Bins180–200,200–220 and220–240 individually flip this fixed-state objective comparison. This is **descriptive sensitivity**, not cross-validation, nuisance refitting, an endpoint selector or justification for deleting a block. Keeping full prior penalties after subtracting data also changes their relative influence. No effective independent sample count or physical emitter persistence is inferred.

The channel pattern distinguishes a persistent discrepancy from time-local tradeoffs:

| Channel | Bins with observations | Adverse / favorable bins | Total NLL gap | Min / max bin gap |
|---|---:|---:|---:|---:|
| CH1 | 12 | 4 / 8 | −234.147295 | −104.966 / +11.008 |
| CH2 | 12 | 8 / 4 | +144.651961 | −35.463 / +94.771 |
| CH3 | 12 | **11 / 1** | **+461.756026** | −14.078 / +102.280 |
| CH4 | 12 | 5 / 7 | −90.011401 | −83.188 / +30.590 |
| CH5 | 12 | 3 / 9 | −130.673042 | −90.204 / +71.128 |
| CH6 | 11 | 5 / 6 | +167.520016 | −29.161 / +99.448 |
| CH7 | 12 | 6 / 6 | +27.068071 | −50.394 / +50.956 |
| CH8 | 11 | 4 / 7 | −35.216730 | −89.567 / +74.601 |

RX0 and RX1 each have6 adverse and6 favorable observed bins; their total gaps remain+265.983530/+44.964076. CH3 is adverse in9/12 RX0 bins and7/9 RX1 bins with observations. It is not simply one receiver or one short interval. The earlier RX0-high narrative applied to earlier complete states and is not the current explanation.

## Two falsifiable model controls to prespecify before fitting

**First priority: normalized heterogeneous observation dispersion.** At the updated states, CH3's model-conditional signal mass/RMS is250.844/102.994Hz at the incumbent and135.235/152.354Hz at the donor. These fitted, mixture-truncated residuals do **not** estimate measurement noise and must not determine sigma. The persistent CH3 discrepancy motivates a predictive model test, not truth-based downweighting. The old039/023 width2→1 experiment was an optimization continuation ending at original sigma; it did not test calibrated heterogeneous observation errors.

A bounded conditional-development-CV design would use prespecified even/odd20-second bins **within existing training only**. Hold both prescribed geographies fixed and initialize every arm with the same complete common state. Compare original sigma125Hz against a shrinkage RX/channel log-sigma extension fitted through the **full normalized marginal mixture likelihood**, including Gaussian normalization and clutter, never a residual-only regression. Both arms fit nuisance/calibration only on fold-training rows, under the original20s/600 caps; evaluate opposite training-fold only after all scientific outcomes seal. Specify bounds/shrinkage and exact null/gradient/posterior oracles before execution. Predictive improvement must reproduce across folds and cannot be defined by reference error. A failure to improve fold-excluded log density, or unchanged far preference, falsifies the proposed repair even if training density rises.

**Second priority: normalized satellite detectability versus uniform candidate prior.** The original B score assigns detection probability1.6/K to each candidate. The updated CH3 states have roughly56 visible candidates/window, but posterior effective candidate counts are5.089 at the incumbent and8.060 at the donor. At the far state, satellite65094 carries38.1% of CH3 and45.8% of CH6 signal mass. These are model assignments, not physical identities. Thus a simple story of many equally weighted accidental matches is unsupported, and visibility normalization contributes only30.214 of310.948 NLL loss. No authoritative beam footprint currently justifies a new beam mask.

A separate fold-trained shrinkage detectability-prior arm could test nonuniform satellite propensity while preserving the total detection budget, exact probability-of-zero-detection conditioning, positive normalized mixture and original sigma. Weights must be shared across receiver/channels and learned only from fold-training marginal density, without satellite truth or candidate deletion. The uniform-prior arm is mandatory. This model may strengthen the far mode because its concentrated satellite support is stable; that outcome would falsify a naive uniform-prior remedy. It would not identify satellite65094 as correct or incorrect. Do not combine this arm with heterogeneous sigma before their separate effects are assessed.

A common maximum design is2 folds×2 fixed geographies×3 arms (original, dispersion, detectability):12 bounded calls, organized as four independently bounded units with at most3×20s/600 calls each. No free-geography search or reference-driven selector. Full-training-derived discovery, candidate bank, clock/frame layout, initializers and geographies leak information across these internal folds, so results would be **conditional development CV, not untouched validation**. Original held and locked partitions must remain untouched. This is a proposal only; no new fit, sigma estimate, prior change, beam mask or temporal weight was executed here.

Source/protocol`34332cb86`;3 component/runner tests and Ruff passed, covering exact window alignment, additive block/channel closure, fixed-prior leave-out arithmetic, changed-input rejection and exclusive launch. Runtime `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-training-block-audit-059-v1`; terminal SHA256`f14568dc3abdcf05a916feaf4445c254156fa0e8f4d2f399e68c36ccba64001f`; seal`209a5cab7a2c1c3d9863390f91aa0a2856d5c906a537ec605242a331737b5c41`. Every bin count, RX/channel contribution and arithmetic sensitivity remains reviewable. Baseline selection and histograms are unchanged.
