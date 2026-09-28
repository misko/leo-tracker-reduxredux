# Sparse multi-frame coarse proposal review

The proposed shape is coherent as an explicitly approximate detector: use a
cheap multi-frame coarse proposal, retain a deterministic 32-center inventory,
recompute the existing full 16-frame, 12-symbol FP32 coarse statistic at each
center and its local epoch neighborhood, then send at most the usual eight
repaired candidates through unchanged fine, conditioned, verification, and
GLRT stages.  The repair is valuable because every emitted candidate begins
from the qualified full statistic.  It does not make the search exact.

## Why it is approximate

The full coarse statistic is the average of magnitudes after per-symbol/frame
normalization.  A proposal that omits frames, symbols, epochs, or CFO work
changes both its ranking surface and its support pattern.  No algebra turns a
sparse-frame magnitude average into the full 16-frame result.  A true full
candidate can be absent from the 32 centers, and its full score is then never
computed.

`±2` repair covers center refinement and immediate local-maximum comparison,
but it is not enough to certify the existing epoch-separation rule: retained
peaks suppress same/near-CFO alternatives at circular distance below five.
An un-repaired cell at distance three or four can change final NMS even when
the center and its two neighbors are repaired.  Endpoint behavior needs the
same care: local maxima use linear edges while peak separation is circular.
Do not wrap a linear endpoint repair merely because NMS is circular.

There is no usable global score-error bound for the proposal.  Thus a 32-center
cut and `±2` repair must be reported as a new detector with measured recovery,
not as a guarded exact optimization.  The only exact fallback is the complete
existing full coarse grid for that window.

## Model and numerical risks

- Preserve the current all-rate geometry: 16 rounded frame offsets; 12 anchor
  symbols; 12 internal CFO lanes (11 public rows); and tap counts 11, 22, 33,
  and 44 at 2.5, 5, 7.5, and 10 MS/s.  Proposal frame starts must use the
  same rounded offsets as repair, especially at 7.5 MS/s.
- A sparse frame count must carry its own support count.  It cannot compare a
  sum, a differently normalized average, or an incomplete terminal frame with
  the repaired full-support score.  At partial-window boundaries, repair must
  invoke the present `coarse_fp32_cell` behavior and retain its exact support
  semantics.
- All-zero input must retain the baseline zero grid/no-positive-basin outcome;
  do not turn a flat proposal plateau into arbitrary centers.  Test zero,
  subnormal/local-low-energy, and short inputs at every rate.
- Deterministic selection needs the baseline score, absolute-CFO, epoch, and
  discovery-order tie rules.  Plateaus, equal centers across CFO signs, peak
  epoch zero/final epoch, and candidates straddling sparse-grid cells must be
  explicit tests.  Do not let an unordered top-K container determine results.
- The 32 centers must be chosen before final eight-NMS with an auditable
  definition.  Count centers discarded by capacity, centers whose repair
  changes rank, repaired cells, and full-grid fallbacks.  A fixed 32 may be
  insufficient in noise-rich or multi-signal windows; that insufficiency is a
  scientific miss, not an implementation anomaly.

## Qualification sequence

1. **Exact full-budget control.**  Add a mode that executes the original full
   coarse grid and routes its complete grid through the new center/repair and
   final-selection plumbing without sparse pruning.  Require exact full
   candidate-object parity with the selected baseline on deterministic ties,
   zero/partial/all-rate fixtures, and the initial saved-IQ screen.  This is
   required before interpreting a sparse mismatch as a model tradeoff.
2. **First 64 configured screen variants.**  Compare baseline and sparse
   results per receiver/probe, recording every 32-center inventory, repaired
   epoch/CFO cell, support count, final eight inventory, and fallback.  Score
   individual positive candidates and positive 20-ms windows; confirmation
   existence alone is insufficient.
3. **Frozen host704 gate.**  Run the same individual-positive-hit and
   positive-window matching used by the existing host704 paired audit.  Report
   per-rate denominators, recovered and added hits/windows, center-overflow
   misses, and fallback fraction.  Keep full candidate-object mismatch counts
   as a diagnostic, but do not expect equality for the sparse detector.

The prior DS7 progressive experiment is the relevant warning: at 2.5 MS/s,
four windows with two candidates retained 90.6% of confirmations but only
22.9% of individual positive hypotheses.  Sparse work can preserve a
detection-oriented outcome while discarding the evidence needed for complete
scientific output.  Acceptance for this proposal should therefore be stated
in individual hits and positive windows, with the full-budget parity control
separating plumbing regressions from intentional approximation.
