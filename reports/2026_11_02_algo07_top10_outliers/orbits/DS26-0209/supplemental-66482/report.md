# DS26-0209: orbit and curve diagnostic

The catalogue search compares the saved ALGO06 composition at its own inferred positions. Per-track nuisance fits are diagnostic lower bounds; a clean fit does not establish unique identity. No localization gain or production recovery is claimed.

| Target | Incumbent | Regime | L3 winner / runner-up | Margin | RMS Hz | Phase s | Rate Hz/s | Noise gate |
|---|---:|---|---|---:|---:|---:|---:|---|
| 0: SCAN-RX1-CH6-T002-RF11959687500.000000 | 66482 | causal | 66482 / 61677 | 55.08 | 125.5 | -6.0 | 0.14 | True |
| 0: SCAN-RX1-CH6-T002-RF11959687500.000000 | 66482 | later | 66482 / 61677 | 41.72 | 136.3 | 0.3 | -0.40 | False |

Target 0 full graph selects degree 4 under descriptive independent-noise BIC; RMS 111.2 Hz; endpoint leverage [0.3937732764330429, 0.5478897828907561]. Irregular correlation limits this complexity score. Piece fits and excluded original endpoints are retained in `targets.json`.
![Orbit](target-0-orbit.png)
![Graph audit](target-0-graph-audit.png)
![Consecutive 20-second context](target-0-20s.png)
![Candidates](target-0-models.png)

Whole-family consistency uses all published native owners of each influential family and matched shortlists. A shared phase/rate must explain every track. Constants remain per-track diagnostic terms; no independent receiver correction is inferred from them.

These restricted-model RMS values are not published baseline residuals. The restricted search uses SGP4 phase plus constant/rate in place of the production marginalized satellite/orbit nuisance block. It omits the posterior physical orbital-mode corrections and any satellite-clock/family corrections in that full block. Published full-model residuals and exact production gates are recorded separately in the sibling diagnostics report. A restricted-model failure therefore does not prove the published association is wrong.

![Family 66482](family-66482.png)
causal family 66482: best shortlist identity 66482, RMS 113.1 Hz, shared phase -6.0 s, rate 0.07 Hz/s, all-track noise pass True.
later family 66482: best shortlist identity 66482, RMS 121.6 Hz, shared phase 0.4 s, rate -0.70 Hz/s, all-track noise pass False.

Paired causal/later swaps appear in `frozen_tle_swap.json`: the frozen-corrections comparison isolates the changed elements; later-refitted values are separately labeled. Missing later exact fits are null. Exact production gates and localization ablations live in the sibling diagnostics report. These per-track RMS/noise screens are not a replacement for those gates.

Search: every propagation-valid member of causal ≤72h and first-post-epoch ≤48h catalogues receives a coarse scan. Matched c arms share top-three model nominees plus the incumbent and exact phase budget. L1/L2 freeze the saved phase; L3/L4 profile ±30s with a 5s prior. L2 rate prior SD is 0.5 Hz/s and L4 is 2 Hz/s. Detailed inventories and hash provenance are in `run_manifest.json`, `tle_inventory.csv`, and search coverage files.

Remaining ambiguity: independent whole-group prediction and regional position stability have not been executed for these single-track catalogue fits. Per-track slopes cannot distinguish receiver clock, calibration and orbit errors. Next bounded discriminator: compare the same candidate over independent receivers/families using a shared correction, then replay exact ownership gates.

Reproduce from the worktree with `PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 /srv/bulk/leo-dev/fast-algo02-production-v1/.venv/bin/python reports/2026_11_02_algo07_top10_outliers/orbits/investigate.py CASE`, then the same invocation of `finish.py CASE`. Archive creation requires the existing read-only archive permission. No RF collection was performed.

Mechanism assessment (restricted model):

Paired later-element check: 0/2 fitted-c rows improve under frozen causal phase, constant and rate. Refitted later-RMS improvements re-estimate those corrections and therefore do not isolate an orbit improvement. Frozen-swap and refitted values are separately listed in `paired_tle_summary.csv`.

This is a posthoc supplemental family nominated by the completed omission ablation. Original top-two targets are preserved separately. A gate-qualified omission displacement is influence evidence and does not justify removing the family.

Family 66482: incumbent identity stable in restricted family shortlist; geometry or richer nuisance calibration remains the leading unresolved alternative. Same diagnostic identity 66482: later refit restricted-family RMS 113.1→121.6 Hz; this refits nuisance and is not the frozen-swap test. Confidence: model-sensitive / ambiguous; no independent identity validation. Next: Use the rival and incumbent with matched production physical orbital modes and all family receivers, fit on frozen whole time groups, test held groups, then exact ownership/gate replay.

![Published full nuisance versus restricted model](target-0-published-vs-restricted.png)

Saved ALGO07 conditional candidate-family guards:
Final selected replacement: None. Guard passage and final production acceptance are separate checks; no replacement is implied by a diagnostic orbit fit.
