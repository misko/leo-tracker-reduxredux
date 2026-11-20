# Archived initial-only phase-stop diagnostic

The frozen stability rule would have omitted **218 of 4,030 initial refresh rounds (5.41%)** across the 135 original roof recordings. The shared `c = 0` winning branch stayed the same on every recording. Across the selected branches, the largest shifts from the archived five-round initial positions were **0.245 m** with `c = 0` and **0.268 m** with fitted `c`. [Summary](summary.json) · [Matched figure](figures.json)

## Rule and scope

The audit authenticated each original five-round evidence archive, its worker receipt, numerical source and embedded request digest. It read all saved initial branches in cold-rank order and checked that the original lowest final-round `c = 0` objective reproduced the stored winner. The archived phase-reference vector follows the previous raw posterior clipped to ±15 s. At each round the audit independently recomputed the maximum absolute change from that round's reference to its raw posterior, and the movement from the position supplied at the start of the round. The first zero-based epoch at or above 1 with phase change ≤0.01 s and movement ≤0.001 km supplies the stopped checkpoint. The minimum stopped `c = 0` objective selects the shared branch, and the fitted-`c` arm takes its own checkpoint from that same branch. [Rule source](../../../../tools/pipeline_eval/variants/stable_phase.py) · [Archive audit seal](audit-lock.json) · [All saved round measurements](phase-histories.jsonl.gz)

The inputs contain 403 branches per calibration arm, with three on 133 recordings and two on the remaining two. Each historical branch-arm fit has five rounds. The measurements describe saved original initial fits. Recovery, reassociation, and live solver timing are outside this audit. The final points are the separately extracted original v5 controls. [Per-branch evidence](per-branch-arm.csv) · [Selected checkpoints and original final controls](per-recording.csv)

| Calibration arm | Potential rounds saved, all branches | Branches stopping before round 5 | Potential rounds saved on selected branch | Selected cases saving rounds | Largest selected shift from original initial | Largest selected conditional RMS change |
|---|---:|---:|---:|---:|---:|---:|
| `c = 0` | 112 / 2,015 (5.56%) | 109 / 403 | 46 / 675 | 44 / 135 | 0.245 m | 0.00330 Hz |
| Fitted `c` | 106 / 2,015 (5.26%) | 104 / 403 | 46 / 675 | 44 / 135 | 0.268 m | 0.00338 Hz |

Three `c = 0` and two fitted-`c` branches first qualified on round 3. A further 106 and 102 first qualified on round 4. The maximum local difference between the stopped and five-round position across all branches was 0.430 m and 0.268 m. The largest conditional RMS differences across all branches were 0.0119 and 0.0164 Hz. [Stop counts and fit diagnostics](per-branch-arm.csv)

## Geographic and RF comparison

Errors are kilometres from the independent receiver location. The selected conditional RMS median agrees with the original initial median in both calibration arms. The original final stage has its own selected likelihood and support, which account for different RF residual and position distributions. [Both calibration arms and separate RF metrics](per-recording.csv)

| Calibration arm | Stable stop initial median / P95 | Original initial median / P95 | Original final median / P95 | Stable stop / original initial / original final median conditional RMS (Hz) |
|---|---:|---:|---:|---:|
| `c = 0` | 1.285 / 4.487 | 1.285 / 4.487 | 0.982 / 2.941 | 164.044 / 164.044 / 69.817 |
| Fitted `c` | 1.293 / 4.505 | 1.293 / 4.505 | 0.988 / 2.819 | 164.055 / 164.055 / 69.840 |

The two low-priority archive readers finished in 73.40 s. This is audit wall time. [Prediction lock](prediction-lock.json)

```bash
nice -n 10 timeout 470s env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -B -m tools.pipeline_eval.qualification.stable_phase_history_audit \
  --lanes 2 --out /tmp/phase-history-audit
.venv/bin/python -B -m tools.pipeline_eval.qualification.phase_history_results \
  --out /tmp/phase-history-audit
```
