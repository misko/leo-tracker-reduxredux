# Identity, uncertainty and information: independent methods review

The strongest next experiment is a **common-observation identity challenge for
the four chronological fast-scan nominees**, with an unresolved outcome and a
genuinely separate owner where available. The second is a small paired nuisance
ablation of the already generated fast synthetic realizations. Information-based
allocation of existing sources is a useful third step once ownership and actual
geometric independence are established. A generic new soft-label fit, local
phase integral or wider receiver process would repeat substantial prior work.

This was a read-only source/result review, not a new fit, gate change or
publication. The operational comparator remains fresh ALGO02-v1 plus qualified
causal signed phase priors and equal-assignment-prior family cavity. All current
DS24 results are examined development evidence.

## Evidence table

| Existing method/control | What was actually tested | Result and missing evidence |
| --- | --- | --- |
| Soft predictive identities | Four engineering plus seeded random20 DS23 scans; variational shared Gaussian calibration latent and independent track labels; original 300 Hz source biases; candidate pool only curved-supported/incumbent predictive families; original track aliases fixed. Curved calibration/Gamma stay unchanged at fixed position. | All24 final models audited/passing, but random20 fitted-c mean 1.507979→1.509590 km, maximum error change32.18 m. RF-score control adopts0/24. Alternate initializations improve the bound by at most9.10e-13. This tests neither full-catalogue new-family ambiguity, an unknown/clutter outcome, alternative aliases, nor curved-label selection. [Saved review evidence](evidence/soft_summary.json). |
| Grouped new-family prediction | Full410 available DS23, causal catalogue coarse search/best7 refinement, two/three whole fragments with at least two RX/channel owners, same candidate in both c arms, fixed-radio gates, unresolved-curve null, multiplicity penalty, shared Gaussian phase/three-mode uncertainty and old/new cross-covariance. | Fitted-c mean1.469461→1.448708 km; median1.178102→1.178987. Fast204 mean1.240377→1.242341 and median1.031316→1.044628 worsen despite more accepted points. Full original likelihood remains, but some postfit IDs are lost. This is strong evidence against rerunning the same grouped rule as a generic fast solution. [Full report](https://github.com/misko/leo-tracker-reduxredux/blob/dad19ba5ef74744d8234ccb4d461bac8444663aa/reports/2026_10_22_ds23_dbg01_iteration_007/README.md). |
| Direct orphan/temporal mixture | Original out-of-graph points, wrapped active-family mixture plus uniform clutter; shared calibration uncertainty, integrated signal fraction; EM-guided importance proposals retain exact prior/proposal correction. Separate old/new predictive covariance control exists. | Prior sampling collapsed to about1–3 effective draws; bounded importance refinement qualified only0221's strict no-extra-constant model at its incumbent. Every new fine-grid position failed paired numerical qualification. No position adopted. More samples/another generic mixture is not a new hypothesis. [Iteration004](https://github.com/misko/leo-tracker-reduxredux/blob/dad19ba5ef74744d8234ccb4d461bac8444663aa/reports/2026_10_22_ds23_dbg01_iteration_004/README.md). |
| Temporal native path recovery | Active-curved-family HMM with explicit clutter, independent versus5s persistence,19 time/CFO permutations, whole-path correlated-covariance identity check and joint predictive-only position factor. The HMM probabilities are proposal tools, not calibrated identity probabilities. | Both unscreened unions fail on0272/0068. Whole-path screening leaves78/83 points on0272; independent fitted-c error3.931 km, temporal3.746 km. On0068,37/19 points pass residuals but strict phase qualification fails. This already tests temporal continuity and post-selection path validation; it cannot discover absent active families. [Iteration005](https://github.com/misko/leo-tracker-reduxredux/blob/dad19ba5ef74744d8234ccb4d461bac8444663aa/reports/2026_10_22_ds23_dbg01_iteration_005/README.md). |
| Gamma evidence audit | DS23-0257 incumbent and identity challenger; sample noise/Student precisions, analytically integrate Gaussian coefficients at fixed geometry; exact prior/proposal ratios and fractional powers. |4096-draw ESS3340/3426; challenger still worse by about15.33 objective units. This does not support blaming that identity decision on the VI bound. It did not integrate nonlinear Doppler phase or position. [Uncertainty report](https://github.com/misko/leo-tracker-reduxredux/blob/dad19ba5ef74744d8234ccb4d461bac8444663aa/reports/2026_10_19_ds23_uncertainty_study/README.md). |
| Parent nonlinear phase correction | Five DS23 cases, both c arms, 3×3 RF-endpoint grids, correlated Gaussian phase draws, exact nonlinear nominal Doppler, other Gaussian coordinates integrated; Gamma precisions and physical-shape design held at each existing VI point. | All importance checks pass; maximum predicted local shift22.795 m, independent-seed disagreement0.062 m. This specific protocol entails829,440 curved/joint draw-evaluations. It is already a parent nonlinear-phase slice diagnostic, not full hierarchical marginalization. [Protocol](evidence/phase_protocol.json), [independent audit](evidence/phase_audit.json). |
| Gaussian log-volume removal | Twenty DS23 development cases, common frozen precisions, same observations/priors, marginal versus penalized-profile cold refits. | Dropping volume moves c0 positions a median5.84 m, maximum15.89 m. Earlier larger local sensitivities were not realized gains. Do not remove normalization/volume to improve GPS. [Frozen-precision report](https://github.com/misko/leo-tracker-reduxredux/blob/dad19ba5ef74744d8234ccb4d461bac8444663aa/reports/2026_10_19_ds23_frozen_precision/README.md). |
| R2 target uncertainty | Only the new target's phase is directly integrated under the explicitly conditioned Student law; original parent VI/Gaussian and local phase treatment remain. Full target three-mode covariance differs between branches. | On0095 covariance prevents most shape-zero regression but still loses to baseline. These are not identity-validation or full-parent marginalization results. [R2](https://github.com/misko/leo-tracker-reduxredux/blob/dad19ba5ef74744d8234ccb4d461bac8444663aa/reports/2026_10_25_ds24_new_family_uncertainty/README.md). |
| Latest fast transfer/synthetic/receiver controls | Four chronological one-owner proposals; known-label artificial-position simulation; direct same-family/same-RF cross-RX differences. | Transfer improves2/worsens2, one arm loses29 accepted IDs; correct-label stochastic errors reach1.09 km; receiver mean gain0.585 Hz is small and timing-support dependent. None establishes a new accepted identity. [Completed wave](https://github.com/misko/leo-tracker-reduxredux/blob/dad19ba5ef74744d8234ccb4d461bac8444663aa/reports/2026_10_25_ds24_fast_identifiability/README.md). |

The soft-identity RF loss includes a changed identity prior/KL cost: a uniform
candidate prior charges even a concentrated incumbent identity. Its negative
gain against a hard, already-conditioned reference is not a common-prior
identity likelihood ratio or proof that the hard original label is true.
The independent algebra/gate audits passed; this is a scope/interpretation
limit, not a demonstrated implementation error.

The source paths inspected are
`tools/ds23_soft_predictive_identity.py` (`identity_bound`, `attach_soft_identities`),
`probe_ds23_soft_predictive_identity.py`, `refine_ds23_soft_predictive_identity.py`,
`audit_ds23_soft_predictive_identity.py`,
`ds23_new_family_prediction.py` (`wrapped_curve_score`, `joint_prediction`,
`attach_new_families`, `new_gates`), `probe_ds23_linear_family_groups.py`,
`confirm_ds23_new_family_prediction.py`, `ds23_nonlinear_phase_integral.py`,
`probe_ds23_nonlinear_phase_integral.py`, `audit_ds23_nonlinear_phase_integral.py`
and `probe_ds23_marginal_evidence.py`, all under the repository's `tools/`.
The grouped source is also published as an exact [source snapshot](https://github.com/misko/leo-tracker-reduxredux/blob/dad19ba5ef74744d8234ccb4d461bac8444663aa/reports/2026_10_22_ds23_dbg01_iteration_007/source/tools/ds23_new_family_prediction.py).
[Evidence provenance](evidence/provenance.json) records original paths and hashes
for the local soft/phase receipts, rather than implying an absent public report.

## 1. Challenge the four fast nominees before a new position policy

Keep0010/0011/0012/0013, including both regressions; this is an explanatory
panel, not an unseen sample. Freeze original native IDs, radio posterior source,
both saved baseline/diagnostic positions and both c arms. Compare the archived
nominee against at most seven causal alternatives from the existing catalogue
screen, plus the same normalized unresolved-curve/clutter null. Candidate pools
are proposals, not a proof that omitted catalogue alternatives have zero mass.
Use the same allowed alias hypotheses/prior for every candidate and marginalize
or penalize them symmetrically. Forcing the incumbent alias on all alternatives
would repeat the old soft model's restriction.

Use the R2 direct-phase treatment and physical uncertainty unchanged, including
old/new predictive cross-covariance and full quadratic/determinant/normalization.
Score the identical complete observation vector. First do only fixed-position
RF comparisons: at most4scans×2positions×2arms×8candidates=128 candidate contexts,
plus nulls and a declared common alias budget. Limit preparation/execution to
10 minutes, two workers/BLAS1. No new geographic selector or automatic association
threshold follows. A lower target loss at a new position is not identity truth.

Where metadata establishes another complete receiver/channel owner not used in
the discovery source or parent calibration, select using one owner and predict
the other with shared uncertainty. Do not nominate that witness by closeness to
the chosen satellite, and do not split one source into random points. If no
independent owner exists, report that fact and retain unresolved status; do not
replace missing evidence with a larger posterior weight. A later at-most-four
paired position-fit diagnostic is justified only by a specific RF contradiction
this test exposes. Record original accepted-ID preservation separately from
likelihood ownership, especially the already observed0011 failure.

The current [identity review](../identity/FINDINGS.md) supplies a concrete0013
lead: four raw owners/189 IDs under60108, all RX1. Their conditional cross-owner
gain is useful, but it neither supplies cross-receiver independence nor compares
competing families with calibrated clutter. Challenge that positive witness
alongside the other three nominees; do not select it because its RF gain looks
attractive.

This differs from old active-family soft identities and from repeating the
full410 grouped policy: it challenges the present one-owner proposals, includes
alias/null alternatives, and asks whether another owner actually falsifies them.

## 2. Isolate fast-model information loss using existing synthetic draws

The known-label fast panel leaves a concrete gap: all nuisances were drawn
together. Reuse its eight noisy realizations, sites, seeds, per-ID Gaussian
noise and Gamma draws. Add only two controls: zero the generating orbital
phase/shape deviations while keeping radio/noise draws; zero generating
radio/smooth deviations while keeping orbital/noise draws. Keep inference
priors, candidate labels, powers, masks, bounds, start and budgets unchanged.
This needs at most32 new fits (2controls×8realizations×2c), under a10-minute
global cap with two workers. It changes synthetic truth to isolate interactions;
it does not grant the estimator true nuisance values or license a real-data
prior change. Earlier oracle information calculations answer a different question.

Report paired artificial-position errors, displacement direction, parent phase
and Gamma behavior, gates and fixed-reference truth-versus-fit score components.
Do not select a real policy from whichever synthetic intervention helps.
If phase-related interactions dominate, a subsequent small coupled integral is
worth considering. Otherwise prioritize the implicated measurement/radio model.

Full parent nonlinear phase marginalization has **not** been established by the
reviewed evidence. However, a generic local dense slice or Gaussian-phase
importance correction is already tested. A new numerical pilot must add a
specific omitted term: joint phase/precision uncertainty, phase-dependent shape
design, or fast-specific alternative modes outside the old local proposal.
Freeze the same bounded/unbounded prior law on both approximation sides and
include any conditioning normalizer. R2 conditioning and the fast generator
change the original Student law; comparing them blindly with clipped/unbounded
parent VI cannot identify a pure integration error. Use at most two fast
contexts, a few fixed RF-selected position probes, independent seeds/rules and
explicit effective-sample/convergence checks. If it fails, publish numerical
nonqualification rather than increasing to another millions-of-draw campaign.

The association/selection stage remains a further distinct missing control:
the present simulator fixes labels/masks/powers. Testing it needs a consistent
synthetic causal candidate bank and clutter/unused observation universe, then
the actual selection code. Merely perturbing labels after selection or rerunning
soft weights is not end-to-end closure. IQ-level GLRT-peak bias needs a different
simulator and is not tested by a native-CFO path simulation. None is full SBC
without posterior-rank sampling and a matching generative law.

## 3. Allocate existing-source effort to additional geometry, then verify it

Inventory existing candidate ownership/time support first. A new channel seeing
the same satellite can help receiver diagnosis but shares that satellite's
phase/orbit error; another physical point, fitted polynomial sample or derived
cross-RX contrast is not a new independent position measurement. The40-degree
feed angle is not a bearing constraint. The direct contrast loses common Doppler
and cannot be added independently to its original measurements.

For the first four metadata-eligible scans, use the same archived candidate
pool and reconstruction budget for two allocators: point-count/length versus
expected increase in weak-direction information after projection of existing
receiver, phase and orbit uncertainties. Require native-ID nonoverlap and
compare the conservative result across both c arms. Expected Schur information
is conditional on identity and local geometry: use it to allocate work, not to
accept a satellite or score raw residual likelihoods. Favor genuinely different
satellite gradients and observations connecting poorly supported time intervals.

Limit each allocator to one source per scan; even when choices differ this is
at most16 matched-arm fits. Recheck actual information, complete old accepted-ID
ledgers, original gates and geographic outcomes only after RF sealing. Report
zero eligible witnesses if the corpus lacks them, without relaxing support or
turning an owner-only curve into calibrated orbital evidence. All24 DS24 scans
remain development. An exposure ledger must establish any genuinely untouched
recording/session block before it can serve as validation; none is assumed here.

Do not repeat unchanged soft identities, grouped full410 recovery, blanket
phase narrowing, Gaussian log-volume removal, generic multistart, broad receiver
flexibility, density-only movement selection or a GPS-chosen family blacklist.
The missing evidence is discriminating ownership and geometry, calibrated model
behavior under the actual selection stage, and identifiable omitted coupling—not
another increase in nominal point coverage.
