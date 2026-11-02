# Independent final review

The RF experiment and its receipt audit pass. The result is a bounded,
retrospective development comparison of a fixed revision proxy. It does not
establish calibrated orbit errors or independent predictive performance.

The authoritative `final_audit.json` binds the complete 205-recording ledger to
result SHA `360bd3c179aedc997d50016eb986312677e5ff615f8f4aa84fc81e6e5bd56d2f`
and protocol SHA
`0942b133ae4733d5ab8847b0ae8e84aaf309ab8f89f3357c4c2351f079c2d793`.
All 402 frozen source hashes remain unchanged. The audit independently checks
prior nominations, causal source receipts, deterministic disjoint age matching,
physical coefficient transport, covariance arithmetic, paired qualification and
exact comparator fallbacks. All observations, ownership and initial references
match across the c=0 and fitted-c arms.

All 30 supported candidates started once. Their 60 arm fits completed in the
single 218.963-second run; 56 arms qualified. The primary Age3 policy adopts all
five three-pair cases. The exploratory Age2 policy adopts 27 cases, comprising
those five and 22 two-pair cases. Three cases retain selected A: DS26-0024 fails
the physical/ownership gates in both arms; DS26-0219 fails fitted-c stationarity;
DS28-0003 fails c=0 physical/ownership gates. The remaining 175 recordings retain
their exact selected-A controls. There are no orphan RF cells or checkpoint-only
cells and no additional fit attempts.

The model changes only three existing target-family physical columns. Historical
revisions are resolved at their historical newer epochs in physical mean motion,
inclination and RAAN, then expressed in the current declared SDs. The mean stays
zero. Fixed `.5 I + .5 E[aaᵀ]` shrinkage, variance floor 1 and ceiling 16 preserve
a proper prior; two or three dependent revisions do not calibrate a full error
distribution. Age3 and Age2 reuse identical endpoints and differ only by their
prospective minimum pair count. RF objective differences are diagnostic.

Two independent checks support the implementation. Before fitting, the
FRSH-0001 covariance receipt stayed exactly identical when RF values, RF methods,
tracks, saved endpoints/owners and GPS-like fields were poisoned. After fitting,
the authorized two-arm FRSH-0001 replay took 3.325 seconds without optimization or
phase refresh: objectives, conditional nuisance coefficients, residual
decomposition and physical coefficient maps reproduced exactly. The target
Cholesky feature map differs by at most `2.14e-14`, and every unrelated feature
column is identical. These are conditional base nuisance diagnostics; separately
scored ancillary phase-mixture families are not a joint posterior.

The causal archive has one shared-snapshot connected group. The 25 strictly
issued auxiliary forecasts cannot provide independent validation. Their proper
Gaussian score includes covariance volume but covers only the represented three
coefficients; omitted state error is reported separately. Neither this archive
diagnostic nor the four selected old-B geographic examples changed the frozen
RF model, thresholds, support tiers or candidate list. The old-B panel remains
posthoc; its missing mode and receiver posteriors were not reconstructed.

The audit was completed before new geographic evaluation. Position accuracy,
including the matched c ablation and immutable ALGO07/A/B controls, must determine
the practical conclusion separately from in-sample RF fit. The previous C
projection is not rethresholded or claimed to demonstrate successful risk
control. A finite-prior sensitivity study remains a proposed diagnostic.
