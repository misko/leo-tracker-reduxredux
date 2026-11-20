# Fixing from the first 180 seconds

This is a contiguous capture test at full cadence. Each early trial takes every complete 20 ms visit ending by the original sample counter plus 1.8 billion ticks. The input still covers both physical receivers and all eight RF channels. Captured retune gaps, radio time, the UTC bracket and valid/invalid decisions carry through unchanged. The solver rebuilds observations, Graph tracks, satellite discovery and association from the shortened input. Both exposures use the supplied 25 km tile, the same compact v5 cavity solver and the same start-time causal catalogue. Its 300-second sky screen only propagates orbital elements already available at capture start. [Preregistered protocol](PROTOCOL.md) · [Source seal](seal.json) · [Exact paired solver sources](sealed-cavity-source.tar.gz)

## Six capture-era factor pairs

All six prefixes produced positions in both calibration arms. Fitted-calibration median error rose from **0.832 to 1.977 km**, and the number within 2 km fell from six to three. All six remained within 5 km. At `c = 0`, median error rose from 0.818 to 1.925 km, with the same counts at 2 and 5 km. The latest possible elapsed time for the final prefix delivery was 180.11–180.16 seconds from the recorded start bracket. Conditional first-fix estimates came in at **214–275 seconds**. [Full predictions](full-positions.jsonl.gz) · [Prefix predictions](prefix-positions.jsonl.gz) · [Scored pairs](scores.json)

| Recording | Full error `c = 0` / fitted `c` | Prefix error `c = 0` / fitted `c` | Full → prefix solver wall | Prefix solver CPU | Conditional first fix, latest |
|---|---:|---:|---:|---:|---:|
| DS26-0036 | 1.278 / 1.208 km | 2.482 / 2.622 km | 53.40 → 33.88 s | 33.66 s | 214.01 s |
| DS26-0122 | 0.751 / 0.747 km | 1.817 / 1.818 km | 158.70 → 89.19 s | 78.83 s | 269.31 s |
| DS26-0237 | 0.362 / 0.271 km | 0.919 / 0.765 km | 136.09 → 70.66 s | 63.50 s | 250.82 s |
| DS29-0082 | 0.567 / 0.517 km | 2.802 / 2.670 km | 45.39 → 43.11 s | 42.98 s | 223.26 s |
| DS29-0174 | 0.885 / 0.917 km | 0.802 / 0.770 km | 70.65 → 47.78 s | 41.71 s | 227.91 s |
| DS29-0247 | 1.320 / 1.458 km | 2.033 / 2.136 km | 170.21 → 94.44 s | 85.75 s | 274.59 s |

The median paired solver speedup was 1.68×, with a 1.05–1.93× range. Each pair used the same pinned core on a shared x86 host. The prefix contained 4,061–4,065 scheduled visits. It retained 37–96 tracks after rebuilding them, compared with 61–161 from full exposure. All six selected causal catalogues matched between exposures. Each prefix position used observations and tracks within the verified end counter. Fitting `c` lowered the prefix RF RMS in six cases and reduced position error in three. [Timing, causal receipts and track counts](prefix-positions.jsonl.gz) · [Frequency and position effects](scores.json)

## Two ordinary-native raw IQ replays

The raw replays ran the production capture-policy wrapper and ordinary fractional C GLRT on every valid visit in the prefix. The clock and all 14,026 newly generated probe rows matched the corresponding ordinary native archive exactly, including the 62,344 complete fractional candidates. The installed archive reader authenticated whole compressed chunks, so it also verified 35 and 33 trailing windows in the boundary chunks. Only in-prefix IQ reached GLRT and v5. Each full-exposure control ran the same compact cavity solver on the previously authenticated full ordinary-native factors. [Raw prefix predictions](raw-prefix-positions.jsonl.gz) · [Ordinary-native full controls](ordinary-native-full-positions.jsonl.gz) · [Scores and frequency fits](raw-scores.json)

| Recording | Valid / scheduled visits | Full error `c = 0` / fitted `c` | Prefix error `c = 0` / fitted `c` |
|---|---:|---:|---:|
| DS26-0036 | 4,059 / 4,061 | 0.231 / 0.186 km | 4.351 / 4.178 km |
| DS29-0082 | 2,954 / 4,063 | 2.802 / 2.662 km | 5.367 / 5.154 km |

| Recording | Latest prefix delivery from start bracket | Raw batch wall / detector CPU | Solver wall / CPU | Raw plus solver wall | Conditional first fix from start bracket |
|---|---:|---:|---:|---:|---:|
| DS26-0036 | 179.95–180.13 s | 70.64 / 105.62 s | 68.27 / 65.18 s | 138.91 s | 248.22–248.39 s |
| DS29-0082 | 179.97–180.14 s | 62.09 / 83.36 s | 45.55 / 43.48 s | 107.64 s | 225.51–225.69 s |

The batch wall times come from offline replay of stored IQ. The conditional first-fix time adds measured solver wall to the last recorded prefix delivery. It assumes the frontend computes factors during acquisition and delivers them to the solver when the last visit arrives. Both estimates fall before the recorded endpoint. The shortened native input increased the error on both recordings and crossed 5 km on DS29 in both arms. DS26's fitted-calibration RMS fell from 102.296 to 99.787 Hz as error rose from 0.186 to 4.178 km. Frequency fit and position error therefore move independently under this reduction. [Scores and frequency fits](raw-scores.json)

## Reproduction

The capture-era comparisons use the exact solver bytes in the preregistered seal. Copy the evaluation package into a scratch directory, restore the four sealed files there, and run the six matched cases with one numerical thread per case. This keeps concurrent solver development outside the timing trial.

```sh
repo="$PWD"
report="$repo/reports/2026_11_19_short_receiver/prefix"
scratch="$(mktemp -d)"
mkdir "$scratch/tools"
cp -a "$repo/tools/pipeline_eval" "$scratch/tools/"
ln -s "$repo/.venv" "$scratch/.venv"
tar -xzf "$report/sealed-cavity-source.tar.gz" -C "$scratch/tools/pipeline_eval/variants"

(
  cd "$scratch"
  env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 taskset -c "$CPU" \
    .venv/bin/python -B -m tools.pipeline_eval.qualification.contiguous_prefix_trial \
    --out "$OUT/$CASE" pair "$CASE" --seal "$report/seal.json"
)
.venv/bin/python -B -m tools.pipeline_eval.qualification.contiguous_prefix_trial \
  --out "$REPORT_OUT" score "$OUT"

env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -B -m tools.pipeline_eval.qualification.contiguous_prefix_raw \
  replay "$CASE" --out "$RAW_OUT/$CASE" --cpus "$RAW_CPU0" "$RAW_CPU1"
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 taskset -c "$CPU" \
  .venv/bin/python -B -m tools.pipeline_eval.qualification.contiguous_prefix_raw \
  full-control "$CASE" --out "$RAW_CONTROL_OUT/$CASE"
```
