# Whole-scan prediction from curvature-fitted positions

This experiment tests whether the fixed shared-curvature prototype transfers
to scans excluded from fitting. Each of the nine eight-scan panels is split
first-four/last-four, then reversed, giving eighteen directed comparisons.
Targets never estimate location, grouping or timing. This is a common-model
test of fitted-position transfer, not the full curvature posterior predictive.

**Result: modest positive transfer, with dataset variation.** Among 16
qualified pairs, geographic error improves in 10 and whole-target prediction
improves in 10; both improve in 8. Sub-km coverage rises from 2/16 to 3/16.
Two optimizer failures remain excluded and are not replaced. This supports
another bounded test, not broad sub-km performance or production promotion.

| Dataset | Qualified pairs | Geographic wins | Target-score wins | Aggregate target log-score gain | Sub-km baseline → curvature |
|---|---:|---:|---:|---:|---:|
| DS7 | 5/6 | 2/5 | 2/5 | −13.110 | 0 → 0 |
| DS8 | 5/6 | 3/5 | 3/5 | +177.168 | 1 → 1 |
| DS9 | 6/6 | 5/6 | 5/6 | +166.906 | 1 → 2 |
| Total | 16/18 | 10/16 | 10/16 | +330.965 | 2 → 3 |

Positive target gain favors the curvature-fitted position under the common
q020 likelihood. These are natural-log units, not metres. Matched qualified
median geographic errors are DS7 2,568→2,574 m, DS8 2,474→1,834 m, and DS9
2,331→2,101 m. Overall median error changes only 2,470→2,417 m. Source
interleaved held scores improve in all 16 qualified pairs, illustrating why
they alone are a weaker criterion.

![Qualified whole-scan comparisons](holdout.png)

One new sub-km source fit is DS9 late, first-four direction: 1,174→779 m.
The already-sub-km DS9 middle first-four fit improves 697→171 m, while the
DS8 early first-four fit worsens 530→597 m. These are exposed-reference local
results, not independent demonstrations of absolute accuracy. The total
target gain includes a large +152.916 contribution from DS8 late first-four;
the aggregate is not evidence that every scan or dataset benefits.

Next, retain the fixed prior and test curvature on the longer source pools,
then evaluate their excluded scans against the same center and N8-mixture
controls used earlier. Keep the mixed DS7 result and optimizer failures visible;
do not tune the prior from these target outcomes.

## Frozen comparison

The baseline is the previous source-only q020 fit chosen from three training
starts. It is reused rather than rerun, with source-session identity, numerical
fit gates and training-score replay checked. The curvature model is initialized
at that same fit and uses the fixed 0.1 Hz/s² prior from the prior prototype.
No target or reference score tunes its width or chooses a start.

Source grouping requires the same candidate, exact RF and both receivers,
at least eight training points spanning ten seconds, and baseline training
joint candidate/signal probability >=0.5. The curvature time basis removes
only the training intercept/linear projection and is fixed during fitting.
No target grouping is constructed.

Both locations are evaluated under the **same original full-track q020 target
likelihood**. Each target's common unknown time offset is integrated uniformly
over [−5,+5] s. This avoids granting target-specific fitted timing or curvature
flexibility to one arm. It deliberately does not test whether a new curvature
prior improves target likelihood at a fixed location; the question is whether
the source-fitted location generalizes better under a common measurement model.

Paired geographic errors use the inherited exposed unsurveyed reference.
Source conditional interleaved held scores are also retained, but cannot
substitute for whole-target evidence. Reverse-direction pairs share a panel
and are not independent trials. These are explored data, not a blind new site.

## Evidence and checks

The [protocol](PROTOCOL.md) precedes execution. Each raw result includes source
and target session IDs, fit diagnostics, source held scores, per-target timing
integrals and source hashes. Target integration replays the scalar likelihood
to 1e-7 and compares 16/32 nodes per timing-bank interval to a 0.01 log-score
gate. Only failed integrals receive 64/128-node refinement; original values
remain in the result. Shared-curvature integration is audited at 128/256 nodes.

The [summary](summary.json) and [full table](TABLE.md) report every directed
split. Summarization verifies disjoint source/target sessions, input/code
hashes, target order and score sums. Failed or unqualified pairs remain in
the failure list and are excluded from qualified aggregates. Workers are
bounded to 180 seconds each, with at most three concurrent workers.

All 18 subprocesses returned zero and produced evidence, but DS7 middle
reverse and DS8 early reverse fits reported optimizer `ABNORMAL` status.
Their gradients were small and other checks passed; the frozen success gate
still marks both unqualified. Raw outputs and numerical errors are retained
in the full table, while qualified aggregates omit both arms of each pair.

All 144 whole-target integrals qualified. Two integrals required the
predeclared refinement; their original results remain embedded. Maximum final
timing quadrature discrepancy was 0.005178 log units, and maximum scalar replay
error was 1.82e−11. Summed numerical runtime was 748.5 seconds; the longest
worker took 80.3 seconds. The three reused curvature tests and Ruff passed.

The underlying curvature-model tests cover training-basis isolation, shared
product integration, zero-width baseline recovery and gradients. Runtime
checks test real-corpus scalar/derivative/quadrature consistency. This report
adds no production component or new RF collection.

## Limits and reproduction

Retained banks are site-conditioned, and UTC/orbit/candidate truth is not
independently established. Local warm-start fitting and an exposed reference
limit geographic claims. Results apply to four-scan source fits; they do not
directly validate the earlier eight- or twenty-four-scan positions.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_curvature_scan_holdout/batch.py
OPENBLAS_NUM_THREADS=1 .venv/bin/python reports/2026_09_29_curvature_scan_holdout/summarize.py
uv run --no-project --with matplotlib python reports/2026_09_29_curvature_scan_holdout/plot.py
```

Artifacts use exclusive creation: reproduce in a fresh archived-run context
instead of overwriting this run. These are local research artifacts.
