# Repository tool map

Resolve paths against `git rev-parse --show-toplevel`. Check local `AGENTS.md` and the actual checkout revision. Some research utilities below exist only in newer production/research revisions; discover them with `rg --files tools src/leo reports` and inspect source before running. Do not silently change branches or import a second checkout into a supposedly reproducible run. Record the chosen tool revision.

There is no claim that one existing command implements this entire skill. Reuse numerical analyzers and narrow ports; add only a bounded adapter when a required comparison is missing. Any implementation change must include component-owned tests. Avoid concrete storage/network imports in analyzers; load observations/TLEs in an adapter and pass numerical inputs.

## Polynomial and residual numerical helpers

- `src/leo/analysis/research/robust_polynomial_order.py`: `polynomial_orders` compares degrees 1–4 on a frozen unwrapped branch with a Gaussian/clutter model and parameter penalty. Leave-one-out seeds initialize fits; every final score uses all observations. Responsibilities are not satellite-identity probabilities. Its default noise/clutter scales and independent-sample penalty need checking against the recording and covariance policy. Degree zero, alternative aliases, and join searches require separate handling.
- `src/leo/analysis/research/polynomial_satellite_diagnostics.py`: `batch_noise_screen` computes mean, slope, quadratic gain, step, and lag-one checks; `orbit_shape_lower_bounds` gives free offset/affine diagnostic minima; `feasible_order` ranks after gates. Read the deployed revision for exact floors and thresholds. The affine lower bound is not calibrated hardware or accepted identity evidence.
- `tools/validate_polynomial_tracklet_predictions.py`: inspect its input schema and options for polynomial prediction validation. Do not assume it performs catalogue discovery or joint radio calibration.

## Later research utilities, when present

- `tools/debug_fast_graph_unassociated.py`: replays a sealed production model and screens residual sources. Its saved-context and membership helpers are version-specific. Verify ownership against the actual published artifact; reconstructed proposals are not necessarily final owners. A screening nomination is not an accepted association.
- `tools/probe_high_channels_post_tle.py`: example read-only later-TLE diagnostic using `leo.operations.tle_archive.TleArchiveReader` and `leo.sky.propagation`. The inspected version uses the **latest archive collection within 48 hours**, restricts IDs to the causal bank, carries scan-specific target logic, and falls back to causal elements for missing IDs. It therefore does **not** implement this skill's first-post-epoch/full-catalogue/missing-data protocol unchanged. Reuse the archive/propagation APIs, not those experimental selection assumptions.
- `tools/predictive_new_family.py`, `tools/annotate_track_predictively.py`, and `tools/audit_shared_predictive_inclusion.py`: starting points for independent nomination and shared-family inclusion. Inspect partition semantics, physical priors, target selection, and exact ownership replay. Do not assume their CLI or artifacts are interchangeable across releases.
- `tools/analyze_algo05_residuals.py` and `tools/diagnose_algo05_residuals.py`: examples of ranking residual sources and rendering retained nominations. The inspected diagnostic has DS26/DS27 paths and case-specific artifact assumptions. It explains already saved results; it does not prove a fresh exhaustive search was run.
- `src/leo/analysis/research/block_predictive_evidence.py`: numerical predictive evidence for frozen linear-Gaussian hypotheses, including missing opportunities and covariance. Its prequential/calendar-block semantics differ from randomized whole-group validation. Use only with a declared, matching protocol. Its normalized masses are explicitly uncalibrated and conditional on the supplied hypothesis inventory.

Prefer archive readers and element-set parsing/propagation ports from the checked-out version. Record full element hashes and availability provenance. Do not access reference repositories as runtime dependencies.

## Efficient execution

1. Locate a sealed run and reproduce its saved objective/predictions before changing models.
2. Load native observations once; cache propagated orbit states keyed by element hash, time grid, and propagation version. Cache observer-dependent projections separately with position/RF keys.
3. Batch candidate calculations where the implementation supports it. Keep per-candidate fitting budgets comparable and retain a coverage ledger.
4. Start with one bounded source and finalists. Expand to independent supporting families only as needed to identify shared corrections. Dataset-wide evaluation is a separate user-requested task.
5. Render from saved numerical outputs. Run appropriate component tests if code changed, then validate counts, units, provenance, and plot legends. Do not initiate a long collection campaign to complete a debug report.

Example requests:

- `$find-glrt-association DS27 scan 0020 RX1 CH4 T005; compare causal and first later TLE, show the best alternatives and why the step gate fails.`
- `$find-glrt-association this run's longest residual CH7/CH8 curve; audit joins and compare receiver drift against a shared satellite correction.`
- `$find-glrt-association this suspected match; test whether it remains unique across nuisance models and regional position starts, without using evaluation GPS to choose it.`
