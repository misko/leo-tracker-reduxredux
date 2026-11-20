# Coarse pilot filter bank

The tiled bank cut median paired CPU time by 14.7% on DS26 and 13.9% on DS29, measured against the receiver's existing anchor-grid acceleration. The paired replay returned byte-equivalent detector payloads for all 16 windows. Both versions used the same installed producer, candidate grid, sample support, control pilots and thresholds. The optimized kernel accumulates four real products independently, then forms the complex result after the tap loop. That allows the compiler to use four fused multiply-add chains and keep 16 epochs' intermediate products in registers. [Protocol](PROTOCOL.md) · [Kernel](../../../tools/pipeline_eval/variants/pilot_kernel.c) · [Replay runner](../../../tools/pipeline_eval/qualification/pilot_kernel_eval.py)

The baseline profile covered four separate scheduled windows per recording with the existing anchor fast path enabled. The coarse grid took 3.21 of 6.55 profiled seconds on DS26 and 3.13 of 6.33 on DS29. Fractional evaluation took 1.14 and 1.21 seconds, and the fine CFO and whole-frame conditioned CFO stages each took 0.69–0.85 seconds. The timed comparison below excludes profiling and IQ decode. [DS26 profile](DS26-0036-profile.json.gz) · [DS29 profile](DS29-0082-profile.json.gz)

## Detector timings and agreement

Each value below uses three paired runs for each valid 20 ms window. The median for each window enters the across-window distribution. The wall and CPU results each come from one pinned Intel Core Ultra 9 285K CPU per recording, with GCC 15.2 and one numerical thread. The two sets of windows are about 136 seconds apart by recorded sample counter in each 10 MS/s recording. The selected sequences cover channels 2, 4, 6 and 8. On DS29, channels 2 and 6 had invalid sample support in both segments. [Window-level timings](detector-timing.csv) · [DS26 receipt](DS26-0036-detector.json.gz) · [DS29 receipt](DS29-0082-detector.json.gz)

| Recording | Valid / scheduled | Wall control → tiled, median / P95 s | CPU control → tiled, median / P95 s | Median paired wall speedup, range |
|---|---:|---:|---:|---:|
| DS26-0036, lower edge | 8/8 | 0.840 / 1.271 → 0.718 / 1.082 | 0.840 / 1.271 → 0.718 / 1.082 | 1.172×, 1.050–1.214× |
| DS29-0082, upper edge | 4/8 | 0.830 / 1.382 → 0.748 / 1.196 | 0.830 / 1.382 → 0.748 / 1.195 | 1.161×, 1.072–1.171× |

Across 192 complete candidate records, the canonical payloads agreed on the integer and fractional scores, candidate order, gates, and capture status. All 208 retained coarse peaks had the same epoch, frequency and order. The largest absolute coarse-peak score change was 7.0 × 10⁻⁹. Near-tied peaks on unseen inputs can be sensitive to the altered single-precision accumulation. The 24 selected receiver probe rows and the four invalid-capture exclusions matched the archived producer output.

A repeat used a different CPU for each recording and reproduced every canonical hash, peak trace and archive check. Median paired CPU speedups in that repeat were 1.147× on DS26 and 1.124× on DS29. The repeat used the final runner, which also removes a redundant control-to-control comparison from the archive summary. [Repeat verification](replay-verification.json)

## Position with the archived remainder

Each fit uses eight scheduled windows from the raw-IQ replay and stored detections for all other visits. The fresh windows contribute two positive fractional observations on DS26 and six on DS29. Each detection arm went through the same compact projector and v5 cavity decision with both calibration settings. The paired worker received identical observations, policies, causal catalogues and region budgets. It returned exactly the same coordinates and conditional RMS for the two filter banks in both calibration arms. The coordinates also equal the two published original-v5 endpoints for each recording. [DS26 paired position receipt](DS26-0036-position-pair.jsonl.gz) · [DS29 paired position receipt](DS29-0082-position-pair.jsonl.gz) · [Scored errors](position-errors.csv) · [Standard predictions](positions.jsonl.gz)

| Recording | Position error with `c = 0` → fitted `c` | Conditional Doppler RMS with `c = 0` → fitted `c` |
|---|---:|---:|
| DS26-0036 | 1.278 → 1.208 km | 74.761 → 74.682 Hz |
| DS29-0082 | 0.567 → 0.517 km | 97.004 → 96.684 Hz |

The calibration comparison describes these two fits. The kernel speedup comes from the paired detector windows. Measuring complete original-rate IQ through position or qualifying real-time performance on the receiver board requires separate tests.

## Reproduce

Run from the repository on the corpus host. The first command compiles both C filters for the host and verifies each capture-era worker before reading the archived IQ. It uses the same pinned CPU for each arm within a recording. The profile command can be repeated separately with `--profile` and a different output path. The second command runs both composites through the compact projector and the same v5 cavity decision.

```sh
.venv/bin/python - <<'PY'
import os
import subprocess
import sys
from pathlib import Path

from tools.pipeline_eval.__main__ import ROOT, THREAD_ENV
from tools.pipeline_eval.qualification.full_v5_check import PRODUCERS

out = Path('/tmp/pilot-kernel-results')
out.mkdir(exist_ok=True)
cpu = str(min(os.sched_getaffinity(0)))
command = ['taskset', '-c', cpu, sys.executable, '-m']
for case, producer in PRODUCERS.items():
    receipt = out / f'{case}-detector.json.gz'
    subprocess.run(
        command + ['tools.pipeline_eval.qualification.pilot_kernel_eval',
                   '--case', case, '--out', str(receipt)],
        env={**os.environ, **THREAD_ENV, 'PYTHONPATH': f'{producer.root}:{ROOT}'},
        check=True,
    )
    subprocess.run(
        command + ['tools.pipeline_eval.qualification.pilot_kernel_positions',
                   '--case', case, '--receipt', str(receipt),
                   '--work', str(out / case),
                   '--out', str(out / f'{case}-position-pair.jsonl.gz')],
        check=True,
    )
PY
```
