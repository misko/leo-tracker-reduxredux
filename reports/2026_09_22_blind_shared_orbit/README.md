# Blind multi-scan position and shared satellite refinement

## Status

The bounded validation is sealed and negative. Nominal and shared estimates are
about 7,995 km and 7,978 km from the post-seal reference, and the shared arm's
held-out predictive sum is 12.005 lower than nominal. It does not produce a
useful receiver position or held-out improvement. In addition, its fitted
quartic Doppler approximation misses exact propagation by as much as 2.2524 Hz,
above the predeclared 0.2 Hz limit. The scientific qualification is therefore
**insufficient** even though both outer optimizers and the inner rate optimizer
converged. This remains research code; automatic scanner analysis is unchanged.

## Question and model

Can several scans jointly constrain one stationary receiver position more
effectively when repeated satellite candidates share an orbital correction?
The estimator first searches a declared geographic region using the full causal
Starlink catalogue. It then refines common receiver position and uncertain
satellite assignments, sharing one orbital phase-rate correction per NORAD
across all of that candidate's retained occurrences.

The region is a 14,484.096 km square centered at Denver (39.7392°, −104.9903°),
using the repository's azimuthal-equidistant map and fixed receiver altitude.
This is a geographic constraint, not a claim of prior-free inference. Known
receiver coordinates and site-selected satellite review lists are excluded
from fitting. Reference coordinates are read only by a separate evaluator after
the fit is sealed.

The catalogue snapshots and element epochs are causal to each archived capture,
and target truth does not enter the fit. The fixed phase-rate prior scale of
0.091766159 s/hour comes from the later September 21 formal research module and
is applied retrospectively to this September 7 cohort. This is therefore a
truth-free fit with causal orbital inputs, not a full historical deployment
simulation with every hyperparameter fixed before capture.

At each common position, a candidate's orbit-phase displacement is its shared
rate (seconds/hour) multiplied by that candidate's causal TLE age (hours).
The receive-time Earth rotation remains fixed. Five phase nodes support a
quartic interpolation of predicted Doppler in hertz, and the fitted predictions
are checked against exact propagation. This reuses the formal model's phase-node
structure; it is not a port of that model's AR(1), Student-t correlated
likelihood or state interpolation, and it cannot inherit the formal model's
328 m result. This experiment instead uses a pseudo-Huber IID composite mixture
with independent track offsets. Candidate identities remain a mixture with an
explicit unassigned component. The catalogue prior denominator remains the full
population even when local refinement retains a subset.

Nominal and shared-correction arms use matched observations and likelihood
settings. Each track still has a training-fitted constant frequency offset.
This implementation does not yet fit a common receiver oscillator drift or a
complete cross-dwell fragment-assignment graph. Mixture weights are model
weights, not calibrated identity probabilities.

## Predeclared saved-data cohort

Six scans were selected by ordinal coverage of the existing 24-scan September 7
research corpus, spanning approximately 7.6 hours. Raw RF tracklets were
reconstructed through current public scanner inputs without loading the old
report's satellite assignments. All exporter-eligible disjoint tracklets are
retained; the export accounts for conflicting or overlapping alternatives.

| Session | Tracklets | Observations | Role |
|---|---:|---:|---|
| `scan-hop-66cae29c39756be7` | 47 | 1,083 | Fit and within-track holdout |
| `scan-hop-fa8b9ec97ff14b97` | 44 | 959 | Fit and within-track holdout |
| `scan-hop-6c9417eeec67a616` | 47 | 1,186 | Transfer evaluation |
| `scan-hop-163ca5acea5cce6b` | 34 | 723 | Fit and within-track holdout |
| `scan-hop-d04702aa7553ee39` | 65 | 1,772 | Transfer evaluation |
| `scan-hop-7a31f1dfb82a20e3` | 80 | 2,130 | Fit and within-track holdout |
| **Total** | **317** | **7,853** | |

The four fit scans contain 205 tracklets and 4,895 observations. The first 60%
of each track provides fitting data; its final 40% is held out. The two transfer
scans do not choose position or shared orbit parameters. Any adaptation of
their identities or frequency offsets must be reported separately from frozen
prediction and use only their initial samples.

## Required interpretation checks

- Acquisition must account for the full eligible catalogue and all selected RF
  tracks, with causal snapshot and source digests.
- No held-out frequency or reference-coordinate error may select a spatial
  branch, candidate support, model setting, or shared correction.
- Nominal and shared arms must be compared on matched support and scored on
  held-out observations using their training-fitted parameters.
- Exact propagation must validate the model actually optimized, rather than a
  different approximation applied only after fitting.
- Truncated corrected candidate support and frozen nominal horizon masks must
  remain explicitly uncertified.
- A coarse regional search does not certify discovery of the global optimum.
  The September 7 report already demonstrated that coarse grids can miss the
  useful region. Unfinished search stages are reported rather than hidden.

## Sealed result

The chronological full-region acquisition, not the excluded randomized coarse
v1 attempt, seeded the fit. The runner used 205 fit tracklets with 4,895
observations and evaluated 112 transfer tracklets with 2,958 observations. It
reported no track exclusions. Runtime was 1,231.85 seconds and peak resident
memory was 384,680 KiB. Both bounded outer optimizers terminated successfully
after 115 total objective evaluations. The nominal arm disabled shared-rate
optimization as designed; the shared arm's inner optimizer converged.

| Quantity | Nominal position arm | Shared correction arm |
|---|---:|---:|
| Estimated latitude | 51.556252° | 51.891706° |
| Estimated longitude | −12.244228° | −12.116917° |
| Post-seal horizontal reference error | 7,994.7 km | 7,978.2 km |
| Selected-arm training objective | 21,478.833 | 20,544.384 |
| Held-out log predictive sum | −18,405.296 | −18,417.301 |
| Tracks with better held-out score | — | 115 / 205 |

At the selected shared position, the matched nominal and shared training
objectives were 21,770.967 and 20,544.384. The shared parameters improve that
training objective by 1,226.583, but their held-out predictive sum is 12.005
lower. The roughly 16.5 km reduction in reference error is conditional on two
estimates that are both almost 8,000 km wrong and does not establish useful
positioning. Reference coordinates were introduced only after the result seal.

The fit retained 254 candidate NORADs. Of these, 221 appeared in more than one
track's retained shortlist and 44 received weight at least 0.5 in more than one
track. These are diagnostics for uncalibrated composite weights, not confirmed
satellite identities. Several rates reach the configured ±0.25 s/hour bound,
which adds to the identifiability concern.

All 205 fit-track exact-replay audits ran, but the maximum approximation error
was 2.252432 Hz. This fails the 0.2 Hz requirement, so the runner's structurally
complete document is scientifically **insufficient**. The two transfer scans
used the frozen shared position and rates. Their nuisance-only scoring converged:
matched nominal and shared training objectives were 13,431.894 and 13,402.400,
and held-out log predictive sum was −12,805.987. All 112 transfer exact audits
completed with maximum error 0.018492 Hz. Transfer support remains explicitly
`uncertified-truncated-corrected-support`; transfer cannot rescue the failed fit
audit or the gross position error.

A frozen-selection post-seal audit recomputed exact propagation and refit only
each track's training-only constant offset. Offset centering did not remove the
failure: its maximum error was 2.404143 Hz. The worst candidate was NORAD 58111
at about −7.65 seconds of realized phase, but its frozen mixture weight was only
3.91×10⁻⁴². Replacing approximate predictions with exact predictions changed
the frozen-weight held-out total by only +0.031812; updating training-derived
weights changed it by +0.021521. The sealed approximate total was reproduced
exactly. Thus the audit failure is real but numerically too small in the mixture
score to explain the held-out gap or the wrong geographic mode.

The runner chooses the refinement basin using full-catalogue nominal training
evidence, then compares nominal and shared corrections conditionally within that
basin. The returned shared estimate is the lowest shared objective among the
branches actually evaluated, but the 1,000 km acquisition and one-basin local
search do not certify global shared-mode selection. Top-eight corrected support
and nominal-state horizon masks are also uncertified. This run gives negative
evidence for this formulation and search budget. It does not reject all
multi-scan models.

## Figures and reproducibility

The research estimator is implemented in
`src/leo/analysis/research/blind_shared_orbit.py`. The saved-data exporter,
chronological coarse acquisition, and sealed validator are respectively
`tools/research/export_uncapped_position_tracks.py`,
`tools/research/run_blind_shared_orbit_coarse.py`, and
`tools/research/validate_blind_shared_orbit.py`. The executed validator predates
a post-run provenance hardening patch, so the exact archived bytes and their
digest are authoritative for this result.

The final relevant test run passed **51 tests**, with Ruff clean. It covered the
new implementation, its reused numerical components, exporter, validator,
renderer, and post-seal audit:

```bash
.venv/bin/python -m pytest -q \
  tests/analysis/test_blind_shared_orbit.py \
  tests/analysis/test_orbit_identity_mixture.py \
  tests/analysis/test_formal_orbit.py \
  tests/tools/test_export_uncapped_position_tracks.py \
  tests/tools/test_validate_blind_shared_orbit.py \
  tests/tools/test_render_blind_shared_orbit.py \
  tests/tools/test_audit_blind_shared_orbit_exact.py
```

- [`heldout-predictive-comparison.png`](artifacts/heldout-predictive-comparison.png)
  compares matched per-track held-out scores.
- [`spatial-branch-evaluation.png`](artifacts/spatial-branch-evaluation.png)
  shows the evaluated search trace and post-seal reference; it is not a
  confidence region.
- [`rate-recurrence-exact-audit.png`](artifacts/rate-recurrence-exact-audit.png)
  shows recurrence and the exact-propagation audit distribution.
- [`summary.json`](artifacts/summary.json) is the rendered evaluation;
  [`sealed-result.json`](artifacts/sealed-result.json) is the source fit with
  seal `sha256:aa8e2918ae05c9b64703737e3af748fe0a6ee83ded2831f16c1af53d38eb689f`.
- [`postseal-exact-offset-audit.json`](artifacts/postseal-exact-offset-audit.json)
  is the frozen-selection exact audit with canonical receipt
  `sha256:60ee7765c1a3870d2a5aff5023e03a15ab21dbb9ee6a12fb44057a13a7e85fcf`.

Reproduce the truth-after-seal rendering with:

```bash
.venv/bin/python reports/2026_09_22_blind_shared_orbit/render_validation.py \
  --sealed-result reports/2026_09_22_blind_shared_orbit/artifacts/sealed-result.json \
  --coarse-result reports/2026_09_22_blind_shared_orbit/artifacts/coarse-full-region-1000km.json \
  --output-dir reports/2026_09_22_blind_shared_orbit/artifacts \
  --reference-latitude-deg 37.84903264307456 \
  --reference-longitude-deg -122.4856541910174
```

To rerun the fit with the current hardened validator, reconstruct the immutable
inputs under a scratch directory. The coarse configuration must retain its
executed filename because the validator binds it next to the coarse result:

```bash
mkdir -p /tmp/leo-shared-orbit-reproduction/shards \
  /tmp/leo-shared-orbit-reproduction/coarse
.venv/bin/python - <<'PY'
import gzip
from pathlib import Path

source = Path("reports/2026_09_22_blind_shared_orbit/evidence/input-shards")
target = Path("/tmp/leo-shared-orbit-reproduction/shards")
for path in source.glob("*.json.gz"):
    (target / path.name.removesuffix(".gz")).write_bytes(gzip.decompress(path.read_bytes()))
PY
cp reports/2026_09_22_blind_shared_orbit/artifacts/coarse-full-region-1000km.json \
  /tmp/leo-shared-orbit-reproduction/coarse/full-region-1000km.json
cp reports/2026_09_22_blind_shared_orbit/artifacts/coarse-configuration.json \
  /tmp/leo-shared-orbit-reproduction/coarse/configuration.json
.venv/bin/python tools/research/validate_blind_shared_orbit.py \
  --shards /tmp/leo-shared-orbit-reproduction/shards \
  --tle-root /var/lib/leo/tle \
  --coarse-result /tmp/leo-shared-orbit-reproduction/coarse/full-region-1000km.json \
  --output /tmp/leo-shared-orbit-reproduction/sealed-result.json
```

The causal TLE archive at `/var/lib/leo/tle` must contain the snapshot digests
listed in the input shards. This is a saved-corpus replay and makes no RF
collection request. With those shards extracted, replay the post-seal audit:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python tools/research/audit_blind_shared_orbit_exact.py \
  --sealed-result reports/2026_09_22_blind_shared_orbit/artifacts/sealed-result.json \
  --shards /tmp/leo-shared-orbit-reproduction/shards \
  --tle-root /var/lib/leo/tle \
  --output /tmp/leo-shared-orbit-reproduction/exact-audit.json
```

The current validator adds provenance and resource guards after the reported
run; it does not retroactively change the sealed result. The six compressed
exported shards and digest manifest are in
[`evidence/input-shards`](evidence/input-shards). Executed sources and hashes are
in [`evidence/executed`](evidence/executed). The exact executed validation runner
hash is `db65c87341c8d48264098698b5adcb590788c48ed0c681894f0e7a896091dc21`;
the repository runner was hardened only after this process exited. The process
had `OPENBLAS_NUM_THREADS`, `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, and
`NUMEXPR_NUM_THREADS` unset. Observed CPU use varied from about 1.0 to 4.30 CPUs
over snapshots and reached 47 threads; final aggregate CPU time was not retained.
These runtime facts do not change the scientific failure.

## Prior evidence

- [Blind regional acquisition across eight hours](../2026_09_07_blind_regional_doppler_positioning.md)
- [Uncertain identity refinement](../2026_09_21_identity_mixture_positioning.md)
- [Shared identity/orbit prototype and failed approximation audit](../2026_09_21_shared_identity_orbit.md)
- [Formal fixed-identity orbit model](../2026_09_21_formal_orbit_model.md)
