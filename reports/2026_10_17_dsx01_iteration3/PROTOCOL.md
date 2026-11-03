# DSX01 iteration 3: position-independent recovery experiments

This iteration follows the saved 15-window and timing diagnostic. That previous
turn made progress by producing checked recovery tables, timing distributions
and input/output bindings; it did not change a localization model. The active
goal remains recovery of more of the same 15 GLRT windows with a method that
generalizes to new positions.

No station-reference coordinates enter initialization, candidate selection,
priors or algorithm selection. Configured-reference distance is an output
diagnostic only. No fixed satellite IDs, target-window exceptions, new RF
recording, production change or remote push is part of this experiment.
The previous frozen dataset, model, iteration 2 and recovery snapshot artifacts
remain unchanged. No per-window best-of combination will be presented as a
single method.

All association comparisons retain the original 693 window observations,
15 windows and 20,084 complete-scan observations. Report new and lost original
assignments separately. Better conditional frequency likelihood or a narrower
timing distribution does not by itself establish better position or identity.
The ≥80% net-missing-restored grouping is descriptive rather than a new
preregistered success gate. Full-data warm experiments remain development
results, not predictive validation.

Parallel investigations:

1. `timing/`: change only relative timing prior sigma from 2 s to 1 or 0.5 s.
   Keep common sigma 3 s, all physical bounds, observation sets and candidate
   order unchanged. Exact profiles and continuation are matched at 1,000
   complete-objective calls / 120 s per fit, with projection counts separate.
   Both fitted-c and c=0 are required. Reuse sigma-2 receipts only when their
   complete original protocol and hash bindings match. Compare NLL and prior
   penalty separately because total objectives differ between prior arms.
2. `calibration/`: bind actual earlier same-radio fast recording receipts and
   learn or initialize band differences causally. Donor acquisition must finish
   before target acquisition starts and its analysis must already be complete.
   Do not copy a donor position. Learn current calibration using only declared
   training rows. Preserve missing-donor coverage and both temporal directions.
   Perturbing held CFO must leave seeds, training objective and proposals
   unchanged. Correct the previous permanently-zero band-contrast restriction.
3. `support/`: explain displaced assignments with actual residuals, visibility,
   mixture odds, calibration and timing changes. Implement a generic repair
   only when this evidence supports it. Do not lock original labels as truth
   or lower classification thresholds to manufacture recovery.

An additional bounded archive sensitivity in `ephemeris/` holds satellite IDs,
order, warm start and fixed band calibration identical while replacing only
the original elements with the latest causally collected Space-Track snapshot.
Both c arms use the same 1,000-call / 120 s profile allowance. S02–S04 already
use the same Space-Track digest; they are identity controls, not new independent
provider trials. Only S01 and S05 require new numerical fits. TLE collection
time and matched-satellite element-epoch age are recorded separately.

All paths are research orchestration using the pinned scientific runtime
documented in the previous iteration. QNAP and hardware are not written.
Component-owned numerical tests precede actual-data evaluation. No sealed
scientific fixtures are changed to accommodate failures.
