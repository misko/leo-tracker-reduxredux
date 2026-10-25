# DS24 fast-scan identifiability and transfer controls

Started 2026-10-25 after publication of commit
`7c11ca70240bbb029c2cb070992f3baa2979f288`.

The preceding goal turn made progress: it completed the two-case controlled
new-family uncertainty test, independently checked the likelihood and numerical
results, and published the full review and reproducible artifacts. It did not
establish a new algorithm or improve both examples over their baselines.

## Objective

Identify a general, evidence-supported route to better fast-scan localization.
Keep the full objective intact: a mechanism result, more associated points, or
a lower frequency loss alone does not establish better position performance.

## Parallel work

1. **Transfer — SOL xhigh, plan_evidence.** Reconstruct complete original
   accepted-ID ledgers, including postfit extensions, for the archived provisional
   candidates. Select at most four distinct eligible scans chronologically,
   excluding the two development cases 0095/0087. No fresh nomination or geographic
   selection. Test the existing predictive physical-prior role only after original
   ownership, construction, numerical and validity checks pass. At most 80 fixed
   branch evaluations and eight matched-c position fits; preserve unsupported
   target identity status and exact operational baseline.
2. **Synthetic — SOL xhigh, plan_validation.** Extend existing conditional
   simulations to two chronologically selected fast scans, excluding 0095/0087.
   Freeze artificial regional positions and random seeds. Compare exact noiseless
   forward-model and stochastic controls with matching c arms; add actual
   association selection only if the available entrypoint fits the bounded scope.
   At most 24 fits. Explicitly distinguish fixed-label inference, source selection,
   and a complete generative model. No formal SBC claim without rank testing.
3. **Receiver contrasts — SOL xhigh, next_validation.** Measure simultaneous
   same-family, preferably same-band RX differences from existing data. Carry
   interpolation uncertainty and source-constant ambiguities. Test prediction of
   held families with negative controls. No localization fits or new association
   search; contrasts alone cannot supply absolute position.

## Common controls

- Independent study subdirectories; preserve prior reports and unrelated work.
- Existing archived corpus only; QNAP read-only; no RF collection or raw IQ work.
- Original 25 x 25 km search box centered at 37.906, -122.545.
- Actual evaluation GPS is used only after RF output freezing, never selection.
- Observations, candidates, other priors and budgets match between c=0 and fitted
  c. Synthetic true c is zero for both inference arms.
- Two workers and one BLAS/OMP/MKL thread per branch. Science execution capped at
  20 minutes per branch and 180 seconds per fit, with no retries or rescue.
- Freeze branch definitions before outcomes; retain every failure and exclusion.
- Use existing meaningful numerical checks and component-owned tests. Avoid
  redundant audit infrastructure or replaying completed fits for convenience.
- Report frequency behavior, ownership/association status and position separately.

## Decisions and publication

Each branch produces sources, tests, exact input/result references, a compact
machine-readable result and informative figures. Root independently reviews the
scientific claim and relevant outputs. Publish an integrated MD report to remote
main under the standing user instruction, including negative outcomes. Reuse
existing immutable artifacts; add only necessary new evidence.

An improvement on previously examined same-site data is not a new-location
validation. No automatic ALGO promotion or broad campaign follows this pilot.
Use the results to select the next bounded test, and stop repeating explanations
that the evidence contradicts.
