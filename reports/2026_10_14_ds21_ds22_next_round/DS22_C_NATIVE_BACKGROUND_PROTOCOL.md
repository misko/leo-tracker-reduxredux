# DS22 C053/C075: native selected-frequency background qualification proposal

Status: **protocol only; no new model fits authorized or reported here**. The C053 solver controls recover a strict, more efficient lower-distance endpoint, but its full training score still loses by 4564.120327. Further identical-basin optimization does not address that evidence ranking. Test whether the assumption of a uniform background frequency density contributes, while preserving original native signal physics and branch evidence.

## Prior work and reusable boundary

The repository already has `tools/rx_empirical_background.py`, including 16-bin circular frequency estimates in a paired count/set model. Its pseudocounts and event model differ from this proposal. The new folded-B component `src/leo/analysis/research/model_b_empirical_clutter.py` at `c5c8436c6` uses 16 bins and 32 uniform pseudowindows per RX/channel/exact-RF lane; its actual B081/B115 uniform/gradient qualifications passed with 136 objective calls and zero fits. Neither is an existing native-C branch-preserving localization control. The report/source search found no earlier native-C empirical-background localization experiment; this is a scoped repository audit, not a claim that empirical backgrounds are novel.

Earlier native C visibility-mass, satellite-propensity, timing, alias, receiver-clock and band-calibration controls changed different assumptions. Preserve those results and avoid presenting a new background as a normalization repair. B's frozen estimator is ALIAS-periodic: inserting its density directly into native C would multiply uniform signal/clutter odds by approximately `sample_rate/ALIAS = 11`. **That substitution is prohibited.** Agent B reviewed this distinction and supports a new narrow pure estimator with explicit domain width, without modifying its frozen source.

## Explicit observation-domain model

Use native sample-rate circle width `F`, independently validated from each source model. Retain exactly the available native branch CFOs, native timestamps, normalized waveform weights `w_ib`, original candidate bank/visibility, satellite weights, Gaussian sigma, receiver lifts, complete calibration/timing and all priors. No branch duplication, additional peaks, inferred waveform power, or posterior-based training weights. Unavailable branches have zero weight and each window's available weights sum to one.

The new pure estimator accepts numeric measured branch CFOs, availability, fixed waveform weights, exact lane keys, window IDs, an own-training-fold mask and explicit F. Each selected window contributes total weight one across its existing alternatives. For lane/bin j:

`p_j = (sum_i,b w_ib * I[branch in bin j] + 32/16) / (own-fold training-window mass within this lane + 32)`.

The 16 equal bins are anchored at `-F/2`, with `g(y)=16*p_bin(y)/F`; unseen lanes use `1/F`. Receipts bind probabilities, fractional counts, total window mass, source branch evidence, complete fold map and training-window hash. All densities freeze before objective evaluation. Bin membership depends on measured CFO, never fitted prediction; therefore this change introduces no optimizer-coordinate bin crossings. Original hard visibility discontinuities remain.

For each observed native window, background density is `G_i = sum_b w_ib*g(y_ib)`. Let q0 be the original fixed clutter mass, p_k the original satellite probabilities, and phi_F the original native wrapped-residual Gaussian. Preserve the original signal numerator exactly:

`S_i = (1-q0) * sum_k,b p_k*w_ib*visible_ikb*phi_F(y_ib-prediction_ikb)`.

The proposed numerator is `q0*G_i + S_i`. Uniform g gives **exactly q0/F**, so raw uniform objective, full gradients and posteriors must replay the original native source. No satellite propensity, clock or calibration freedom is added.

Normalization is conditional on the frozen branch pattern, waveform weights and visibility. Define a one-dimensional common circular translation u of all measured alternatives, retaining their relative offsets. Every translated g integrates to one, hence `integral sum_b w_ib*g(u+offset_ib) du = 1`. The original narrow wrapped-residual Gaussian integrates to `E=erf(F/(2*sqrt(2)*sigma))`; for the qualified original narrow-Gaussian domain E is numerically one, but record it rather than silently assuming an exact infinite-support integral. Conditional integrated numerator mass is

`M_i = q0 + (1-q0)*E*sum_k,b p_k*w_ib*visible_ikb`.

The matched conditional baseline and empirical arm both use `rowNLL = -log(q0*G_i+S_i)+log(M_i)`. Raw uniform remains a separate exact source oracle, not mixed with conditional selectors. In the original supported narrow-Gaussian domain M must also replay `model_c_visibility_mass.support_mass` to numerical tolerance. This is **not** a normalized joint model of detector sets, branch availability, waveform evidence, occurrence/absence or winner selection. Visibility and branch evidence are conditioned on; original observations may contain real signals, so g is an observational reference, not verified clutter.

## Source states and qualification, before any fitting

Use fitted-c only. C053 starts from the original 44-candidate, no-clock native full model and its original full/LOW/HIGH training-selected complete states, with the already qualified exact half-to-full transport. C075 uses the completed 87-candidate no-clock union full model and its corresponding current same-bank full/LOW/HIGH selected complete states. Do not mix historical smaller-bank C075 halves, import clock-arm states, or use reference distances to choose states. Pin exact source seals, chosen source indices, domains and complete vectors in a new manifest before preparation. These three states are validation probes, not permission for optimizer calls.

Use the existing randomized whole-20-second block helper, seed 20261014, per-recording reset, saved map and no redraw. Histogram fitting uses only its own fold. Full-derived discovery, bank, frame and source geographies make any later opposite-fold result conditional development evidence; original held and locked observations remain untouched.

Component tests must cover: nonuniform density integrals; exact uniform nest; weighted alternative mass one per window; unavailable/missing branches; duplicate alternatives without count inflation; unseen lanes; permutation invariance; own-fold isolation; sample-rate versus ALIAS units; source raw and conditional likelihood/posterior accounting; complete physical/nuisance derivative chain; and full/partial/zero visibility mass. Numerical quadrature must vary the common measured-phase translation while freezing branch offsets/weights and visibility, including nonzero offsets and nonuniform histograms. Do not integrate branches as independent observations.

Proposed actual-data qualification ceiling: **120 full-objective evaluations per case, zero optimizer calls**, internal 120 seconds and independent external TERM135/KILL140; up to two single-thread workers. Before execution, implement and test the source-bound runner and publish its exact count inventory (the ceiling is not permission to hide variable work). At all three source states and both folds, replay original raw uniform values/gradients/posteriors, conditional normalization, empirical accounting and finite-difference physical/nuisance directions, with explicit native prediction counts. Record visibility crossings separately and do not claim smooth-gradient closure across a changed hard support pattern. Failures remain terminal in their namespace; no automatic retry.

Only after qualification and review should a distinct bounded matched conditional-uniform versus empirical-background predictive protocol be proposed. It must use identical fixed training-derived geographies, non-geographic seeds, domains, calibration priors and budgets; seal every profile before opposite-fold prediction. No free localization, hyperparameter tuning, model promotion or new C053 optimizer cycle is included in this protocol.

## Implemented qualification inventory

The approved implementation uses **96 full-objective evaluations per case**, zero optimizer calls and zero additional explicit orbit predictions. Each full objective performs one native orbit prediction. For each of three complete source states: two full raw source/uniform replays, then for each of two folds three central evaluations (source conditional, uniform wrapper, empirical wrapper) and twelve signed finite-difference evaluations. This is `3 × [2 + 2 × (3 + 12)] = 96`. The six finite-difference directions are both geographic coordinates, c, common timing, one relative-timing coordinate and one original group offset. Uniform closure compares all physical/nuisance gradients and satellite posteriors, not only these six directions. Stable native interpolation cells are required for timing FD; hard visibility crossings explicitly fail qualification.

New sources are `native_empirical_background.py`, `native_background_objective.py`, and `tools/ds22_native_background_qualification.py`. The native objective port copies the qualified native propensity wrapper's chain rule while replacing only its pure density call; no monkeypatching or folded likelihood import occurs. Source freezing recursively walks local AST imports, including imported child modules and relative imports, and unions them with genuine parent authority source bindings. Tests explicitly check closure contains native density, propensity, orbit and group-calibration dependencies. External TERM135/KILL140 remains required even when nested preparation alters an internal timer. No fit is authorized by successful qualification alone.
