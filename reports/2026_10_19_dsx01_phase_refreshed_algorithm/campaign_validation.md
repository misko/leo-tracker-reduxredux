# Completed 13-start DSX01 campaign: compact publication snapshot

This snapshot preserves the completed campaign's validation conclusions. Its large plot gallery and per-run histories remain in the local archived campaign. Links below point to the compact receipts included with this publication.

The original independent-start campaign is complete: **49 configurations × 5 scans × 13 starting positions = 3,185 paired runs**, with **6,370 fitted endpoints** and 65 independently initialized discovery results. There were no failed jobs or blocked dependencies. This is distinct from the subsequent 81-start joint-descent investigation.

The [terminal receipt](campaign/run_receipt.json), [protocol](campaign/protocol.json), and every result agree on source fingerprint `ed01548efc5c171197e46e08d8f9d4206041762494b0677782e1982c1a8cf418`. All 202 bound source files retain their recorded hashes. The final plot watcher exited successfully with all 3,185 paired results and 6,370 finite endpoints rendered: 245 basin plots, 245 endpoint-loss plots, and 245 original-versus-new comparison figures.

[Algorithm and present findings](README.md) · [Every endpoint and association count](campaign/restart_summary.csv) · [Consistency audit](campaign/consistency_audit.json) · [Plot audit](campaign/report_audit.json) · [Watcher receipt](campaign/watcher_status.json)

## What was checked

- All 13 starting coordinates lie on the declared 5 km grid inside the 10 km disk. Each scan/start has its own fresh discovery receipt; learned state is reused only by recipes at that same start.
- Discovery and normal-parent hashes match their consuming results. Satellite labels, aliases, membership, and common round-start positions agree between each `c = 0` and fitted-`c` pair.
- Associated-point and track counts reproduce from each result's stored acceptance decisions.
- Read receipts contain no old assignment atlas, inherited endpoint, following-TLE diagnostic, or another starting position's learned state.
- Causal input receipts pass. A separate byte-epoch and collection-time check covered all **15,443** records in the five past-only history exports.

These checks validate stored provenance and consistency. They do not constitute a complete cold replay of all 3,185 pipelines, proof of satellite identity, or a global-optimality certificate.

## Numerical stopping conditions

| Final endpoint status | Count |
|---|---:|
| Small step and improvement | 4,208 |
| No accepted damped step | 1,472 |
| Outer iteration budget reached | 40 |
| Scalar optimizer converged | 650 |
| Total | 6,370 |

The 40 budget-limited locations are listed in the consistency audit. A no-accepted-step status alone does not certify stationarity. Inner variational stopping diagnostics were not persisted for the full campaign: its `variational_converged` fields are null, so they must not be interpreted as convergence passes.

Four S01 normal endpoints—center and eastern boundary starts, both `c` arms—were independently reevaluated without optimizing. All four objectives replay exactly, with maximum score difference **0**. Actual 50 m central-difference gradient magnitudes range from **5.20 × 10⁻⁵ to 1.19 × 10⁻⁴ loss/km**. Their inner precision updates each converged in 17 iterations, below the `1e-5` tolerance. These inner-convergence statements apply only to these four replays. See [replay values and gradients](campaign/endpoint_gradient_replay.json).

The engine and standalone auditor have **17 focused component tests passing**; Ruff checks pass. No golden fixtures changed.

## Representative position results

For each method and scan, select the lowest **c0 frequency/prior objective** among the 13 starts and use that same starting-position result for the paired fitted-`c` comparison. GPS evaluates errors afterward and does not select a result. This keeps the observations, candidate pool, other priors, and search budgets matched within each pair.

| Scan | Method | Selected start | c0 error, km | Fitted-c error, km | Associated points, c0 / fitted-c |
|---|---|---:|---:|---:|---:|
| S01 | Normal | 8 | 0.571 | 0.560 | 2,646 / 2,646 |
| S01 | Linear white joint | 12 | 0.693 | 0.685 | 3,536 / 3,500 |
| S02 | Normal | 2 | 1.121 | 1.161 | 1,973 / 1,973 |
| S02 | Linear white joint | 2 | 0.943 | 0.996 | 2,334 / 2,334 |
| S03 | Normal | 8 | 1.806 | 1.875 | 2,287 / 2,287 |
| S03 | Linear white joint | 8 | 1.947 | 1.984 | 2,700 / 2,700 |
| S04 | Normal | 7 | 1.847 | 1.876 | 2,330 / 2,330 |
| S04 | Linear white joint | 8 | 3.232 | 3.252 | 2,701 / 2,701 |
| S05 | Normal | 9 | 1.873 | 1.856 | 1,934 / 1,934 |
| S05 | Linear white joint | 5 | 1.610 | 1.606 | 2,519 / 2,519 |

[Exact representative values and medians](campaign/representative_results.json) retain the selection rule. Lower frequency/prior loss does not imply lower position error: for example, S03 normal's c0 objective winner has 1.806 km error, while the median across its 13 starts is 1.073 km. These frozen configurations do not achieve sub-kilometer accuracy on all five scans.

The frequency/prior objectives for those same paired results are reported separately below. They include the method's priors, covariance-volume terms and, for linear transfer, predictive score. They are not pure frequency RMS values and should be compared within each method, rather than ranked across different methods.

| Scan | Method | c0 objective | Fitted-c objective |
|---|---|---:|---:|
| S01 | Normal | 12,874.192 | 12,886.412 |
| S01 | Linear white joint | 24,305.708 | 24,317.918 |
| S02 | Normal | 12,119.969 | 12,123.033 |
| S02 | Linear white joint | 16,960.944 | 16,962.099 |
| S03 | Normal | 13,188.787 | 13,196.553 |
| S03 | Linear white joint | 18,562.209 | 18,569.530 |
| S04 | Normal | 12,387.904 | 12,396.641 |
| S04 | Linear white joint | 18,355.068 | 18,364.694 |
| S05 | Normal | 12,290.089 | 12,301.440 |
| S05 | Linear white joint | 20,128.016 | 20,139.562 |

Here fitted-`c` has higher composite objective in all ten comparisons, while its effect on position error is mixed. The full CSV also retains each method's residual metric; normal's RMS covers all modeled curved observations, whereas linear transfer reports accepted curved-track RMS and does not include linear observations in that RMS column.

The maps show sampled starting positions and resulting optimization paths/endpoints. Endpoint groups and their frequencies are descriptive basin summaries, not calibrated probabilities. Position-independent acquisition, GLRT measurements, and graph tracks were cached; satellite discovery and association/localization were rerun from each starting position.
