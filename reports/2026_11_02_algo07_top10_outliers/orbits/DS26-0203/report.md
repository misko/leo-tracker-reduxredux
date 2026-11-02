# DS26-0203: orbit and curve diagnostic

The catalogue search compares the saved ALGO06 composition at its own inferred positions. Per-track nuisance fits are diagnostic lower bounds; a clean fit does not establish unique identity. No localization gain or production recovery is claimed.

| Target | Incumbent | Regime | L3 winner / runner-up | Margin | RMS Hz | Phase s | Rate Hz/s | Noise gate |
|---|---:|---|---|---:|---:|---:|---:|---|
| 0: SCAN-RX1-CH8-T001-RF12690312500.000000 | 67935 | causal | 67935 / 59360 | 35.28 | 81.8 | -5.8 | 0.23 | True |
| 0: SCAN-RX1-CH8-T001-RF12690312500.000000 | 67935 | later | 67935 / 68062 | 440.28 | 75.7 | 0.3 | 0.04 | True |
| 1: SCAN-RX2-CH2-T001-RF11190312500.000000 | 63377 | causal | 63377 / 68256 | 3490.18 | 72.2 | -0.7 | 0.61 | False |
| 1: SCAN-RX2-CH2-T001-RF11190312500.000000 | 63377 | later | 63377 / 68256 | 4186.31 | 103.3 | 1.3 | -0.88 | False |
| 2: SCAN-RX2-CH1-T002-RF10940312500.000000 | None | causal | 64133 / 63466 | 6.28 | 50.7 | 4.0 | -0.33 | False |
| 2: SCAN-RX2-CH1-T002-RF10940312500.000000 | None | later | 64133 / 63466 | 11.41 | 42.0 | 3.8 | -0.26 | False |

Target 0 full graph selects degree 4 under descriptive independent-noise BIC; RMS 56.0 Hz; endpoint leverage [0.5357334710626952, 0.36748127503866657]. Irregular correlation limits this complexity score. Piece fits and excluded original endpoints are retained in `targets.json`.
![Orbit](target-0-orbit.png)
![Graph audit](target-0-graph-audit.png)
![Consecutive 20-second context](target-0-20s.png)
![Candidates](target-0-models.png)

Target 1 full graph selects degree 4 under descriptive independent-noise BIC; RMS 31.3 Hz; endpoint leverage [0.6098485973376695, 0.49750672644687777]. Irregular correlation limits this complexity score. Piece fits and excluded original endpoints are retained in `targets.json`.
![Orbit](target-1-orbit.png)
![Graph audit](target-1-graph-audit.png)
![Consecutive 20-second context](target-1-20s.png)
![Candidates](target-1-models.png)

Target 2 full graph selects degree 4 under descriptive independent-noise BIC; RMS 19.6 Hz; endpoint leverage [0.26491276193179303, 0.3356525253648527]. Irregular correlation limits this complexity score. Piece fits and excluded original endpoints are retained in `targets.json`.
![Orbit](target-2-orbit.png)
![Graph audit](target-2-graph-audit.png)
![Consecutive 20-second context](target-2-20s.png)
![Candidates](target-2-models.png)

Whole-family consistency uses all published native owners of each influential family and matched shortlists. A shared phase/rate must explain every track. Constants remain per-track diagnostic terms; no independent receiver correction is inferred from them.

These restricted-model RMS values are not published baseline residuals. The restricted search uses SGP4 phase plus constant/rate in place of the production marginalized satellite/orbit nuisance block. It omits the posterior physical orbital-mode corrections and any satellite-clock/family corrections in that full block. Published full-model residuals and exact production gates are recorded separately in the sibling diagnostics report. A restricted-model failure therefore does not prove the published association is wrong.

![Family 67935](family-67935.png)
causal family 67935: best shortlist identity 67935, RMS 56.7 Hz, shared phase -5.8 s, rate 0.08 Hz/s, all-track noise pass True.
later family 67935: best shortlist identity 67935, RMS 137.0 Hz, shared phase 0.4 s, rate 2.35 Hz/s, all-track noise pass False.

![Family 63377](family-63377.png)
causal family 63377: best shortlist identity 63377, RMS 66.3 Hz, shared phase -0.6 s, rate 0.85 Hz/s, all-track noise pass False.
later family 63377: best shortlist identity 63377, RMS 85.3 Hz, shared phase 1.2 s, rate -1.21 Hz/s, all-track noise pass False.

Paired causal/later swaps appear in `frozen_tle_swap.json`: the frozen-corrections comparison isolates the changed elements; later-refitted values are separately labeled. Missing later exact fits are null. Exact production gates and localization ablations live in the sibling diagnostics report. These per-track RMS/noise screens are not a replacement for those gates.

Search: every propagation-valid member of causal ≤72h and first-post-epoch ≤48h catalogues receives a coarse scan. Matched c arms share top-three model nominees plus the incumbent and exact phase budget. L1/L2 freeze the saved phase; L3/L4 profile ±30s with a 5s prior. L2 rate prior SD is 0.5 Hz/s and L4 is 2 Hz/s. Detailed inventories and hash provenance are in `run_manifest.json`, `tle_inventory.csv`, and search coverage files.

Remaining ambiguity: independent whole-group prediction and regional position stability have not been executed for these single-track catalogue fits. Per-track slopes cannot distinguish receiver clock, calibration and orbit errors. Next bounded discriminator: compare the same candidate over independent receivers/families using a shared correction, then replay exact ownership gates.

Reproduce from the worktree with `PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python reports/2026_11_02_algo07_top10_outliers/orbits/investigate.py CASE`, then the same invocation of `finish.py CASE`. Archive creation requires the existing read-only archive permission. No RF collection was performed.

Mechanism assessment (restricted model):

Paired later-element check: 0/6 fitted-c rows improve under frozen causal phase, constant and rate. Refitted later-RMS improvements re-estimate those corrections and therefore do not isolate an orbit improvement. Frozen-swap and refitted values are separately listed in `paired_tle_summary.csv`.

Family 67935: incumbent identity stable in restricted family shortlist; geometry or richer nuisance calibration remains the leading unresolved alternative. Same diagnostic identity 67935: later refit restricted-family RMS 56.7→137.0 Hz; this refits nuisance and is not the frozen-swap test. Confidence: model-sensitive / ambiguous; no independent identity validation. Next: Use the rival and incumbent with matched production physical orbital modes and all family receivers, fit on frozen whole time groups, test held groups, then exact ownership/gate replay.

Family 63377: incumbent identity stable in restricted family shortlist; geometry or richer nuisance calibration remains the leading unresolved alternative. Same diagnostic identity 63377: later refit restricted-family RMS 66.3→85.3 Hz; this refits nuisance and is not the frozen-swap test. Confidence: model-sensitive / ambiguous; no independent identity validation. Next: Use the rival and incumbent with matched production physical orbital modes and all family receivers, fit on frozen whole time groups, test held groups, then exact ownership/gate replay.

![Published full nuisance versus restricted model](target-0-published-vs-restricted.png)

![Published full nuisance versus restricted model](target-1-published-vs-restricted.png)

Saved ALGO07 conditional candidate-family guards:
Final selected replacement: None. Guard passage and final production acceptance are separate checks; no replacement is implied by a diagnostic orbit fit.
