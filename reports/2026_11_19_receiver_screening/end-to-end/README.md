# Recorded IQ to a compact secant position

Two fresh whole-recording replays returned both calibration-arm fixes in **134.82 s** and **111.86 s** of elapsed time. The captures span 300 s each. The same freshly generated ordinary detector factors then went through stock compact v5. The secant fit reduced downstream wall time by 28% on each recording and moved the matched endpoints by 9.6–20.9 m. The two recordings show opposite geographic effects from substituting the ordinary detector for the capture-era source. [Protocol](PROTOCOL.md) · [Sealed inputs and timing receipts](prediction-lock.json) · [Both calibration arms](scores.csv)

## Measured replay

Each chain starts before authenticated CI16 replay and stops when the secant position worker returns both arms. It includes both ordinary native detector lanes, complete fresh factor assembly, graph tracking, causal TLE projection, and compact v5 cavity inference. The stock comparison ran immediately afterward on the same factor bytes. The two worker requests match after removing their output-directory field, including the original 25 km tile, causal catalogue, and numerical priors. No evaluation coordinates were available to either solver. [Stage receipts and matched request digests](stage-receipts.json)

| Recording | Recorded span (s) | IQ read (GB) | Valid / excluded visits | Whole secant chain wall / CPU (s) | Wall s per recorded s | Secant fit wall / CPU (s) | Stock fit wall / CPU (s) |
|---|---:|---:|---:|---:|---:|---:|---:|
| DS26-0036 | 299.996 | 10.8304 | 6,765 / 4 | 134.82 / 205.76 | 0.449 | 44.34 / 43.08 | 61.67 / 59.48 |
| DS29-0082 | 300.018 | 10.8352 | 4,868 / 1,904 | 111.86 / 166.73 | 0.373 | 36.69 / 34.48 | 50.95 / 38.77 |

The read and detector envelope consumed about two thirds of each whole-chain wall time. The ordinary detector separately metered 127.77 and 95.64 CPU seconds inside the two lanes. Both factor files were SHA-256-identical to the independent earlier whole-IQ replays. Fresh graph preparation included 104 tracks and 3,610 observations on DS26-0036 and 70 tracks and 2,044 observations on DS29-0082. [Secant predictions](positions.jsonl.gz) · [Matched stock predictions](stock-positions.jsonl.gz)

| Secant chain stage | DS26-0036 wall / CPU (s) | DS29-0082 wall / CPU (s) |
|---|---:|---:|
| Authenticated IQ read and ordinary GLRT lanes | 89.58 / 161.80 | 74.32 / 131.54 |
| Complete factor assembly and request binding | 0.87 / 0.85 | 0.83 / 0.69 |
| Native factor decode in fit worker | 0.23 / 0.13 | 0.10 / 0.09 |
| Fresh graph tracks | 1.49 / 1.38 | 0.69 / 0.69 |
| Remaining native, sky and history preparation | 11.94 / 11.45 | 16.26 / 15.31 |
| Compact v5 numerical inference | 27.34 / 26.78 | 15.97 / 14.80 |

The fit envelope also includes compilation, worker startup and result handoff. The worker breakdown records initial position, conservative recovery, family history, signed context and cavity operations. The fit envelope, its constituent stages and the complete chain are nested clocks. Both measurements used host CPUs 0 and 1 with single-threaded BLAS. Time for both fits plus the single read was 196.51 s and 162.82 s, respectively. This qualification measures two host runs with the secant fit first and the stock fit second.

The compact position worker recorded a process RSS high-water mark of 1,036,384 KiB and 916,092 KiB in the secant runs, and 1,039,056 KiB and 919,864 KiB in the stock runs. The whole-chain receipts include cumulative parent and waited-child high-water marks. Those counters cannot resolve simultaneous memory across the two raw processes or isolate a stage-local raw peak. The first secant receipt predates adding the explicit invocation count to each stage, with the same timing boundaries and scientific worker. [Full measured stages](positions.jsonl.gz) · [Whole-chain process counters](stage-receipts.json)

## Geographic and RF comparison

Each entry gives `c = 0` followed by fitted `c`. All four fresh solver outputs returned both arms. Distances in kilometres use the independent surveyed receiver locations, after results were sealed. Capture-era positions are the four original v5 reference outputs for these recordings. [Capture-era reference positions](capture-era-reference-positions.json) · [Earlier exact capture-era v5 confirmation](../../2026_11_19_receiver_streaming/finish/README.md)

| Recording | Fresh ordinary + secant | Same ordinary + stock | Era no-repair | Era selective-gap | Era omitted-track-one | Era omitted-tracks |
|---|---:|---:|---:|---:|---:|---:|
| DS26-0036 | 0.218 / 0.180 | 0.231 / 0.186 | 1.278 / 1.208 | 1.278 / 1.208 | 1.278 / 1.208 | 1.278 / 1.208 |
| DS29-0082 | 2.789 / 2.654 | 2.802 / 2.662 | 0.567 / 0.517 | 0.567 / 0.517 | 0.115 / 0.486 | 0.115 / 0.486 |

Fitting `c` lowered secant position error by 38 m on DS26-0036 and 135 m on DS29-0082. Conditional Doppler RMS rose from 102.253 to 102.289 Hz on DS26-0036 and fell from 106.672 to 106.588 Hz on DS29-0082. On matched inputs within each arm, secant reduced conditional RMS by up to 0.0072 Hz relative to stock. Both recordings meet the earlier numerical comparison limits of 50 m and 1 Hz in both arms. With fitted `c`, the ordinary compact stock fix gained about 1.02 km on DS26-0036 relative to capture-era no-repair and lost about 2.14 km on DS29-0082. The paired numerical optimizer change is much smaller than those differences between complete receivers. [Geographic errors, conditional RF RMS and optimizer displacement](scores.csv) · [Earlier numerical comparison limits](../../2026_11_19_receiver_convergence/position-fit/PROTOCOL.md)

## Reproduce

Run each case in sequence with a fresh local output directory and the original read-only recording inventory mounted. Publication compares both solver requests and seals all positions before the separate truth read.

```bash
for case in DS26-0036 DS29-0082; do
  env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    taskset -c 0,1 .venv/bin/python -B -m tools.pipeline_eval.qualification.secant_end_to_end \
    --replay /tmp/leo-secant-end-to-end --case "$case" || break
done
.venv/bin/python -B -m tools.pipeline_eval.qualification.secant_end_to_end \
  --publish /tmp/leo-secant-published --source /tmp/leo-secant-end-to-end
.venv/bin/python -B -m tools.pipeline_eval.qualification.secant_end_to_end \
  --score /tmp/leo-secant-published
```
