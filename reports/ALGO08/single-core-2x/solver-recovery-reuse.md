# Reusing a converged fit after track recovery

The production solver fits both calibration arms, excludes incompatible tracks and attempts to recover portions of those tracks. When recovery accepts no change, the production solver can repeat the same converged pair of fits. The prototype still runs the full recovery search. It reuses the preceding pair only when the original scan object, serialized assignment inputs, observation mask, and all fitting budgets match. It discards the entry after one use and bypasses reuse for callbacks or parallel arm mapping. The cache lives inside one recovery invocation.

| Saved detections and offer | Control → reuse, solver CPU | Recovery pairs reused | Outcome |
|---|---:|---:|---|
| DS30-0016, containing offer | 4.608 → 4.522 s | 1 | Same valid position |
| Northern simulation, far omitted offer | 11.831 → 11.041 s | 1 | Same false fix |

Each row is one component comparison on a single low-priority core. The two runs at each site returned identical decisions, both calibration arms, residuals, attempted trims, shortlists, objective replay, optimizer path and grid after excluding recorded timings. Each kept its own search square and orbital inputs. The northern false fix remains a geographic failure. On earlier dense DS30 cases, recovery changed the accepted observations, which would require a fresh pair. These measurements do not predict an end-to-end saving on those cases. [Full measurements](measurements/recovery-reuse.json.gz)

Run `solver_recovery_reuse_trial.py MODE DETECTIONS TLE_ARCHIVE ASSETS OFFER DETECTIONS_SHA256` with `MODE` set to `control` or `reuse`, using the release interpreter, a single numerical thread and the shared Gauss benchmark lock. Both use the saved-detection solver with causal orbit reuse and the same track recovery calculations. [Runner](solver_recovery_reuse_trial.py) · [Scoped implementation](../../../tools/pipeline_eval/variants/algo08_recovery_reuse.py) · [Component tests](../../../tests/pipeline_eval/test_algo08_recovery_reuse.py)
