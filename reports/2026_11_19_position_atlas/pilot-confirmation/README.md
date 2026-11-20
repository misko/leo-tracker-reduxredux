# Late-pilot confirmation through position

The 112-visit intervention moved the DS26 position farther from truth in both calibration arms. The DS29 position and conditional frequency fit were identical to the matched ordinary control. Applying the gate at every valid visit reduced conditional frequency RMS on both recordings. The DS26 `c = 0` position improved by 76 m, its fitted-`c` position worsened by 61 m, and the DS29 positions changed by less than 19 m. [Sample positions](positions.jsonl.gz) · [Matched ordinary controls](control-positions.jsonl.gz) · [All-visits positions](full-positions.jsonl.gz)

The primary comparison uses the frozen late-pilot decision from 112 scheduled visits per recording. It feeds both candidate sets through complete v5 observation selection, track reconstruction, catalogue association and position solving. The matched control uses the complete ordinary native detector output from the same raw recording. Capture-era v5 remains a separate reference. The original detector qualification missed its predeclared agreement criterion on both recordings. [Position protocol](PROTOCOL.md) · [Original detector qualification](../../2026_11_19_receiver_frontend/confirmation/README.md)

| Recording | Capture-era v5 error | Matched ordinary error | 112-visit gate error | All-visits gate error |
|---|---:|---:|---:|---:|
| DS26-0036 | 1.278 / 1.208 km | 0.231 / 0.186 km | 0.308 / 0.245 km | 0.155 / 0.247 km |
| DS29-0082 | 0.567 / 0.517 km | 2.802 / 2.662 km | 2.802 / 2.662 km | 2.802 / 2.681 km |

Each cell gives `c = 0` / fitted `c`. Both fresh ordinary control fits reproduced their published coordinates, conditional RMS and frequency score exactly. [Published complete ordinary results](../../2026_11_19_receiver_frontend/ordinary/positions.jsonl.gz)

| Recording | Matched ordinary conditional RMS | 112-visit gate conditional RMS | All-visits gate conditional RMS |
|---|---:|---:|---:|
| DS26-0036 | 102.260 / 102.296 Hz | 102.135 / 102.161 Hz | 98.279 / 98.204 Hz |
| DS29-0082 | 106.677 / 106.591 Hz | 106.677 / 106.591 Hz | 106.415 / 106.329 Hz |

The all-visits comparison uses 2,516 associated observations on DS26 and 1,294 on DS29. The ordinary controls used 2,521 and 1,310. Conditional RMS describes each arm's selected observations and associations.

| Recording | Scheduled visits | Valid visits | Sample visits gated | Originally positive proposals removed in the sample arm | Originally positive proposals removed in the all-visits arm |
|---|---:|---:|---:|---:|---:|
| DS26-0036 | 6,769 | 6,765 | 112 | 38 / 15,073 | 1,603 / 15,073 |
| DS29-0082 | 6,772 | 4,868 | 112 | 10 / 7,962 | 336 / 7,962 |

The sample arm checked 317 originally passing proposals on DS26 and 185 on DS29. The removal touched 22 and 7 recorded visits, respectively. DS29 had 33 rejected captures in the sample, so 79 scheduled sample visits reached the waveform decision. The all-visits arm streamed all authenticated segments and reproduced the original decisions for all 112 scheduled sample visits on each recording. It reused the exact ordinary native proposal coordinates and measured confirmation directly on the committed dual-CI16 samples. Its incremental confirmation CPU time was 27.94 s on DS26 and 15.09 s on DS29. Those times exclude archive read and ordinary GLRT compute and include witness input preparation. [Sample replay](../../../tools/pipeline_eval/qualification/confirmation_position.py) · [All-visits replay](../../../tools/pipeline_eval/qualification/confirmation_position_full.py)

Each result declares the ordinary native source archive SHA-256 and the exact numerical input digest. The frozen ordinary inputs and the sample receipt digests are bound before inference. All arms retain the same causal catalogue, roof tile, clocks, capture exclusions, receiver identities and no-repair policy.

The all-visits archive read, confirmation and reconstruction took 160.93 s on DS26 and 142.32 s on DS29. The full numerical fits took 382.75 s and 202.80 s respectively, for 543.68 s and 345.12 s elapsed. These wall times include concurrent pinned work. The DS26 ordinary control finished on the second allocated CPU after the DS29 jobs completed. Twelve component tests passed, covering exact IQ and candidate binding, unchanged factors outside the gate, preserved ranks, whole-stream terminal coverage and the frozen waveform witness. [Position replay tests](../../../tests/pipeline_eval/test_confirmation_position.py)

## Reproduce

Run from the repository root. Start each recording in a separate process with one CPU and one numerical thread. Use fresh scratch roots outside the recording archive. The complete gate opens the recordings with their installed capture-era source runtime.

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
taskset -c 8 .venv/bin/python -m tools.pipeline_eval.qualification.confirmation_position \
  --case DS26-0036 --work /tmp/late-pilot-paired-position
taskset -c 9 .venv/bin/python -m tools.pipeline_eval.qualification.confirmation_position \
  --case DS29-0082 --work /tmp/late-pilot-paired-position
.venv/bin/python -m tools.pipeline_eval.qualification.confirmation_position \
  --work /tmp/late-pilot-paired-position --publish /tmp/late-pilot-position-outputs
taskset -c 8 .venv/bin/python -m tools.pipeline_eval.qualification.confirmation_position_full \
  --case DS26-0036 --work /tmp/late-pilot-all-position
taskset -c 9 .venv/bin/python -m tools.pipeline_eval.qualification.confirmation_position_full \
  --case DS29-0082 --work /tmp/late-pilot-all-position
.venv/bin/python -m tools.pipeline_eval.qualification.confirmation_position_full \
  --work /tmp/late-pilot-all-position --publish /tmp/late-pilot-position-outputs
```
