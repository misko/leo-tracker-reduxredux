# Single-tile omission challenge

All three receivers withheld all three recordings when given the first tile from the frozen missing-region query. There were **0 false publications in 9 executions**, with zero publications in either calibration arm. All nine runs produced forced estimates, 33.45–526.00 km from the independent reference. The exact same three recordings have separate, archived correct-tile predictions. Folded Doppler issued one correct-tile fix on DS29-0174, 6.38 km from the reference in both arms. Point votes and rate triplets withheld all three correct-tile runs too. This cohort demonstrates the observed abstentions and limited correct-tile publication coverage. [Protocol](PROTOCOL.md) · [Paired decisions and errors](scores.json) · [Chart](omitted-tile.png)

| Receiver | Correct-tile publications | Omitted-tile false publications | Omitted-tile forced error, km | Omitted-tile wall time, s |
|---|---:|---:|---:|---:|
| Point votes | 0 / 3 | 0 / 3 | 47.37–526.00 | 9.55–13.57 |
| Rate triplets | 0 / 3 | 0 / 3 | 33.45–499.79 | 6.56–10.10 |
| Folded Doppler | 1 / 3 | 0 / 3 | 56.96–510.51 | 3.44–4.60 |

Counts are per calibration arm and agree across arms. Forced error ranges span both arms. The omitted-tile wall measurements include native GLRT and TLE loading, verification, sandbox setup and solving. `scores.json` preserves the timing reported for each archived correct-tile run under its original boundary. The chart compares positions and decisions from the three GLRT-only receivers.

The full native-GLRT bytes and causal TLE bytes matched across both tile conditions for every recording. The Transfer124 prepared observation bytes were hashed to bind the query to the recording. Only native probe candidates, capture timing, causal TLE and the first declared tile went to the worker. Frozen coordinates entered only after the omitted predictions were sealed. [Point votes receipts](point_votes.jsonl.gz) · [Rate triplets receipts](rate_triplets.jsonl.gz) · [Folded Doppler receipts](folded_doppler.jsonl.gz)

Point-vote carrier differences cancel the fixed-RF calibration term. Folded Doppler absorbs it into the offset fitted on each fixed-RF channel. Both methods returned identical scores and endpoints for their two arms. Rate triplets fits the coefficient explicitly. On DS29-0247, for example, fitted `c` reduced the conditioned frequency RMS from 1,100 to 1,065 Hz while the forced geographic error increased from 498.92 to 499.79 km. Both arms withheld. Its DS29-0174 wrong-tile fit attained about 183 Hz RMS and still withheld the forced coordinate, which was 278.88 km from the reference.

The initial folded sandbox could not resolve the compiler `cc`. The retry mounted the host compiler's symlink directory and restored its binary path. It used the original locked solver and tile bytes. All three first attempts failed before returning a scientific decision and are accounted for separately. [Setup failure lock](setup-retry/folded_doppler-lock.json) · [Successful folded lock](folded_doppler-lock.json)

## Reproduce

```sh
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  taskset -c 6,7,22,23 .venv/bin/python -B -m tools.pipeline_eval.qualification.cold_missing \
  predict --out "$NEW_OUTPUT_DIRECTORY"
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 MPLBACKEND=Agg \
  taskset -c 6,7,22,23 .venv/bin/python -B -m tools.pipeline_eval.qualification.cold_missing \
  score --out "$NEW_OUTPUT_DIRECTORY"
```
