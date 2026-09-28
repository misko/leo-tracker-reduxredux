# Probabilistic receiver-sequence follow-up

## Decision

This is an implementation design for one bounded predictive experiment on the existing ten recordings. Before fitting, it needs an executable freeze of the candidate domain, lane grouping, priors, periodic-density truncation/tolerance, and latent-state integration grid. It replaces the unique-hit/first-lag reduction with a likelihood for each complete raw candidate set in an exact receiver lane. The question is limited: after training-only Doppler hypotheses and a calibration-only reception model are frozen, does static geometry or nominal-tilt temporal geometry improve the **ungated** future-frequency predictive density over Doppler-only reception? No result exists yet.

This does not identify a satellite, resolve an integer CFO alias, measure a physical arrival order, calibrate an antenna, or measure localization accuracy. The four evaluation recordings are reserved predictive evidence inside a corpus already reused for research; they are not blind confirmation.

The 2.5 kHz circular gate used by the completed proxy sequence export is not used here. It selected the events whose residuals it then described, so its residuals cannot be a predictive endpoint.

## Authorities, roles, and analysis population

| Requirement | Existing artifact supplies it | Use |
|---|---|---|
| Whole-window train/reception/held roles and fixed six-calibration/four-evaluation split | grouped partitions | Keep source groups intact and preserve the split. |
| Training-only top-three Doppler forecasts, fitted CFO, visibility, elevation and ENU LOS | candidate bank | Fixed hypotheses, frequency means and geometric covariates. The bank does not export range. |
| Raw candidate IDs, native CFOs, ranks, margins, qualified candidate absences and paired timing | paired opportunities | Raw candidate-set outcome. |
| Exact session/channel/edge/RF anchors, alias period and training RX bias | alias mapping | Eligibility and fixed receiver-coordinate transform. |
| Decoded common-emitter labels, continuous coverage, surveyed phase centres and antenna response | unavailable | Never imputed or regarded as target truth. |

The scored population is a unique paired source window with its declared reception or held-frequency role, qualified receiver views, a qualified mapped receiver bias, and an exact session/channel/edge/RF lane shared by the competing frozen track hypotheses. Missing/unqualified views, unsupported transfer, malformed payloads and lane mismatches go into a complete exclusion ledger; none is a miss or clutter observation. A hypothesis that is invisible in an otherwise eligible common window remains in the mixture with signal-detection probability zero and its clutter-only set likelihood; it does not remove that hypothesis or window after forecasts are seen.

Within an eligible window score every passed raw candidate and an observed empty set once. Do not choose the closest raw candidate. The training prefix remains solely for reconstruction, candidate ranking, CFO and alias anchors. Fit shared reception and clutter parameters from reception windows of the six calibration records only. Seal their held-frequency windows during fitting. For each evaluation record, reception may update a frozen hypothesis mixture sequentially, and only the later held-frequency windows receive the primary score. No connected source group crosses roles.

## Candidate-set sequence likelihood

For hypothesis h, window i, receiver r, let Y_ir be the complete set of passed candidates: canonical frequency and its recorded rank/margin mark. Map either receiver into that track's frozen mapping.receiver_id coordinate using the signed RX1-minus-RX0 bias: leave r unchanged only when r equals the anchor; subtract the bias for RX1-to-RX0 and add it for RX0-to-RX1. Do not refit that bias or assume that RX0 is the anchor.

Let mu_hi be the frozen Doppler prediction and A_l the mapped canonical alias period. Use a periodic normal signal density:

    g_hi(f) = sum over integer k of Normal(f; mu_hi + k A_l, sigma_f,l^2).

Evaluate it stably as a periodic density. Do not select an alias integer, minimize a held residual, or place a residual threshold around mu_hi. Fit the lane-shared sigma_f,l, a simple signal mark density q_s(m), and lane-shrunk clutter intensity b_l(f,m) on calibration only. The mark model is fixed to candidate rank and standardised log(1 + margin). The clutter frequency density is broad and periodic, so a distant candidate is clutter evidence rather than an excluded row.

Each receiver may have at most one signal-origin candidate in one probe; all remaining candidates are clutter. With signal-detection probability p_hir, the unordered-set likelihood is:

    L_ir(h) = exp(-B_ir) product_j b_l(Y_irj)
              * [(1 - p_hir) + p_hir sum_j g_hi(f_ij) q_s(m_ij) / b_l(Y_irj)].

B_ir is integrated clutter intensity. Thus a qualified empty set has likelihood exp(-B_ir)(1 - p_hir): it is an observed missed detection, not an absent satellite. Multiple plausible raw candidates and compatibility with several hypotheses are summed as latent alternatives; no raw candidate becomes a decoded label.

Model correlated dual-RX reception with a shared window state u_i distributed as Normal(0, sigma_u^2) in both receiver logits. Integrate the product L_i0(h,u_i)L_i1(h,u_i) over u_i, rather than multiplying marginal receiver likelihoods. The primary model adds the fixed AR(1) sequence state u_i = rho^Delta_i u_i-1 + epsilon_i, with elapsed-probe Delta_i; estimate rho and sigma_u on calibration with fixed regularising priors. If the bounded implementation cannot integrate it stably, use the nested shared-window model rho = 0 in every arm and explicitly report temporal correlation unavailable. Never silently use independent receiver rows.

### One generative score per raw window

Different frozen tracks can project to the same raw paired window. They are competing explanations, never independent replicated observations. For each exact lane, give its training-selected tracks fixed equal prior weight (a_t); within track t use its log-domain-reconstructed candidate weights (w_{tc}) and retained mass (R_t). The one likelihood contribution for unique paired window i is

    P(Y_i) = sum_t a_t [R_t sum_c w_tc L_i(t,c) + (1 - R_t)L_other(Y_i)].

The reception filter updates this normalized track-by-candidate mixture, not separate track posteriors. Each raw paired source window therefore appears once in the likelihood and once in the recording-window denominator, even if several tracks or candidates explain it. The denominator is the number of unique eligible paired source windows, reported by exact lane and role; receiver views are factors inside that one window contribution. This eliminates duplicated-track pseudo-replication while preserving ambiguous raw candidates and the support ceiling.

## Nested reception arms

All arms share the same frequency density, clutter process, lane and receiver intercepts, latent state, candidate prior, eligibility ledger, priors and implementation. Only the signal-detection logit differs.

| Arm | Covariates beyond lane/receiver/sample-rate/sequence-time nuisance | Meaning of a better held score |
|---|---|---|
| D: Doppler-only | visibility | Frozen Doppler frequency evidence is sufficient for this comparison. |
| S: static geometry | D plus elevation and fixed-site LOS components | Static LOS geometry adds predictive information. |
| T: nominal-tilt temporal | S plus d_hir = n_r dot LOS_hi, and its predeclared elevation interaction | The documented nominal orientation feature adds predictive information under this model. |

n_0 and n_1 are the frozen nominal ENU boresights with upward component, (-sin(10 deg), 0, cos(10 deg)) and (+sin(10 deg), 0, cos(10 deg)), under the provisional RX0-west/RX1-east convention. They are sign-convention metadata, not fitted orientations or calibrated physical mounts. T has one shared, strongly regularised tilt slope; it may change detection probability, never the Doppler frequency mean. Use zero-centred normal priors after calibration-only standardisation: scale 1 for intercept/mark terms, 0.5 for geometry, and 0.35 for tilt. Use a recording random intercept and partial pooling by lane. One MAP parameter vector per arm is fitted from the six calibration reception subsets; deterministic forward filtering or fixed Gauss-Hermite quadrature integrates the latent state.

## Sequential future prediction and score

For each evaluation lane, start with component prior weights v_(t,c) = a_t R_t w_tc and v_other = sum_t a_t(1-R_t). These weights sum to one. Reception updates this single normalized component mixture, including the other branch, in log space:

    log v'_k = log v_k + log P(Y_reception | k) - log normalizer.

The component reception likelihood integrates the correlated latent-state sequence. It is not a product of independently integrated window marginals. The stored candidate bank remains immutable; conditioning may change predictive weights and their ordering. There is no coefficient refit, alias choice or CFO update. In particular, do not restore the original R after updating the joint component weights: that would undo the other-branch conditioning.

Score the complete held block by its normalized predictive density:

    P(Y_held | Y_reception) = sum_k v'_k P(Y_held | Y_reception, k).

The component held-block density carries forward the reception latent-state distribution and integrates the held sequence. A forward factorization may condition each one-step score on preceding held observations; it must score each observation before consuming it, without parameter fitting or event selection. This is equivalent to the joint held-block score, not repeated independent use of an unchanged window mixture.

L_other is a common calibration-fitted broad/clutter fallback used identically by D, S and T. It prevents silent renormalisation of top-three mass to one. The primary endpoint is the **ungated held-frequency log predictive density** difference T minus D, normalized by the number of unique eligible paired windows within each evaluation record, then averaged with equal recording weights. S-D and T-S are prespecified secondary contrasts.

Every raw candidate frequency and mark in every eligible held receiver view contributes. Every qualified empty set contributes. There is no closest match, circular gate, post-score ambiguity rejection, or held residual used for selection. Report audit strata for both-present, one-empty, both-empty and multi-candidate windows without promoting them to new endpoints. Use leave-one-evaluation-recording-out score range and a whole-recording bootstrap only as descriptive uncertainty; four clusters cannot support a physical-discovery p-value.

## Concentrated top-three prior and support ceiling

The candidate-leverage diagnostic must be bound into the receipt. It found 27/30 tracks with conditional top-three weight at least 0.999999, 19 exactly float 1, and 5 with only one positive displayed weight. In evaluation, 11/12 selected tracks are saturated; the sole-lag hypothesis has a rank-1 versus rank-2 training log-likelihood gap of 1,977.5368 nats, while the evaluation median gap is 272.6738 nats (range 2.6518–12,503.48). This is a limiting prior/model assumption, not physical confidence or target truth.

Reconstruct w_h in the log domain from the frozen finite training log likelihoods, preserving the pre-existing likelihood scale and without probability flooring. This distinguishes display rounding from numerical underflow; do not change a temperature, add a prior floor, or rerank candidates after these diagnostics. The existing top-three support remains incomplete: maximum omitted mass is 13.379% in calibration, while evaluation omitted mass is approximately 9e-12. The omitted catalogue is not available for an additional target likelihood. L_other honestly represents that unavailable branch; a result therefore supports only the shortlist-plus-fallback predictive model, never a full-catalogue association probability.

Report R, prior and reception-updated entropy, positive-weight count, log-likelihood gaps, and per-rank score contributions. Do not claim that a concentrated posterior is an identified satellite.

## Negative controls

Keep T calibration coefficients fixed and use the identical unique held-window and hypothesis population, covariate availability, frequency density, clutter, training prior weights and score denominator. Recompute reception filtering and the held-block score for each control; its conditioned weights may differ. Only the predeclared geometric covariate transformation changes.

1. **Receiver swap:** exchange n_0,n_1 assigned to RX0/RX1, leaving receiver labels, offsets and native transforms intact.
2. **Trajectory reversal:** reverse the time-sorted geometry-covariate sequence within each track, candidate and role, separately for reception and held periods. This reverses covariate order on irregular samples without inventing a nearest-time interpolation. Keep true Doppler frequency prediction, raw data, lane and actual observation times unchanged. Only the reception-probability features are reversed.
3. **Static nesting:** fix the T tilt coefficient to zero and reproduce S exactly. Failure is an implementation failure.

A similar gain under swap or reversal diagnoses receiver-label or schedule structure. Passing controls supports only a nominal-geometry predictive relation, not a physical tilt measurement.

## Go/no-go and bounded run

**Go** only after an executable design receipt freezes the candidate domain, lane/track mixture weights, periodic-density tolerance, clutter parameterisation, priors and latent-state integration grid, and a pre-fit audit verifies: exact-lane eligibility can be recomputed from frozen artifacts; every eligible paired window has exactly one set-likelihood contribution; train/reception/held source groups remain disjoint; calibration has finite likelihood under each arm; periodic density, empty-set, candidate-permutation, multi-candidate, alias-shift, shared-RX, unique-window mixture, and control tests pass; and S is reproduced by T with zero tilt.

**No-go** if any audit fails, if the latent-state integration is numerically unstable under the fixed budget, or if exact-lane/role accounting cannot reconcile. Record the blocker; do not widen gates, borrow lanes, drop ambiguous candidates, tune priors, temperature or candidate domain, change the six/four split, or collect RF.

The artifacts make the predictive experiment feasible, but they do not establish that meaningful physical tilt inference is possible. The unique-hit proxy had one uncensored reception lag and none held, while most hypothesis-window rows were exact-lane exclusions. In the sole-lag case audit, RX0 had 10 unique, 3 ambiguous and 99 no-hit opportunities; RX1 had 12, 15 and 85 across 112 eligible opportunities per receiver. Its first-hit brackets were 0.281 s and 0.942 s wide and the conditional lag bracket was 8.4009192--9.6240198 s. Seven dual-unique windows across 17 inspected cases were proxy epoch-compatible, but these are discrete candidate observations, not continuous shared-target evidence. Raw candidate sets retain more information, but lack common-emitter labels and continuously sampled reception. Call the nominal feature useful only if real T beats both D and S on the primary score and its gain exceeds both the receiver-swap and trajectory-reversal gains on the identical held population. Even then it is a model-specific predictive result, not a calibrated antenna tilt, receiver arrival order, satellite identity or localization improvement.

Execute one existing-artifact run with one numerical thread, nice 19, 4 GiB address-space limit and 300 seconds. The final report must include hashes, full denominator/exclusion ledger, calibration receipt, per-record D/S/T/control held scores, all contrasts, support/entropy diagnostics, and the limits above. No new RF, raw-IQ work, QNAP mutation or production change is part of this experiment.
