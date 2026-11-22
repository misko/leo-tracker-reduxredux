# Causal stereo visit reduction preserved the inputs and saved no work

**Do not advance this schedule.** The prespecified rule skipped zero visits on the short physical and public southern ledgers. DS30 had ample timestamp overlap, but no antenna pair established the required run of measured strong support at the forecast follow-up. The simulated cadence never offered four donors at that follow-up even under the optimistic all-donors calculation. [Prespecified rule](adaptive-stereo-visits-protocol.md) · [Ordered replay receipt](measurements/adaptive-stereo-visits.json.gz)

| Saved ledger | Scheduled / admitted stereo visits | Timestamp-only maximum skips | Actual skips | Verified raw factors retained | Exact selected factors retained | Native CPU eligible for saving |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0016, physical | 808 / 713 | 343 | 0 | 807 / 807 | 440 / 440 | 0 of 4.631 s |
| Southern simulation | 1,200 / 1,200 | 0 | 0 | 531 / 531 | 456 / 456 | 0 of 6.357 s |

The replay matched every original published probe before comparing the adaptive decisions. It presented a window's factors only when the scheduler requested the measurement. A synthetic steady lane exercises the skip path and confirms that its empty opportunity advances continuation without contributing a vote. Other tests cover the forced follow-up, a weak secondary onset, distinct RF histories and the timestamp ceiling. [Schedule code](../../../tools/pipeline_eval/variants/experimental/adaptive_stereo_visits.py) · [Component tests](../../../tests/pipeline_eval/test_adaptive_stereo_visits.py)

The complete ordered candidate probe documents were identical to the saved inputs. Both calibration arms therefore use the existing scientific receipt for each recording. The audit binds the ledger to the acquired sample authority and records the fitted region, ownership, numerical grid, path and eight published image digests from the earlier receipt. The two original arms used the same probes, prior and search budgets on each site. [Existing paired publications](moments-publication.md) · [Reused numerical digests](measurements/adaptive-stereo-visits.json.gz)

| Existing science from the identical input | Frequency RMS, fixed zero / fitted | Horizontal error, fixed zero / fitted |
|---|---:|---:|
| DS30-0016 | 109.375 / 109.479 Hz | 1.644 / 1.661 km |
| Southern simulation | 6.503 / 6.392 Hz | 0.826 / 1.109 km |

The southern fitted calibration reduced frequency RMS while increasing horizontal error. The position references enter only this scoring comparison. [Physical reference rules](../../2026_11_21_ds30_full/PROTOCOL.md) · [Public simulated scoring key](../regional-release/scoring-key.json)

## Dense recording ceiling

Existing DS30-0374 timestamps made 4,575 of 4,644 admitted visits structurally eligible if every previous opportunity could provide coherent strong evidence. The largest nonconsecutive set has **2,293 stereo skips**, equivalent to at most 4,586 antenna calls. The calculation allows every historical opportunity to vote and disregards any future loss of usable donors caused by the schedule. That makes it a bound on visit count. The full-observation batch publication paid for 8,933 native calls in 32.02 CPU seconds. At its measured mean cost, removing 4,586 paid calls would correspond to **16.44 CPU seconds**. The mixed distribution of lane costs and existing deferral mean that projection cannot establish whole-pipeline savings. The actual compute shortfall for the 2× target on that publication was **12.58 seconds**. [Dense timing receipt](measurements/DS30-0374-batch.json) · [Clock breakdown](batch-publication.md)

The dense detection file carries final continuation selections and counters. It does not carry the full pre-continuation factors needed to determine how often this rule could enter its strong-support state. The two unreduced replay documents left no changed solver input to evaluate. This evaluation read the saved ledgers, detections and receipts only. The replay was serialized under the Gauss lock on CPU 2 with low process and I/O priority and one numerical thread. Thirteen schedule and continuation tests passed. [Ledger capture](receiver_factor_ledger.py) · [Replay harness](adaptive_stereo_visits_trial.py)

```sh
flock "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD/$report:$PWD:$release/src:$release" OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs "$report/adaptive_stereo_visits_trial.py" \
  --case DS30-0016 "$bench/ledger-DS30-0016.json.gz" "$ds30_detections" "$ds30_pair" \
  --case south "$bench/ledger-south.json.gz" "$south_detections" "$south_pair" \
  --dense "$report/measurements/DS30-0374-batch.json" "$dense_detections"
```
