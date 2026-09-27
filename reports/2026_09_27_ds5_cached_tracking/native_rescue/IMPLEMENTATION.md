# Same-RX rescue implementation

`native_rescue_detector.py` implements the visit-level policy in `DESIGN.md`.
It wraps one unchanged `NativeTradeoffDetector` and the same
`NativeGuidedBoundary` engine.  The public API is:

```python
detector = SameRxRescueDetector(primary, guarded_engine)
result = detector.process(
    raw_ci16,
    (rx0_cache_key, rx1_cache_key),
    start_counter=visit_start_counter,
    visit_index=visit_index,
    force_discovery=False,
)
```

`raw_ci16` has shape `(rate * 120 // 1000, 2, 2)` with sample, receiver,
I/Q axes.  Keys must be ordered RX0 then RX1 and describe the same visit.  The
wrapper calls the primary controller exactly once per receiver, so the primary
snapshot remains compatible with `NativeTradeoffDetector.snapshot()` and
`restore()`.  A raised integrity exception restores the pre-visit snapshot.
Accepted rescue evidence does not enter primary tracking state.

`RescueVisitDecision.decisions` contains two `NativeTradeoffDecision` values
and can be passed to existing assessment code receiver by receiver.  A rescued
receiver uses route `rescue_probe0_probe2`; every untouched or failed receiver
keeps its exact primary decision.  `primary_decisions` preserves both original
objects.  The result separately records acquisition count, retained candidate
count, Python score count, probe-zero native calls, probe-two native calls, and
one `RescueEvent` per examined rank.  The copied per-receiver native work counts
remain the primary controller's counts.  Use `total_scoring_count` or the
separate rescue fields for complete work accounting.

The acquisition keeps the scanner's ten-candidate, five-sample, 10 kHz
separation configuration.  Candidates are consumed in returned rank order.
Each Python margin-positive candidate is measured by the guarded native API on
probe zero.  A passing seed is then transported with the exact 750 Hz phase
formula and measured on probe two using the original Python scoring and
physical CFO hypotheses.  Both native observations must pass status, support,
bounds, fractional and margin checks; each must remain within 2 microseconds
and 8 kHz of the Python hypothesis, and the two native points must meet the same
mutual identity gates.  The pair contains only measured `NativeEvidence`.

This is still a raw-score rescue path.  Python `conditioned_glrt64_score` means
conditioned on the supplied epoch/CFO; it is not the native blind search's tone
nuisance fit.  Native guided scoring also omits that blind nuisance stage.
Constructed negative and mirrored-RX controls therefore remain necessary before
recorded development IQ.  The earlier 76/79 proposal ceiling and 18--22x cost
model are neither measured recovery nor a speed claim for this implementation.

Component tests cover receiver selection, preservation of native positives,
rank order, the ten-candidate configuration, distinct scoring/physical CFOs,
both native measurements, per-point and mutual identity gates, physical frame
transport at both rates, call counts, state delegation, transactional rollback,
input bounds and caller-IQ immutability.  No saved IQ is opened by these tests.
