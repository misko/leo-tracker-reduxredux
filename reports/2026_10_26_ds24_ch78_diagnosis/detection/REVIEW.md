# Independent read-only review of inference branches

Reviewed `common.py`, `residual/run.py`, `matched/run.py`, and
`test_diagnosis.py`, following the reused heldout covariance, frozen-precision,
predictive geometry and fit helpers. No source edits or numerical jobs were run
for this review. Existing detection evidence and its verification manifest were
left unchanged. This review does not certify numerical results or convergence.

## Actionable findings

1. **Input-seal scope is incomplete.** `common.py:75` hashes selected case files
   and loaded Python sources, but `recovery.context()` also reads
   `causal_prior/<case>/previous.tle`, `receipt.json`, `previous_receipt.json`,
   `causal_phase_history/<case>.json`, and `<case>_forecast.json` beneath the
   shared source inventory. Those files are not included in the manifest loop.
   Internal digest and causality checks bind some of them together but do not
   bind that whole dependency set to this experiment's original freeze. Preserve
   a supplementary read-only dependency manifest and qualify its later timestamp;
   do not silently imply those inputs were covered by the original freeze.

2. **Completion does not certify crossed-score numerical convergence.**
   `residual/run.py:74` saves phase refresh changes but omits the crossed
   posterior's `final_log_precision_change` and unclipped phase magnitude.
   `hierarchical_bound()` can exhaust its finite iteration budget and return
   convergence metadata without raising. Training `cold_fit()` saves the final
   precision change; that does not establish convergence for every fixed-position
   crossed score. The declared advancement screen requires all fits and scores to
   converge. Do not treat `status=complete` as satisfying it. Also inspect the
   position fit's `stopped` field: `iteration_budget` is not convergence, while
   `no_accepted_damped_step` alone is a stopping condition rather than a formal
   stationarity proof. If the predictive screen already fails, retain the negative
   result with this limitation instead of expanding the experiment.

## Checks that appear sound

- Whole-family and family/RX holdouts remove retained curved factors through the
  keep mask and matching explicit predictive factors through component ownership.
  The actual-data redaction test mutates both track-value sets and checks posterior
  coefficient/noise precision invariance; held/training IDs are checked disjoint
  again during scoring. Remaining family evidence on the other RX is intentional
  for RX-specific masks. Full-data assignment/noise/prior exposure remains a
  limitation, as the protocol already states.
- Covariance orientation is correct: for precision `A=L L.T`,
  `solve_triangular(L, F.T).T` equals `F L^-T`, whose product with its transpose is
  `F A^-1 F.T`. Receiver/channel marginals retain shared covariance and are
  correctly labeled nonadditive. Added predictive tracks receive shared 300-Hz
  track-bias uncertainty rather than independent per-point biases. Position
  uncertainty is explicitly excluded, and Gaussian moment scoring is not claimed
  as the exact Student/Gamma density.
- The matched masks preserve original ownership and select equal counts within
  family/RX/20-second bins. Empty overlap stays empty. Both c arms use the same
  masks. Predictive factors are removed in every matched comparison. The existing
  frozen Gaussian port checks same case/arm, coordinate labels/support/members,
  full prior width and fitted-c slot mapping. Exact noise/prior precision equality
  is asserted after fitting. This is properly a conditional mechanism control,
  because those packets and assignments came from the original full-data fit.
- Scientific interpretation should keep the protocol's limits: four chronological
  development cases, no independent location validation, repeated masks are not
  independent scans, channel count matching does not equalize illumination or RF
  quality, and a better predictive/fit score alone does not prove better position.

The root agent was notified promptly of the two findings while its sealed jobs
were running. No inference branch was modified by this reviewer.
