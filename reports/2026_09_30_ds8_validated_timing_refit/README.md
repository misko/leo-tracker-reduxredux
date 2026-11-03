# Joint refit from validated timing modes: neither arm qualifies

The independently validated timing alternatives do not yet yield a qualified joint geographic fit. The unchanged optimizer reports success but fails the existing gradient limit. A separately declared objective-centering control lowers the gradient substantially but terminates `ABNORMAL`. Both results remain unqualified; no new reference-distance or convergence claim is made.

## Controlled comparison

Both arms start at the original qualified rank-start N40 location, replacing only the three preselected scan timings with their best qualified scalar solutions. The remaining 37 timings and all forty scans, observations, candidate banks, likelihood terms and qualification thresholds stay unchanged. Initial training and held scores replay from the prior fit plus recorded per-scan changes to within 1e−7.

| Arm | Optimizer status | Maximum gradient | Gradient audit discrepancy | Training score | Qualification |
|---|---|---:|---:|---:|---|
| Original objective | Success: relative objective reduction | 0.0160832 | 0.00002453 | −423353.883935248 | Fail: gradient >0.01 |
| Subtract initial objective constant | `ABNORMAL` | 0.0006174 | 0.00001759 | −423353.883935176 | Fail: optimizer status |

Neither hits a parameter boundary. Both finish within their declared 180-second caps; neither is a timeout. Timing and qualification records are in [summary.json](summary.json) and [centered-summary.json](centered-summary.json). Raw vectors and complete optimizer outcomes are preserved in [result.json](result.json) and [centered-result.json](centered-result.json).

The centered arm starts from the exact same initial vector, not the failed endpoint. It changes only the additive objective constant, which changes the scale used by relative objective stopping. It preserves model derivatives, bounds, optimizer options and qualification gates. The two final absolute scores differ by approximately 7.24e−8, despite the different termination outcomes. This is evidence of numerical termination sensitivity, not evidence that either result should bypass the predeclared qualification gate.

## Interpretation

The original relative-objective stop can occur before the scientific gradient gate passes. Centering prevents that particular early stop here, but does not produce a successful optimizer termination. Thus objective centering alone is not a supported replacement, and the prior disagreement between qualified locations remains unresolved.

The previous corrected fit remains the strongest qualified N40 fit in this sequence, at 424.581 m from the supplied reference. Its training score (−423353.201939) also exceeds either new unqualified score. This does not certify its physical accuracy or global optimality.

The next numerical test should compare an independent joint optimizer against the original objective on a bounded synthetic problem and this exact frozen initialization, preserving the existing derivative and boundary requirements. Further repeated L-BFGS starts or relaxed success gates would not resolve the qualification issue. Any eventual numerical improvement must transfer to held recording groups at a fixed scan budget before being treated as a positioning method improvement.

## Evidence and verification

The [initial protocol](PROTOCOL.md) precedes the original run. The [centering protocol](CENTERED_PROTOCOL.md) was declared after its failure and before the control. A component-owned test confirms exact preservation of score differences and gradients on a quadratic with a large negative likelihood offset. The radio run restores the absolute score and verifies it against the unwrapped model to 1e−7. Source and cached-input hashes verify; all artifacts are bound by `evidence.sha256`.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_30_ds8_validated_timing_refit -p 'test_*.py'
python3 reports/2026_09_30_ds8_validated_timing_refit/summarize.py
python3 reports/2026_09_30_ds8_validated_timing_refit/summarize.py centered-result.json
cd reports/2026_09_30_ds8_validated_timing_refit
sha256sum -c evidence.sha256
```

This is exposed-data numerical diagnosis, not independent geographic validation. No RF collection, archive mutation, propagation, production change or remote publication occurred.
