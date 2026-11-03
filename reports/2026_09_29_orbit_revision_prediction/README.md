# Exact orbital replay supports retaining fresher GP inputs

**The reconstructed orbital baseline reproduces all 3,983 selected cases exactly
in position, velocity and fitted frequency.** Replacing its elements with causal
24-hour-older snapshots then worsens held frequency-shape residuals on most
changed cases in DS7, DS8 and DS9. Keep the current baseline orbital selection.
This is a completed orbital-input sensitivity assay, not a new geographic fit
or validation of absolute orbit accuracy.

| Dataset | Changed 24-hour cases | Older elements improve / worsen | Median paired held-error change | Median training-centered revision RMS |
|---|---:|---:|---:|---:|
| DS7 | 1,337 | 207 / 1,130 | +343.50 Hz | 584.49 Hz |
| DS8 | 1,277 | 224 / 1,049 | +239.07 Hz | 413.79 Hz |
| DS9 | 794 | 158 / 636 | +216.49 Hz | 365.22 Hz |
| Total | 3,408 | 589 / 2,815 | +260.11 Hz | 455.85 Hz |

Positive **error change** means worse here; machine-readable summaries use the
opposite sign, positive **gain** for improvement. Four changed cases tie within
the 1e-6-Hz reporting tolerance. All 3,975 cases with a 24-hour record propagate
successfully; eight missing records retain unchanged baseline errors. Unchanged
element cases also remain in the full-population result. No target is dropped
because its older orbit predicts poorly.

## Exact baseline matters

The earlier [inventory](../2026_09_29_orbit_revision_support/README.md) compared
older snapshots to the latest whole Space-Track snapshot. The numerical banks
actually choose newest-per-object elements among the pinned latest snapshots
from both providers. This replay reconstructs that exact policy from each bank
manifest, including epoch, collection-time and digest tie-breaking.

Consequently, changed-element counts against the actual baseline are **3,408**
at 24 hours and **1,082** at six hours, rather than the inventory's whole-snapshot
counts of 3,402 and 876. Those earlier counts remain correct for their comparator.
Provider-name differences do not constitute independent orbit truth.

Each selected candidate is propagated at exactly the two saved timing-grid nodes
bracketing the inherited fitted recording time, then interpolated exactly as
the original model. Maximum differences against the saved bank and residuals
are **0 km, 0 km/s and 0 Hz** over all 3,983 cases. Thus the measured revision
effects are not caused by changing propagation, observation times, interpolation,
coordinate conventions or position parameters in this replay.

## Six-hour control and interpretation

| Dataset | Changed six-hour cases | Older improves / worsens | Median held-error change |
|---|---:|---:|---:|
| DS7 | 662 | 253 / 402 | +0.609 Hz |
| DS8 | 420 | 118 / 160 | 0 Hz |
| DS9 | 0 | — | — |

Remaining changed cases tie within tolerance. Changed textual elements need
not materially change propagated frequency over a short interval. DS9 has no
changed six-hour cases, so its unchanged predictions supply an identity check,
not a successful correction or an accuracy result.

The larger 24-hour revisions show that orbital inputs materially affect the
frequency shapes used for positioning. They also favor the existing fresher
elements in this conditional comparison. However, locations, times and candidate
assignments were inherited from baseline training fits; the experiment tests
their conditional held predictions, not fully refitted models on a new site.
It cannot prove that residual bias is primarily orbital, estimate the current
orbit error, or calibrate a prior from older/newer disagreement. All cases are
dependent assignments in 72 previously examined scans.

In particular, selecting older elements or extrapolating a correction because
it happens to move a position toward the exposed reference would be unjustified.
No such selection or geographic scoring occurred.

## Method, accounting and verification

The [protocol](PROTOCOL.md) preceded execution. Candidate, location, recording
time, sample times and train/held masks stay fixed. Only the element record is
replaced. Recenter each residual on its own training mean, then evaluate its
median absolute held residual. This removes stationary frequency offsets using
training data in every arm. All values use canonical 11.2-GHz frequency units.
Revision slopes and training-centered RMS are retained per case as sensitivity
descriptors, not calibrated errors.

Three tests pass: radial Doppler/interpolation recovery, constant-offset
invariance and revision-sign accounting. Every observation, manifest and state
bank is SHA-256 checked; archive bytes pass the read-only reader's digest check.
Result bindings include the runner, protocol, parent inputs, model helpers and
installed archive/parser/propagator module digests. The summarizer verifies
3,983 unique case keys, input bindings, unchanged-element identity and explicit
missing/failed fallback accounting. Ruff lint and formatting pass.

The initial full replay completed in 35.8 seconds. An import-format correction
was followed by a full replay to bind the final source. The experiment uses one
numerical thread, one recording bank at a time and a 120-second cap per replay.
No RF collection, provider download, archive write, production edit or geographic
optimization occurred. The installed release is needed for its public propagation
and archive ports; `sudo -n` supplies archive read access and output remains a
workspace-owned file.

```bash
OPENBLAS_NUM_THREADS=1 uv run --no-project --with numpy --with scipy python -m unittest discover -s reports/2026_09_29_orbit_revision_prediction -p 'test_*.py'
sudo -n env OPENBLAS_NUM_THREADS=1 timeout 120 /opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python reports/2026_09_29_orbit_revision_prediction/run.py > reports/2026_09_29_orbit_revision_prediction/results.json
.venv/bin/python reports/2026_09_29_orbit_revision_prediction/summarize.py
```

## Next decision

Retain the exact fresh baseline. The orbital propagation and element-choice
replay now provides a checked foundation for a physically constrained sensitivity
model. Before any orbit-nuisance fit, test whether an external revision direction
explains the shared residual structure while preserving position information;
do not replace the failed free-slope approach with an equally unconstrained
orbit parameterization. Independent precise ephemerides or verified identities
would be stronger constraints, but neither is supplied by this comparison.
Reliable short-window sub-km accuracy remains unresolved.
