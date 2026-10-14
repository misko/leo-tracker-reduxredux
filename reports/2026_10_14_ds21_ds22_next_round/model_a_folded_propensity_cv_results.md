# Final A folded propensity: randomized conditional-development CV

Learned satellite propensities improve opposite-fold frequency fit at A035's current full geography, but worsen it at A053's current full geography. This is mixed evidence about the frozen-shift final likelihood, not a localization result. No position reference or original held observations were read.

The runner is source commit `5fbe28d82`; twenty component tests and Ruff pass. It reuses the qualified folded observation port without changing A's bank, common calibration/clock/timing priors, fitted-c freedom or fixed learned high-band shifts. The two geography roles are the current full endpoint and its own inherited low-stage endpoint. Both start with the **same current full non-position state**, and propensity coefficients start at zero. The original 25 km A035 and 50 km A053 disks remain in force.

Whole original 20-second blocks were randomized once per recording using `model_a_randomized_block_folds.split`, seed **20261014**. The complete saved maps yield A035 1512/1395 and A053 881/989 fold windows. Correlated receiver rows remain together; no balancing or redraw was performed. These are **conditional development folds**: discovery, candidates, learned shifts, clock nodes, initializers and both geographies came from full training data. They are not untouched validation or independent half-band localization.

Exact randomized-plan qualification passed with **24 objective evaluations, zero fits**, in 5.099 seconds. All three arms were then fitted independently for every case/fold/geography: legacy event density, conditional CFO density, and conditional density with learned catalogue propensities. Each retained the original **20 seconds / 600 iterations** and independent strict KKT ≤0.001. The source fitter may perform multiple line-search objective evaluations per iteration; 600 is not an objective-call cap.

All **24 original fits** returned and all eight three-call units completed; wave148 took **25.966 seconds** with four single-thread workers. **19/24** endpoints passed strict KKT. The five failures remain excluded and were not retried. All outcomes sealed before prediction, with seal `c2fc4964940e20ef32a5c4326c35edc44c5e8045842b6d5af98f17fde0feb646`. Post-seal scoring used 24 full-model evaluations, zero fits, in 3.652 seconds.

| Case / geography | Legacy accepted | Conditional accepted | Propensity accepted | Complete two-fold q−conditional conditional NLL | Raw event NLL delta |
|---|---:|---:|---:|---:|---:|
| 035 current full | 1/2 | 2/2 | 2/2 | **−1348.582836** | −1325.764622 |
| 035 own low | 1/2 | 2/2 | 1/2 | unavailable | unavailable |
| 053 current full | 1/2 | 2/2 | 2/2 | **+377.047164** | +398.559474 |
| 053 own low | 2/2 | 1/2 | 2/2 | unavailable | unavailable |

Negative NLL changes favor propensities. A035's current-full fold effects are −1143.306419 and −205.276416 conditional NLL. A053's are +553.839859 and −176.792695, so averaging masks a reversal. At the low geography, the sole eligible matched fold improves −1011.897428 for A035 and −47.520362 for A053; neither constitutes a complete two-fold estimate. Failed-endpoint predictions are retained only as explicitly ineligible diagnostics. The numeric receipt includes raw/conditional likelihood, normalization, receiver/band/block summaries, separate timing/clock/propensity priors, complete vectors and exact scientific bindings.

These fits changed no geography. They neither establish position improvement nor justify selecting an arm by cross-model MAP. A's final learned high-band contrast remains fixed and `group_count=0`; uncertainty in that learned shift is still absent.

## Approved next stage: complete-state full-training release

The next intervention is **25 new full-data free-position continuations**, approved after these CV outcomes: A035 legacy/conditional/q **3/5/4** calls, A053 **4/4/5**. Each arm receives one common source start plus every one of its accepted complete fold states; all nineteen accepted vectors, clock nuisances and q tails are preserved together. The five nonstationary CV states are excluded rather than retried. Counts differ because realized eligibility differs: this is not a matched-search-cost causal comparison.

The new runner must freeze and qualify these exact starts first, retain original 25/50 km disks and frozen learned shifts, use 20 seconds / 600 iterations and strict full KKT, and rank only within each arm's own full-data objective. All 25 outcomes and selectors must seal before configured-reference evaluation. No additional fixed full profiles are inserted. Original incumbents remain explicitly named; any feasible embedded zero-tail score below a learned-q result must flag an optimization gap. Full-data release is an additional development experiment, not validation of the folds.

[Numeric results and provenance](model_a_folded_propensity_cv_results.json). Scientific output: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-folded-propensity-cv-035053-v1`.
