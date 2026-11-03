# Fixed shared curvature on 24-scan pools

This is the direct combination of the strongest pooled q020 estimates and
the fixed 0.1 Hz/s² shared-curvature prototype. It reuses exactly 24 source
scans and five previously frozen outside-pool targets per dataset. No prior
width, source membership or target selection changes were made after results.

**Decision: retain the pooled q020 baseline.** Curvature modestly improves
reference-relative error on DS7/DS8 and worsens DS9, but has no consistent
outside-scan predictive advantage. All fits qualify and all three locations
remain sub-km relative to the inherited reference. That is not independent
proof of general accuracy.

| Dataset | Baseline error | Curvature error | Outside score vs baseline | Outside score vs center | Outside score vs N8 mixture |
|---|---:|---:|---:|---:|---:|
| DS7 | 387.52 m | 340.52 m | −12.023 | +32.428 | −199.085 |
| DS8 | 389.83 m | 372.54 m | +16.912 | −23.770 | −131.222 |
| DS9 | 107.23 m | 134.89 m | −2.352 | +54.170 | −112.149 |

Positive score differences favor curvature. Scores are natural-log units,
not metres. Curvature beats the baseline on 6/15 individual targets (2 DS7,
3 DS8, 1 DS9), with only +2.537 total score gain. It beats the N8 mixture on
2/15 targets and loses in every dataset aggregate, totaling −442.456. The
mixture is broader; its advantage is not evidence that any individual N8
point estimate is geographically better.

![Geographic and outside-prediction comparison](comparison.png)

The new source interleaved held-score gains are +1720.625, +1092.182 and
+1402.941 for DS7/DS8/DS9. Those substantial gains do not carry through to a
consistent outside-pool location advantage. This repeats the warning from
earlier models: explaining residual structure is different from obtaining
a more reliable position. Movement from the baseline is 137, 145 and 28 m.

The correction remains useful research evidence, especially for shorter
source fits, but increasing its width based on these outcomes is unwarranted.
The next direction should address predictive uncertainty and independent
constraints, while preserving the strong long-span baseline. In particular,
separate signal-model calibration from a surveyed geographic/timing reference:
the current exposed-site results cannot supply both fitting guidance and
independent accuracy validation. No pooled-model promotion is claimed.

## Comparison

Each curvature fit starts at the qualified N24 baseline chosen in scan_budget.
The original training score is replayed on the same source documents before
fitting. Groups are determined only from that source fit: recording, physical
candidate and exact RF; both receivers must be represented, and each member
requires eight training points spanning ten seconds and joint training
candidate/signal probability >=0.5. Curvature removes the training linear
projection and uses the same fixed basis for full and training likelihoods.
The common coefficient has the fixed truncated Gaussian prior used previously.

At each new location, the complete-track original q020 likelihood scores the
same five outside-pool scans selected earlier by timestamp order statistics.
One shared timing offset per target is integrated uniformly over [−5,+5] s.
Target location, timing and curvature are not fitted. Three sealed comparison
arms are reused: original N24 position, configured center, and equal mixture
of three N8 positions. N8 densities are averaged per target, not their log
scores; sums are sums of per-scan predictive scores, not a joint shared-location
mixture across all targets.

This tests location transfer under a common measurement model. It is not the
full posterior predictive of a curvature model on the targets. Source
interleaved held scores are reported separately because earlier work showed
they can improve without more reliable geography.

## Evidence and checks

See [protocol](PROTOCOL.md), [full table](TABLE.md), [summary](summary.json), and
per-dataset JSON for fitted parameters, frozen source IDs, group counts,
optimization and integration gates, per-target scores and input/code hashes.
The summarizer verifies identical source/target configuration, target exclusion
from fitting, and identity of the baseline positions used by the earlier
comparison arms. Source and prior artifact hashes are checked before fitting.

Optimizer success, boundary, gradient and finite-difference checks retain the
previous thresholds. Curvature integration is audited at 128/256 nodes. Target
timing integration replays the scalar oracle and compares 16/32 nodes per
bank interval, with only failed integrals refined at 64/128; originals are
preserved. Failures remain visible and do not count as qualified improvements.
Each of three concurrent dataset workers has a 180-second wall cap.

All three workers exited successfully in 82.6–88.2 seconds. All optimizer,
derivative, curvature-quadrature and target-timing gates passed. There were no
target timing refinements or failed cases. The source-model and target-scoring
code are unchanged from their tested predecessors; source training scores
and artifact hashes replayed successfully. Ruff passed for the new runner,
summary and plot. Detailed numerical bounds remain in the raw fit outputs.

## Limits

The targets have been examined in previous research and are not a fresh blind
holdout. The geographic reference is exposed and unsurveyed. The configured
center already lies about 809 m from that reference. Source pools span roughly
8–13 hours, not 24 consecutive short-latency scans. Candidate banks are
site-conditioned and UTC/orbit truth is not independently calibrated. Neither
good reference-relative error nor a predictive-score improvement alone proves
general sub-km accuracy. No RF or production changes were made.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python reports/2026_09_29_curvature_n24/batch.py
python3 reports/2026_09_29_curvature_n24/summarize.py
```

Outputs use exclusive creation. Reproduce in a fresh archived-run context
instead of overwriting the completed artifacts. These reports are local.
