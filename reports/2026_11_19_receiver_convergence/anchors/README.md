# Periodic capture-era detector anchor

Replacing every 64th complete sweep with the capture-era detector produced six fixes in both calibration arms. Median errors increased from 1.027 / 1.102 km on full ordinary native GLRT to 1.304 / 1.330 km with periodic anchors. Errors improved on two of six recordings in each arm. Conditional Doppler RMS decreased on four of six. Both raw confirmation sweeps reproduced the exact saved outputs from both detectors. [Frozen protocol](PROTOCOL.md) · [Hybrid positions](positions.jsonl.gz) · [Prediction seal](prediction-lock.json)

| Recording | Valid reference visits of 112 selected | Hybrid error | Ordinary control error | Capture-era control error |
|---|---:|---:|---:|---:|
| DS26-0036 | 112 | 0.465 / 0.415 km | 0.231 / 0.186 km | 1.278 / 1.208 km |
| DS26-0122 | 112 | 1.957 / 1.964 km | 1.331 / 1.331 km | 0.751 / 0.747 km |
| DS26-0237 | 112 | 0.768 / 0.681 km | 0.896 / 0.821 km | 0.362 / 0.271 km |
| DS29-0082 | 79 | 2.821 / 2.768 km | 2.802 / 2.662 km | 0.567 / 0.517 km |
| DS29-0174 | 111 | 1.123 / 1.194 km | 1.159 / 1.225 km | 0.885 / 0.917 km |
| DS29-0247 | 111 | 1.485 / 1.466 km | 0.711 / 0.980 km | 1.320 / 1.458 km |

Each pair gives `c = 0` / fitted `c`. The fresh hybrid fits took 46.54–179.14 s and the fresh ordinary controls took 47.44–200.93 s. The capture-era controls came from the authenticated complete compact-projector archive, with the same locked solver sources, exact factor files and causal catalogue. [Ordinary controls](ordinary-control-positions.jsonl.gz) · [Capture-era controls](capture-era-control-positions.jsonl.gz) · [Geographic and frequency scores](scores.csv)

Every recording had 846 complete sweeps. The schedule selected sweep 0 and then sweeps 64–832 at a spacing of 64, yielding 112 scheduled visits per recording. The index retained all invalid slots. Both physical receivers changed together on every selected valid visit. Original factors stayed in place everywhere else. The schedule receipts bind the full indexed recording, the complete detector inputs and the hybrid factor digest. All ordinary raw lanes were reassembled and matched their published factor files before the swap. [Schedule receipts](schedule-receipts.json)

## Measured and estimated detector workload

| First selected sweep | Valid visits verified | Measured ordinary CPU / wall | Measured capture-era CPU / wall | Measured whole ordinary CPU | Estimated whole hybrid CPU |
|---|---:|---:|---:|---:|---:|
| DS26-0036 | 8 / 8 | 0.134 / 0.137 s | 14.859 / 15.379 s | 171.48 s | 377.62 s |
| DS29-0082 | 6 / 8 | 0.108 / 0.199 s | 17.359 / 31.956 s | 134.14 s | 361.28 s |

Each detector consumed the original 20 ms dual-CI16 windows from the selected eight scheduled visits. The raw loader authenticated the 12.8 MB of selected samples in each case. The installed original capture-era detector and the ordinary C library both reproduced their archived numerical factors. DS29 preserved both original invalid-capture exclusions. The first DS26 waveform attempt reached its 45 s cap. Its 120 s bounded retry completed. Estimates add the first sweep's mean extra CPU per valid visit to the measured whole ordinary CPU for each switched visit. They describe detector work and carry the sampling uncertainty from a single sweep. Full live hybrid acquisition and deadline behavior were unmeasured. [DS26 raw sweep](DS26-0036-raw-sweep.json.gz) · [DS29 raw sweep](DS29-0082-raw-sweep.json.gz)

## Reproduce

The archive worker uses the original capture installation for each raw sweep. Start the archive replay and numerical jobs in fresh output locations. The scheduled swap and compact fit require no radio hardware.

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
taskset -c 0-3 .venv/bin/python -B -m tools.pipeline_eval.qualification.periodic_anchor_trial \
  --prepare --work /tmp/periodic-anchor-factors
taskset -c 0-3 .venv/bin/python -B -m tools.pipeline_eval.qualification.periodic_anchor_trial \
  --fit --work /tmp/periodic-anchor-factors --cpus 0 1 2 3
.venv/bin/python -B -m tools.pipeline_eval.qualification.periodic_anchor_trial \
  --publish /tmp/periodic-anchor-report --work /tmp/periodic-anchor-factors
.venv/bin/python -B -m tools.pipeline_eval.qualification.periodic_anchor_trial \
  --score /tmp/periodic-anchor-report
```

Run the paired raw sweep verifier after the position workers release their pinned CPUs.

```sh
.venv/bin/python - <<'PY'
import os
import subprocess
from tools.pipeline_eval.qualification.full_v5_check import PRODUCERS, REPO
from tools.pipeline_eval.qualification.recording_to_v5 import ARCHIVE_PYTHON, SINGLE_THREAD

for cpu, (case, producer) in zip((2, 3), PRODUCERS.items(), strict=True):
    env = {**os.environ, **SINGLE_THREAD, 'PYTHONPATH': f'{producer.root}:{REPO}'}
    subprocess.run([
        'timeout', '120s', 'taskset', '-c', str(cpu), str(ARCHIVE_PYTHON), '-B', '-m',
        'tools.pipeline_eval.qualification.periodic_anchor_trial_iq', '--case', case,
        '--schedule', f'/tmp/periodic-anchor-factors/{case}/schedule.json',
        '--out', f'/tmp/periodic-anchor-report/{case}-raw-sweep.json.gz',
    ], env=env, check=True)
PY
```

[Anchor selection and validation](../../../tools/pipeline_eval/variants/periodic_anchor.py) · [Raw sweep verifier](../../../tools/pipeline_eval/qualification/periodic_anchor_trial_iq.py) · [Component tests](../../../tests/pipeline_eval/test_periodic_anchor.py)
