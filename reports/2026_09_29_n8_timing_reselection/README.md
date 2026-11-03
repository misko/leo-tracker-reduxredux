# All nine existing eight-scan fits pass the timing re-selection check unchanged

The fixed one-round timing re-selection rule changes **zero of 72 scan timings**
across DS7/DS8/DS9 early, middle and late eight-scan panels. All nine geographic
locations and training scores remain exactly unchanged. The original endpoints
are retained; no joint refit or target recomputation is triggered.

| Dataset | Panels checked | Scan timings checked | Changes | Higher-scoring endpoint |
|---|---:|---:|---:|---:|
| DS7 | 3 | 24 | 0 | 0 |
| DS8 | 3 | 24 | 0 | 0 |
| DS9 | 3 | 24 | 0 | 0 |

This is evidence of stability under the tested timing-grid check, not proof
of global optimization. An untested continuous timing mode or different joint
geographic mode can still exist. The 41-node grid is finite and the banks
remain conditioned on the original geographic region.

## Method and validation

The [protocol](PROTOCOL.md) freezes all nine panels and reuses the previous
rule unchanged. At each source-only six-start endpoint, compare every scan's
current continuous timing score to all original grid nodes at fixed geography.
Change only for a training-score improvement above 1e−7, preserving the existing
continuous timing on ties. A qualified source-score improvement above 1e−6
would trigger old/new evaluation on all five excluded targets; none occurs.

Source session membership and all original training likelihoods replay. Every
chosen grid maximum replays against the scalar model within 1e−7, and summed
per-scan timing gains match the joint score difference within 1e−7. Source
bindings verify, Ruff passes, and all three workers exit zero within their
300-second caps. The selector is imported from the preceding tested implementation;
its tests cover continuous-optimum preservation and score-increasing switching.

Per-panel source checkpoints and final results preserve all nine cases. The
[summary](summary.json) independently verifies that no timing, score, location
or target evaluation changed. No reference or target outcome selects a panel
or parameter, and no failed result is omitted.

## Consequence for priorities

The preceding [N24 timing re-selection experiment](../2026_09_29_timing_reselection/README.md)
recovered inferior distant-start solutions. That is a useful optimizer guard.
This extension finds no further gain in the already selected short-window fits,
so the remaining kilometre-scale reference errors cannot be credited to an
improvement from this particular timing-grid pass.

Keep the pass as a research diagnostic, without promising a general accuracy
gain or integrating it into production based only on the recovery examples.
Further search changes should demonstrate a higher qualified training solution
and independent predictive behavior. The current evidence still favors treating
source-model disagreement, measurement calibration and reference provenance as
separate unresolved issues rather than expecting this check to resolve them.

No new location fit, RF collection, production edit or publication occurred.
Artifacts are local. Reproduce with `batch.py prepare` and `batch.py run` under
NumPy/SciPy in a fresh output context; preserve the per-panel checkpoints.
