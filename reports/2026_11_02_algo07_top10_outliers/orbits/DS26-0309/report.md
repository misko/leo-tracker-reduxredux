# DS26-0309: orbit and curve diagnostic

The catalogue search compares the saved ALGO06 composition at its own inferred positions. Per-track nuisance fits are diagnostic lower bounds; a clean fit does not establish unique identity. No localization gain or production recovery is claimed.

| Target | Incumbent | Regime | L3 winner / runner-up | Margin | RMS Hz | Phase s | Rate Hz/s | Noise gate |
|---|---:|---|---|---:|---:|---:|---:|---|
| 0: SCAN-RX1-CH6-T001-RF11959687500.000000 | 60148 | causal | 60148 / 53859 | 348.04 | 87.1 | -3.2 | 0.02 | True |
| 0: SCAN-RX1-CH6-T001-RF11959687500.000000 | 60148 | later | 60148 / 69535 | 160.19 | 87.4 | -1.5 | 0.13 | True |
| 1: SCAN-RX1-CH4-T005-RF11459687500.000000 | 68382 | causal | 68382 / 60722 | 3356.19 | 124.2 | -1.7 | 0.40 | True |
| 1: SCAN-RX1-CH4-T005-RF11459687500.000000 | 68382 | later | 68382 / 60722 | 3527.31 | 110.5 | -0.4 | 0.19 | True |
| 2: SCAN-RX1-CH3-T000-RF11209687500.000000 | None | causal | 65641 / 62600 | 73.95 | 99.8 | -0.8 | -0.23 | False |
| 2: SCAN-RX1-CH3-T000-RF11209687500.000000 | None | later | 65641 / 62600 | 79.78 | 105.8 | 0.9 | -0.07 | False |

Target 0 full graph selects degree 4 under descriptive independent-noise BIC; RMS 62.8 Hz; endpoint leverage [0.39292822477038114, 0.37388143629722415]. Irregular correlation limits this complexity score. Piece fits and excluded original endpoints are retained in `targets.json`.
![Orbit](target-0-orbit.png)
![Graph audit](target-0-graph-audit.png)
![Consecutive 20-second context](target-0-20s.png)
![Candidates](target-0-models.png)

Target 1 full graph selects degree 4 under descriptive independent-noise BIC; RMS 46.4 Hz; endpoint leverage [0.8972588167337417, 0.2763413946617206]. Irregular correlation limits this complexity score. Piece fits and excluded original endpoints are retained in `targets.json`.
![Orbit](target-1-orbit.png)
![Graph audit](target-1-graph-audit.png)
![Consecutive 20-second context](target-1-20s.png)
![Candidates](target-1-models.png)

Target 2 full graph selects degree 4 under descriptive independent-noise BIC; RMS 74.4 Hz; endpoint leverage [0.3656190246313368, 0.23799688952955217]. Irregular correlation limits this complexity score. Piece fits and excluded original endpoints are retained in `targets.json`.
![Orbit](target-2-orbit.png)
![Graph audit](target-2-graph-audit.png)
![Consecutive 20-second context](target-2-20s.png)
![Candidates](target-2-models.png)

Whole-family consistency uses all published native owners of each influential family and matched shortlists. A shared phase/rate must explain every track. Constants remain per-track diagnostic terms; no independent receiver correction is inferred from them.

These restricted-model RMS values are not published baseline residuals. The restricted search uses SGP4 phase plus constant/rate in place of the production marginalized satellite/orbit nuisance block. It omits the posterior physical orbital-mode corrections and any satellite-clock/family corrections in that full block. Published full-model residuals and exact production gates are recorded separately in the sibling diagnostics report. A restricted-model failure therefore does not prove the published association is wrong.

![Family 60148](family-60148.png)
causal family 60148: best shortlist identity 60148, RMS 86.3 Hz, shared phase -3.2 s, rate 0.71 Hz/s, all-track noise pass False.
later family 60148: best shortlist identity 60148, RMS 100.1 Hz, shared phase -1.6 s, rate -0.14 Hz/s, all-track noise pass False.

![Family 68382](family-68382.png)
causal family 68382: best shortlist identity 68382, RMS 106.1 Hz, shared phase -1.8 s, rate 0.74 Hz/s, all-track noise pass False.
later family 68382: best shortlist identity 68382, RMS 92.9 Hz, shared phase -0.4 s, rate -0.08 Hz/s, all-track noise pass False.

Paired causal/later swaps appear in `frozen_tle_swap.json`: the frozen-corrections comparison isolates the changed elements; later-refitted values are separately labeled. Missing later exact fits are null. Exact production gates and localization ablations live in the sibling diagnostics report. These per-track RMS/noise screens are not a replacement for those gates.

Search: every propagation-valid member of causal ≤72h and first-post-epoch ≤48h catalogues receives a coarse scan. Matched c arms share top-three model nominees plus the incumbent and exact phase budget. L1/L2 freeze the saved phase; L3/L4 profile ±30s with a 5s prior. L2 rate prior SD is 0.5 Hz/s and L4 is 2 Hz/s. Detailed inventories and hash provenance are in `run_manifest.json`, `tle_inventory.csv`, and search coverage files.

Remaining ambiguity: independent whole-group prediction and regional position stability have not been executed for these single-track catalogue fits. Per-track slopes cannot distinguish receiver clock, calibration and orbit errors. Next bounded discriminator: compare the same candidate over independent receivers/families using a shared correction, then replay exact ownership gates.

Reproduce from the worktree with `PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python reports/2026_11_02_algo07_top10_outliers/orbits/investigate.py CASE`, then the same invocation of `finish.py CASE`. Archive creation requires the existing read-only archive permission. No RF collection was performed.

Mechanism assessment (restricted model):

Paired later-element check: 0/6 fitted-c rows improve under frozen causal phase, constant and rate. Refitted later-RMS improvements re-estimate those corrections and therefore do not isolate an orbit improvement. Frozen-swap and refitted values are separately listed in `paired_tle_summary.csv`.

Family 60148: incumbent identity stable in restricted family shortlist; geometry or richer nuisance calibration remains the leading unresolved alternative. Same diagnostic identity 60148: later refit restricted-family RMS 86.3→100.1 Hz; this refits nuisance and is not the frozen-swap test. Confidence: model-sensitive / ambiguous; no independent identity validation. Next: Use the rival and incumbent with matched production physical orbital modes and all family receivers, fit on frozen whole time groups, test held groups, then exact ownership/gate replay.

Family 68382: incumbent identity stable in restricted family shortlist; geometry or richer nuisance calibration remains the leading unresolved alternative. Same diagnostic identity 68382: later refit restricted-family RMS 106.1→92.9 Hz; this refits nuisance and is not the frozen-swap test. Confidence: model-sensitive / ambiguous; no independent identity validation. Next: Use the rival and incumbent with matched production physical orbital modes and all family receivers, fit on frozen whole time groups, test held groups, then exact ownership/gate replay.

![Published full nuisance versus restricted model](target-0-published-vs-restricted.png)

![Published full nuisance versus restricted model](target-1-published-vs-restricted.png)

Saved ALGO07 conditional candidate-family guards:
60148_to_53859: passed; minimum competitor margin 79.90312985702917; 10 unique folds. Scope: Conditional on supplied full-data finalist inventory, graph/alias choices, and cavity calibration; not independent discovery or an identity probability.
Final selected replacement: None. Guard passage and final production acceptance are separate checks; no replacement is implied by a diagnostic orbit fit.
