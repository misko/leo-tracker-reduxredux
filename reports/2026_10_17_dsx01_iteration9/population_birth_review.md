# Population support before another residual-model search

**The most direct new hypothesis is a bounded population branch over metadata-eligible but training-unselected candidates, with a sparse metadata-defined identity process.** This is a design proposal, not an approved model or measured recovery. Its first useful deliverable would be a normalized finite-state kernel plus a timing-integration accuracy/cost qualification—not another localization fit. No numerical objective, propagation, optimization, model implementation or reference lookup was performed for this review.

The [cold forecast diagnosis](../2026_10_17_dsx01_iteration5/cold_prediction_diagnosis/README.md) found1190/1410 original held assignments had their original full-data winner absent from the25-ID early-selected bank. Those are descriptive, full-data-conditioned labels, not emitter truth. The frozen [metadata bank](../2026_10_17_dsx01_iteration5/metadata_bank/README.md) supplies845 potentially visible IDs, including those labels, using causal elements, the broad prior and complete capture metadata. It has no per-transmitter RF-support authority. Its52.95MiB orbit bank has never entered a fitted likelihood. This is more direct evidence for investigating candidate availability than for polishing the rejected coherent or new-point density families; calibration extrapolation and wrong original labels remain independent confounds.

## Precedents and distinction

The earlier [metadata-bank recommendation](../2026_10_17_dsx01_iteration5/metadata_bank/README.md) already proposed this population direction but did not implement it. The [uniform passed-peak mixture](../2026_10_17_dsx01_iteration4/peak_mixture/README.md) marginalized measurement alternatives within each probe, retained the selected satellite bank and failed its expansion gate. It is not a population of previously excluded catalogue objects and should not be rerun under a new name. The [iteration8 coherent model](../2026_10_17_dsx01_iteration8/coherent_pilot/README.md) shared identity over CFO-selected fixed groups; it failed its predictive gate and omitted the group-selection probability. The [matched point-density control](point_density_control/README.md) also failed its gate. Neither result tested an unsupported845-ID population with metadata-only Markov structure. A targeted search of the older quad/multiscan research found no already evaluated version of that precise combination.

## Common notation and frozen boundaries

Let I be the original TRAIN-selected bank, E the frozen metadata-eligible bank, and M=E\I. Require verified I⊆E; reject mismatched authorities rather than manually inserting IDs. Each original observation remains one original winning CFO mark y_n at its actual time/RF/RX/channel. U=1/ALIAS and phi_n,s(delta) is the125Hz wrapped-normal density at the unchanged physical prediction with total shift c_common+delta, complete current receiver calibration and actual RF. Visibility w_n,s(delta) is the same compact-horizon function evaluated at that shift.

The existing selected q_s sum to Q=1.6. Preserve those existing fitted coordinates and their priors; introduce no q or fitted timing coordinate for any unsupported ID. Choose normalized population weights p_u using only the frozen catalogue/metadata policy; uniform over M is the leanest declared ignorance prior, not RF-emission evidence. Let **eta** denote the new population-budget fraction in this document, not iteration8's all-clutter probability. Split the same q budget:

```text
q'_s = (1-eta)*q_s, s in I
q'_u = eta*Q*p_u,   u in M
sum(q') = Q
```

No eta value or persistence scale is endorsed here. A fixed value or a proper single global prior must be declared before any outcomes; no held/window choice. At eta=0 use the original bank exactly, without zero-q ghost states.

Require every retained q' below1 so odds stay valid; an empty unsupported bank forces eta=0. Population weight belongs to each catalogue object, not independently to each timing node. A separate metadata-only membership check confirms the45 blocked-TRAIN selected IDs are also inside the845 bank, giving800 unsupported IDs for that protocol; the25/820 split refers to the earlier half-forecast protocol.

For unsupported timing, start from the existing2s relative scale around the retained common timing. A proper normalized truncated N(0,2²) on the existing feasible orbit/time domain needs positive quadrature weights a_l summing to one. Common-time-dependent truncation, node motion and normalization require their own derivatives. This extends the selected-bank prior by a population distribution conditional on its common timing; it is not the original zero-sum basis enlarged silently to845 objects. Do not add a second MAP timing penalty for an already integrated latent offset. The selected timing/common priors remain once-only and unchanged.

## 1. Independent population point control

Use the original legacy odds a(q,w)=q*w/(1-q*w), with its original clutter intensity lambda. Define

```text
A_ns   = a(q'_s,w_ns),                         s in I
A_nul  = a_l * a(q'_u,w_nu(delta_l)),           u in M
Z_n    = lambda + sum_s A_ns + sum_u,l A_nul
f_n(y) = [lambda*U + sum_s A_ns*phi_ns(y)
                         + sum_u,l A_nul*phi_nul(y)] / Z_n
```

Weights a_l are **outside** the odds: splitting q into quadrature nodes inside the nonlinear odds would change the prior/model. Integrating every emission gives exactly one. The total q budget is preserved; the actual signal posterior/odds sum need not stay numerically unchanged when q is redistributed. A larger catalogue receives no extra unnormalized mass. At eta=0 this nests the original shared point PDF and all parameter gradients, subject to its existing floating-point wrapped-Gaussian convention.

This ratio of integrated intensities is a well-defined normalized density. It is **not** generally the expectation of the old normalized likelihood over a globally shared vector of unknown satellite timings: expectation and division do not commute. Multiplying these point densities redraws unsupported timing uncertainty independently at each point and supplies no coherent timing evidence. Retain it as the cheap availability-only control, not the claimed full orbital-error marginal.

## 2. Preferred conditional research model: stay/reset HMM

Use states0 (clutter), selected s, and unsupported (u,l). Reset probabilities r_n are `(lambda, A_ns, A_nul)/Z_n`, using exactly formulation1's weights. Emissions are U for state0 and the corresponding phi for satellite states. Initial probability is r at the first metadata epoch. Each RX/channel/actual-RF lane is its own sequence; new lane/capture boundaries reset. Exact simultaneous batch convention, long-gap resets and any maximum episode horizon must be fixed from metadata, never CFO matching.

For metadata-only stay probabilities s_ni, use the sparse transition

```text
T_n(i,j) = s_ni * 1[i=j] + (1-s_ni)*r_nj
alpha_pred_nj = s_nj*alpha_(n-1),j
                 + r_nj*sum_i[(1-s_ni)*alpha_(n-1),i]
```

For example a declared persistence amplitude times exp(-dt/L), optionally multiplied by the destination-epoch visibility of the same state, gives s_ni∈[0,1). The clutter stay policy must be explicit too. This has exact row sums and O(D) propagation, not an845² transition matrix. A visibility mask applied *after* transition without redistributing mass is invalid. Visibility/q/reset-normalizer derivatives enter the fitted gradient even for states with little signal posterior.

Zero persistence gives formulation1. Zero population budget **and** zero persistence gives the original shared point model. Zero population budget with persistence isolates persistence among the original candidates; it does not establish availability recovery. These nestings and a chance-match control are essential before attributing anything to the full branch. Candidate-state persistence can explain crossings probabilistically without constructing groups from their measured CFO.

The timing node remains fixed across every stay run: this integrates the product of emissions at one shared latent episode offset. Independently integrating each emission is a different model. A reset draws a new state/node, so this HMM treats timing as **episode-specific**, including a new draw if an ID returns after a reset. It is not exact marginalization of one globally fixed orbital timing per satellite throughout a recording. That more physical static-latent model remembers every object's past timing uncertainty and is not the simple O(D) HMM. Do not claim identical priors or solve it implicitly with hundreds of fitted shifts.

A clutter state with nonzero reset probability admits individual outliers and whole clutter runs. It may charge transitions around a short dropout; test that behavior explicitly. Adding iteration8's fixed epsilon=.12 uniform component inside every satellite emission would change the zero-persistence point counterpart, so it must not be smuggled in while claiming exact legacy nesting.

## 3. Metadata-episode birth mixture, if HMM complexity is unwarranted

For a partition fixed solely by lane/time metadata, a simpler normalized episode model is

```text
F_g = (1-b)*product_{n in g} f^I_n
      + b*sum_u p_u * integral product_{n in g} h_nu(delta) p(delta)d(delta)
h_nu = (1-epsilon)*w_nu*phi_nu + [1-(1-epsilon)*w_nu]*U
```

Here f^I is the unchanged identified-bank PDF, with its priors only once outside the likelihood. Birth mass b is fixed per episode, not multiplied by the number of candidates; b=0 exactly recovers the identified branch. This has point clutter and a shared unsupported timing inside each metadata episode, without a CFO-selection normalization problem. However, it is not the same per-point q-budget split as formulations1–2, permits only one unsupported identity within that branch's episode, and is sensitive to arbitrary episode boundaries. It is a distinct, less flexible fallback hypothesis—not another run of the old CFO-grouped coherent model. No formulation should be chosen using later requested-window counts.

## Honest held prediction

For a frozen HMM and parameters fitted on TRAIN only, retain every known metadata epoch and set held emission likelihoods to1 when computing Z_TRAIN. No held CFO enters state inference, transitions, calibration, bank selection or initialization. Its complete joint held log predictive density is

```text
log P(y_HELD | y_TRAIN, metadata) = log Z_ALL - log Z_TRAIN
```

For one held block B, score `log Z_(TRAIN+B)-log Z_TRAIN`, leaving all other held emissions1. Such block-conditional scores generally do **not** sum to the all-held joint score. The plain product of proper point densities is a normalized comparator on the same outcomes. Freeze parameters and prediction authorities before any held score. Latent-state/signal posterior classification is separate from the old point classifier and RMS; smoothing with held observations is evaluation, not a held-blind predicted identity. Do not turn posterior count gains into truth labels or geographic accuracy.

## Timing integration is the gating feasibility issue

Three/five Gaussian nodes cannot be presumed adequate. At hundreds of Hz/s, seconds between nodes can miss a125Hz emission peak. For m coherent observations the local timing peak can be as narrow as roughly `sigma/(|dCFO/dtau|*sqrt(m))`; per-point quadrature closure does not establish joint-episode closure. Horizon transitions and piecewise orbit interpolation add structure. A zero-offset delta or silently reduced2s prior is not an acceptable speed fallback.

Before fitting, derive a conservative slope/visibility resolution envelope from RF, bank cells, times and the allowed regional/timing domain only. One possible Doppler derivative bound inside a cell is `RF/c * (|v'| + |p'|*|v|/r_min)` with a proven positive lower range bound; sampled maxima are not certified between-sample bounds. Set and test quadrature resolution against the longest permitted episode, not just one row. Compare nested grid/adaptive integrations, including narrow synthetic peaks between nodes, alias seams, truncated tails, interpolation boundaries and long episodes; keep error estimates and all costs. TRAIN-only actual integral checks may qualify a frozen rule; held measurements must not set resolution. If the required grid is too expensive, stop. A fixed finite offset-mixture may be studied instead only as an explicitly approximate new prior with its own diagnostics and point control.

The existing bank has3,369,860 N×K pairs. Nine timing nodes are only an illustrative cost scale, **not an accuracy recommendation**: the25-known/820-unsupported case has7406 HMM states and about29.5million emission cells over3988 rows, roughly225MiB per float64 state-time plane before geometry derivatives. Streaming/checkpointing can reduce storage and O(D) transitions avoid quadratic cost, but cannot remove the emission/gradient integration work. The52.95MiB propagated bank is additional. No fitting throughput or120s feasibility has been measured. Dense timing resolution can make this intractable even when the Markov recursion itself is cheap.

## Minimal gate before any real fit

First qualify a generic finite-state kernel only: exact small-state path enumeration; circle/torus normalization; analytic prediction, visibility, q-budget, reset and mixture gradients; log stability; candidate permutation and prior-weight-preserving cloning; exact eta=0/persistence=0 nesting; all-invisible/all-clutter/dropout cases; and TRAIN/excluded-CFO perturbation invariance through forward prediction. Include zero-information gaps and the nonadditivity of block conditional scores.

Only then consider one bounded metadata/physics timing-grid accuracy-and-cost prototype, with no localization optimization and a controlled stop. Require source/input/bank/RF/time closure, no invented RF eligibility, exact legacy old-bank endpoint replay, preserved selected calibration/timing/q priors, normalized mass and accurate complete-episode timing integration. No845 free q/timing coordinates, tiny unreported prior replacement or uncounted per-candidate search.

If those gates pass, root must separately freeze the future TRAIN-only protocol and hypotheses before any pilot. It needs matched hard-bank, population-point and persistence controls, c0/fitted-c controls, retained denominators and costs, plus a metadata-preserving TRAIN time/CFO permutation that destroys orbital coherence. Candidate relabeling with unchanged physical predictions is merely an invariance check, not a negative control. Record false-assignment/rotation behavior, whole-held proper scores, original-classifier intersections and all nonstationary outcomes. No independent RF-support authority or correct-emitter labels have appeared, and the already exposed S03 oracle cannot become new confirmation. No model implementation or fit is authorized by this review.

A held permutation diagnostic must recompute the complete joint forward normalizer on the permuted marks; recycling an independent point-density permutation score does not test the HMM. Whether a null also reruns TRAIN inference must be declared and budgeted separately, with every null retained rather than choosing a favorable permutation.
