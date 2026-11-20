# Complete raw GLRT to anonymous tracks and robust EM

Complete fresh dual-CI16 replay reproduced the qualified ordinary native detector factors byte for byte on both recordings. With freshly reconstructed tracks, robust EM issued a 1.84 / 2.37 km fix on DS26-0036 and withheld DS29-0082. On the full six-recording timing panel, robust EM returned four fixes from ordinary native GLRT and five from capture-era GLRT. Both original v5 comparisons returned all six. [Protocol](PROTOCOL.md) · [Ordinary detector positions](positions.jsonl.gz) · [Capture-era detector positions](control-positions.jsonl.gz) · [Prediction seal](prediction-lock.json)

| Recording | Ordinary input | Ordinary + robust EM | Capture-era + robust EM | Ordinary + v5 | Capture-era + v5 |
|---|---|---:|---:|---:|---:|
| DS26-0036 | Fresh IQ | 1.843 / 2.369 km | 1.832 / 2.136 km | 0.231 / 0.186 km | 1.278 / 1.208 km |
| DS26-0122 | Qualified ordinary artifact | 2.206 / 2.209 km | 2.688 / 2.729 km | 1.254 / 1.254 km | 0.751 / 0.747 km |
| DS26-0237 | Qualified ordinary artifact | 0.524 / 0.790 km | 1.279 / 0.801 km | 0.896 / 0.821 km | 0.362 / 0.271 km |
| DS29-0082 | Fresh IQ | Withheld, guess 2.115 / 1.713 km | 4.479 / 4.158 km | 2.802 / 2.662 km | 0.567 / 0.517 km |
| DS29-0174 | Qualified ordinary artifact | 1.237 / 1.122 km | 1.462 / 1.359 km | 1.159 / 1.225 km | 0.885 / 0.917 km |
| DS29-0247 | Qualified ordinary artifact | Withheld, guess 9.564 / 9.551 km | Withheld, guess 3.045 / 2.794 km | 0.711 / 0.980 km | 1.320 / 1.458 km |

Each pair lists `c = 0` / fitted `c`. Among issued fixes, median error was 1.540 / 1.666 km for ordinary native and 1.832 / 2.136 km for capture-era GLRT. The median populations differ because DS29-0082 issued only in the capture-era arm. The ordinary detector gave lower error in three of the four recordings that issued in both arms. [Per-recording scores](scores.csv) · [Error distributions](summary.json)

Fitted `c` reduced the conditional RMS on all six recordings with either detector. In the ordinary detector arm it reduced error on one of the four issued fixes. Conditional metrics describe each fit's selected tracks and assignments. The [score table](scores.csv) preserves the frequency RMS and fit scores separately from geography, including diagnostic fits when the publication gate withheld the position.

## What was measured

The reader authenticated all 14 sealed segments per fresh replay and restarted the same frozen ordinary C detector with the original sample geometry. The sealed graph stage selected winning GLRT candidates and rebuilt anonymous graph tracks from each full native file. The tracker passed only numerical track arrays and capture-time metadata to robust EM. The fitter ran in a fresh bubblewrap sandbox with the original 25 km tile and the causal catalogue. The ordinary-vs-capture detector pair had identical sample-clock authority, input manifest, raw IQ authority, exclusions and probe support. The detector-specific reductions used the same track configuration and locked fit implementation.

| Fresh replay | Visits | IQ input | Archive-to-native wall | Detector CPU, both lanes | Graph wall | Fit wall | Sum of measured pipeline walls |
|---|---:|---:|---:|---:|---:|---:|---:|
| DS26-0036 | 6,769 | 10.830 GB | 149.29 s | 202.88 s | 9.50 s | 10.08 s | 170.27 s |
| DS29-0082 | 6,772 | 10.835 GB | 114.90 s | 150.84 s | 1.11 s | 2.79 s | 119.24 s |

The raw lanes used CPUs 10 and 11. The numerical workers used one pinned CPU each, 17 or 18. The final column includes decoding, orchestration and the fit, with the two measured boundaries summed. The tracker process peaked at 154,724 KiB across the paired runs, and the fitter peaked at 154,832 KiB. Raw lane peak memory was unmeasured. The four ordinary artifact runs and all six capture-era artifact runs have measured graph and fit timing.

## Exact anonymous projection audit

The capture-era projection matched the public anonymous port byte for byte on all three DS26 recordings. The three DS29 files use a different track order. All 350 DS29 tracks match by receiver, channel, tuned RF, timestamps and CFO values exactly, with zero CFO difference. The same robust EM decisions issued or withheld on every capture-era recording. The largest change in a diagnostic endpoint from the archived-order fit was 2.24 × 10⁻¹² km. The archived anonymous files were opened after the fresh fits for this comparison. [Reconstruction worker](../../../tools/pipeline_eval/qualification/raw_robust_worker.py) · [Component tests](../../../tests/pipeline_eval/test_raw_robust.py)

## Reproduce

```sh
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
taskset -c 10,11 .venv/bin/python -B -m tools.pipeline_eval.qualification.raw_robust \
  --fresh /tmp/raw-robust-fresh --cpus 10 11
taskset -c 17,18 .venv/bin/python -B -m tools.pipeline_eval.qualification.raw_robust \
  --detector ordinary-native --fresh-root /tmp/raw-robust-fresh \
  --work /tmp/raw-robust-numerics --cpus 17 18
taskset -c 17,18 .venv/bin/python -B -m tools.pipeline_eval.qualification.raw_robust \
  --detector capture-era --work /tmp/raw-robust-numerics --cpus 17 18
.venv/bin/python -B -m tools.pipeline_eval.qualification.raw_robust \
  --publish /tmp/raw-robust-report --work /tmp/raw-robust-numerics
.venv/bin/python -B -m tools.pipeline_eval.qualification.raw_robust \
  --score /tmp/raw-robust-report
```

The prior ordinary artifact option uses the same CLI with `--fresh-root` omitted and labels those rows as artifact-based. The two fresh runs reported here completed without that fallback.
