# DS26 / DS27: causal TLE age and phase recovery variants

The broadest tested recovery improves DS26 mean fitted-c error from **1,301.1 to 1,295.5 metres**, adds **941 native points in 18 scans**, and increases GLRT coverage from **71.1115% to 71.2562%**. The 90th-percentile error remains **2,424.2 metres**. DS27 remains unchanged: **619.1 metres** mean fitted-c error and **78.2519%** coverage. These are modest cohort gains, with useful individual recoveries and some regressions.

**Recommendation:** retain the current production default. Develop the 72-hour catalogue as a guarded recovery fallback, and reserve the wider phase search for independently supported unmatched curves. The mild calendar-age penalty has no demonstrated benefit here: it changes no winning identity, trial selection, or final decision. Before promotion, rerank competing satellites under the same physical likelihood used for position and replay the complete regional association pipeline. The present experiment does not establish a route to 500-metre cohort error.

The matched 48-hour/±15-second extra-search control already recovers **563 points** and improves mean fitted-c error by **2.7 metres**. Expanding the age window then adds a net **207 points** and **0.7 metres** of mean improvement. Expanding phase adds a net **171 points** and **2.1 metres** more. Wider search sometimes selects a different fragment, so these are differences between policies, not a guaranteed nested set of recoveries. The contribution from merely continuing the incumbent optimizer is negligible; `summary.csv` separates it from the candidate-versus-matched-control effect.

Useful individual examples, with fitted-c position error:

| Scan | Change needed | Before → after | Added points | Satellite |
|---|---|---:|---:|---:|
| DS26-0058 | 72-hour catalogue; TLE age 50.22 h | 1.115 → **0.977 km** | 70 | 64938 |
| DS26-0130 | Wider phase; fitted phase −28.63 s, TLE age only 20.70 h | 1.917 → **1.628 km** | 73 | 58632 |
| DS26-0022 | Additional search at original age/phase bounds | 2.034 → **1.837 km** | 34 | 62959 |
| DS26-0287 | Additional search at original age/phase bounds | 0.689 → **0.440 km** | 32 | 63035 |
| DS26-0046 | 72-hour catalogue; TLE age 52.13 h | 1.209 → **1.261 km** | 51 | 59435 |
| DS26-0142 | Additional search at original age/phase bounds | 0.290 → **0.389 km** | 86 | 58675 |

The last two rows are qualified recoveries that worsen evaluation accuracy. Under the broad variant, eight DS26 scans improve by more than 25 m and two worsen by more than 25 m in fitted-c; the corresponding c=0 counts are nine and four. The broad c=0 mean improves by 5.0 m, while its median worsens slightly. More associated points therefore need a separate localization-utility check.

For this particular penalty, the maximum extra score cost between 48 and 72 hours is only `2 log(2) = 1.386`, versus the required identity margin of 10. A much stronger penalty would be a different, untested assumption. The current results support improving candidate completeness and physical-model validation before introducing an arbitrary stronger preference for younger TLEs.

Evaluated 161 usable fast scans (148 DS26, 13 DS27), with 13 pre-existing unavailable scans retained in the accounting. The search covered 451 residual fragments: at most three per scan, at least 20 native points and 15 seconds, ranked by duration before fitting.

This is a bounded conditional recovery experiment on the current ALGO05 outputs, not a fresh GLRT extraction or cold-start full-pipeline rerun. Every variant starts from the same saved RF-derived position within the existing 25 × 25 km region. Evaluation GPS is used only by `render.py`, after sealing inference decisions. No production changes were made.

## Variants

- **48 h / ±15 s:** matched additional-search control with the original catalogue age and phase bounds.
- **72 h / ±15 s:** admit the latest causal TLE per satellite out to 72 hours. Both collection and element epoch must precede the scan and satisfy the age window.
- **72 h / ±30 s:** extend the phase search and private predictive propagation grid. Existing calibration equations and priors remain unchanged.
- **72 h / ±30 s + age penalty:** add `2 log(2) max(age_h − 48, 0) / 24` to the candidate score. This halves prior odds per additional day. It is a sensitivity test, not evidence that older satellites are less likely to transmit.

## Position and coverage

| Dataset | Arm | Variant | Mean km | Median km | P90 km | >1 km | GLRT associated | Added points |
|---|---|---|---:|---:|---:|---:|---:|---:|
| DS26 | c0 | Current baseline | 1.318 | 0.991 | 2.419 | 72 | 71.111% | 0 |
| DS26 | c0 | 48 h / ±15 s | 1.316 | 0.991 | 2.419 | 72 | 71.198% | 563 |
| DS26 | c0 | 72 h / ±15 s | 1.315 | 0.991 | 2.419 | 72 | 71.230% | 770 |
| DS26 | c0 | 72 h / ±30 s | 1.313 | 0.993 | 2.419 | 73 | 71.256% | 941 |
| DS26 | c0 | 72 h / ±30 s + age penalty | 1.313 | 0.993 | 2.419 | 73 | 71.256% | 941 |
| DS26 | fitted_c | Current baseline | 1.301 | 0.994 | 2.424 | 73 | 71.111% | 0 |
| DS26 | fitted_c | 48 h / ±15 s | 1.298 | 0.994 | 2.424 | 73 | 71.198% | 563 |
| DS26 | fitted_c | 72 h / ±15 s | 1.298 | 0.983 | 2.424 | 72 | 71.230% | 770 |
| DS26 | fitted_c | 72 h / ±30 s | 1.296 | 0.983 | 2.424 | 72 | 71.256% | 941 |
| DS26 | fitted_c | 72 h / ±30 s + age penalty | 1.296 | 0.983 | 2.424 | 72 | 71.256% | 941 |
| DS27 | c0 | Current baseline | 0.638 | 0.643 | 0.921 | 1 | 78.252% | 0 |
| DS27 | c0 | 48 h / ±15 s | 0.638 | 0.643 | 0.921 | 1 | 78.252% | 0 |
| DS27 | c0 | 72 h / ±15 s | 0.638 | 0.643 | 0.921 | 1 | 78.252% | 0 |
| DS27 | c0 | 72 h / ±30 s | 0.638 | 0.643 | 0.921 | 1 | 78.252% | 0 |
| DS27 | c0 | 72 h / ±30 s + age penalty | 0.638 | 0.643 | 0.921 | 1 | 78.252% | 0 |
| DS27 | fitted_c | Current baseline | 0.619 | 0.641 | 0.869 | 1 | 78.252% | 0 |
| DS27 | fitted_c | 48 h / ±15 s | 0.619 | 0.641 | 0.869 | 1 | 78.252% | 0 |
| DS27 | fitted_c | 72 h / ±15 s | 0.619 | 0.641 | 0.869 | 1 | 78.252% | 0 |
| DS27 | fitted_c | 72 h / ±30 s | 0.619 | 0.641 | 0.869 | 1 | 78.252% | 0 |
| DS27 | fitted_c | 72 h / ±30 s + age penalty | 0.619 | 0.641 | 0.869 | 1 | 78.252% | 0 |

![Position distributions](position_error_distributions.png)

![Paired error changes](paired_error_changes.png)

![Changed scans](changed_scan_errors.png)

![Association coverage](association_coverage.png)

## Exact scope and safeguards

The incumbent core and selected additive likelihoods are replayed, including accepted graph fragments and joint new-family mixtures. Published owners are preserved; incidental unpublished membership extensions are recorded and never counted as recovered points.

Screening searches the complete eligible STARLINK catalogue at each saved RF endpoint, with a coarse phase grid and up to three nominations per policy, arm, and training partition. Finalists from the two c arms are unioned within each partition; full-data nominations are not inserted into training-only shortlists. Exact full-point screening integrates a 300 Hz constant, 0.5 Hz/s rate, 5-second phase prior and whole-track alias. The normalized likelihood includes the nuisance-volume penalty.

Three seeded random 12-second block holds with two-second guards test candidate stability. Every partition in both c arms must agree, with score margin at least 10, RMS at most 450 Hz, admissible bias/rate, interior phase, visibility and the existing residual-noise screen. These checks are conditional on the frozen graph and incumbent RF solution; they do not prove globally unique satellite identity.

At most one new-family fragment is proposed per scan and policy, chosen by the minimum RF identity margin, then point count. Existing-family extensions are unchanged. The final position uses the physical orbital-uncertainty model, not the screening offset/rate model. Causal history priors and the existing unavailable-history fallback are preserved. A separate age-dependent widening of nuisance priors is not tested here.

The matched position control and candidate have three phase-refresh rounds, up to 100 evaluations per round, and identical 25 × 25 km bounds. A second new family is integrated jointly with an incumbent new family so receiver covariance is counted once. The declared exact-mixture cap is two families; a third is left unchanged. Target data never recalibrate the receiver mean at a fixed position.

A proposal must pass both c arms, preserve incumbent owners, pass exact-orbit incumbent replay, all family residual gates, phase convergence, phase-boundary checks and local quadrature score/gradient checks. The numerical pilot showed that 0.1-second integration was insufficient; the cohort position trials use 0.05 seconds and verify 0.025/0.0125 seconds. Rejected or failed-closed proposals retain the published baseline. Candidate-versus-matched-control errors are separate in `trials.csv`; better frequency fit is not treated as better localization.

These are research qualifications, not promotion-ready production decisions. Identity ranking uses the normalized offset/rate screening model; the full physical likelihood is evaluated for the selected identity, not exhaustively reranked across every competitor. Shortlisting, the three-fragment cap, the two-family integration cap and local continuation all limit the conclusions. None of the results establishes global uniqueness or demonstrates that the full 25 × 25 km cold-start search improves.

## Reproduction and evidence

Run with the modern numerical worktree `/srv/bulk/leo-dev/fast-algo02-production-v1`, its `.venv/bin/python`, `PYTHONPATH=src:tools`, and `OPENBLAS_NUM_THREADS=1`. `common.py` freezes the cohort; `export_catalogues.py` uses the read-only archive adapter; `screen.py` replays and nominates; `position.py` performs matched trials; `audit_replay.py` verifies full incumbent likelihoods; `render.py` seals inference and introduces evaluation GPS.

Validation: four new screening tests, seven inherited normalized-evidence tests, and nine physical-likelihood / phase-resolution tests passed. The operations test collection could not run in the numerical environment because its shared test configuration imports the unavailable `alembic` package. The executed catalogue search separately checks epoch and collection causality for every exported element. All 241,233 overlapping nominal elements match the 72-hour export byte for byte; existing satellite predictions are not silently swapped.

Machine-readable results: `summary.csv`, `position-errors.csv`, `screen-summary.csv`, `trials.csv`, `controls.csv`, `decisions.csv`, and `inference-seal.json`. Per-scan raw evidence and catalogue provenance are retained under `inputs/`, `preflight/`, `catalogues/`, `screen/`, and `position/`. Initial infrastructure retries and the archived coarse numerical pilot are retained separately.

[All physical-trial curves and residuals](CURVES.md). The overview below shows the eight longest trial sources, selected by native point count, not position error.

![Physical candidate curves and residuals](position_trial_curves.png)
