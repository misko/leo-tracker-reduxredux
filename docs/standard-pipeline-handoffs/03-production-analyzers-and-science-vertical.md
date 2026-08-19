# Handoff 03 — Production analyzers and complete science vertical

## Goal

Wire every pure Standard-v2 component into the typed DAG so each receiver path
runs independently through quality, power, waterfall, schedule, pilot search,
trajectory fitting, corrected replay and terminal report; then reduce exact path
reports into radio and paired reports.

## Starting point

- Pure implementations live beneath `src/leo/analysis/standard/` and the GLRT64
  trajectory modules.
- Additive v2 power and numerical-waterfall contracts preserve v1 wires.
- Source-bound membership wrappers bind reusable scientific bytes to exact path
  input and predecessor closures without embedding run IDs in reusable payloads.
- Pure reducers are implemented and candidate-only.
- The production Standard registry/codecs and complete PostgreSQL worker vertical
  are not implemented.
- The protected trial-132 full-twice test is defined. A historical run produced
  byte-identical 93,667,521-byte outputs, but the corrected code still needs an
  independently reviewed detailed golden and a clean rerun.

## Required implementation

1. Define one analyzer per frozen node and exact `StageSpec`/`ProductSpec` output
   inventory. The 10 path stages remain frozen; feedback publishes feedback and
   trajectory-table products from one job.
2. Analyzers consume only the declared durable predecessors. No analyzer may use
   the legacy whole-dwell coordinator or silently recompute another stage.
3. Quality/power/waterfall/pilot/feedback receive the exact verified one-RX
   reader. Schedule, bank, report, presentation and reducers receive no IQ.
4. Store reusable numerical payloads separately from run-owned source-binding
   membership metadata. Validate the membership closure before downstream use.
5. Add strict bounded JSON codecs for every product, with finite-value, count,
   byte and schema checks.
6. Register the exact Standard-v2 graph in production while preserving explicit
   suppression for QUALIFICATION/CALIBRATION/ACCEPTANCE captures.
7. Produce deterministic scientific JSON. Render PNG only from authoritative
   JSON with a pinned deterministic renderer, or render interactively in the
   browser; never let nondeterministic PNG bytes break job idempotence.

## Required numerical tests

- Frozen trial-132 one-second oracle.
- Zero, noise, tone, same-IQ rolled control, wrong-sign correction, unrelated
  correction, zero-gain correction and sample substitution.
- Gaps, tails, partial dwell, clipping, NaN/Inf, CFO boundary/alias ambiguity.
- Parallel, crossing, intermittent, merge/split and duplicate tracks.
- Every method returns bounded multi-candidate evidence; absence after truncation
  never becomes a miss.
- Linear/quadratic/cubic coefficient, residual, selection and corrected GLRT64
  metric checks.
- Product substitution from another path/run/release fails even when geometry,
  RX number and schedule are identical.
- Radio/paired truth tables cover complete/no-result/partial/insufficient/failed,
  declared 1-RX completeness, missing declared RX, truncation and timing overlap.

## Full real-IQ gate

1. Run the protected four-path analysis once with a retained local output root.
2. Extract the four path summaries; review every family/candidate/control/replay
   count, trajectory ID, degree, coefficient, RMS and corrected margin.
3. Update the golden only through an explicit reviewed receipt; never on test
   failure alone.
4. Rerun twice from raw IQ in isolated processes.
5. Require identical canonical structure and digests, plus the frozen floating
   tolerances. Preserve both output artifacts and hashes in the ledger.

## Completion evidence

- Real-PG full 43-job Standard run with 47 frozen scientific products plus exact
  run-owned membership lineage (update the count explicitly if reviewed contract
  changes require it).
- Exact ProductDependency closure for every product.
- Clean full four-path-twice pytest exit.
- Reviewed golden receipt and retained output SHA-256 values.
- Component, negative-control, concurrency and independent review PASS.
