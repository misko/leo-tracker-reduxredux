# Complete saved-IQ replay through clock and track offsets

Both complete recordings ran from saved IQ through ordinary native GLRT, fresh streaming Graph, causal TLE propagation and the clock-plus-offset receiver. The fresh native factor bytes and new Graph digests exactly reproduced the independently sealed ordinary products. Every manifested visit entered the raw replay. The receiver retained the original attested invalid-capture decisions. No previously prepared detector factors or Graph tracks entered either candidate fit.

## Position and RF results

| Recording | Clock + offset, OU published error `c = 0` / fitted `c` | Compact v5 on the same ordinary factors | Original capture-era v5, no repair |
| --- | ---: | ---: | ---: |
| DS26-0036 | 0.654 / 0.739 km | 0.229 / 0.185 km | 1.278 / 1.208 km |
| DS29-0082 | Withheld / withheld | 2.784 / 2.651 km | 0.567 / 0.517 km |

The DS29 receiver withheld for `weak_held_track_support`. Its forced coordinates had errors of 2.379 and 2.305 km and remain diagnostic. The four original v5 options are no repair, selective gap, omit track one, and omit tracks. They share the causal catalogue with the new receiver and use their original capture-era factors. The compact v5 comparator shares the exact ordinary factor bytes, catalogue and original tile with the fresh clock-chain runs. The comparator and original v5 results come from independently measured, digest-verified prior runs. [Same-factor compact v5](same-ordinary-v5.jsonl.gz) · [Original v5 options](v5-options.jsonl.gz).

On DS26, fitting `c` reduced final raw RF RMS from 232.44 to 209.30 Hz and increased geographic error by 85 m. On DS29, final raw RF RMS fell from 260.24 to 214.02 Hz while both geographic arms withheld. Conditional held-suffix RMS for the combined OU model was 2,804.87 / 2,802.01 Hz on DS26 and 918.30 / 916.79 Hz on DS29. The same four-model worker also ran the diagonal combined model, clock-only OU, and offset-only OU from identical causal inputs, training and held assignments, aliases, and final support in both calibration arms. On DS26 the clock-only model published 0.404 / 0.212 km and the offset-only model 0.585 / 0.698 km. All four models withheld DS29. The observed position and RF outcomes describe two recording sessions.

## Fresh timing and coverage

| Measured stage | DS26-0036 | DS29-0082 |
| --- | ---: | ---: |
| Scheduled visits / processed / attested invalid | 6,769 / 6,765 / 4 | 6,772 / 4,868 / 1,904 |
| Compressed IQ read / decoded IQ | 8.157 / 10.830 GB | 8.405 / 10.835 GB |
| GLRT compute CPU, summed across lanes | 119.81 s | 84.12 s |
| Raw read, decode and GLRT wall | 83.51 s | 61.73 s |
| Factor assembly and validation wall | 0.690 s | 0.665 s |
| Fresh native factor probes / Graph input peaks | 13,530 / 3,610 | 9,736 / 2,044 |
| Native factor read and peak selection wall | 0.114 s | 0.083 s |
| Streaming Graph wall | 1.092 s | 0.489 s |
| Causal catalogue read / orbit propagation wall | 0.002 / 0.778 s | 0.002 / 0.241 s |
| Combined model final geometry stage wall | 0.172 s | 0.130 s |
| Sandbox worker wall, all four models | 7.703 s | 2.532 s |

The raw receipts include 84.155 s and 62.360 s of acquisition-through-assembly wall. Adding the separately timed downstream workers gives 91.858 s and 64.892 s of measured active stages, excluding inter-stage scheduling. Orbit propagation and individual fit timings are nested within the worker's total. The raw lane and fitter address limits were 768 MiB and 512 MiB respectively. The largest raw-lane resident high water was 175.1 and 179.3 MiB. The fitter peaks were 142.0 and 139.0 MiB. No RF was collected. CPUs 4 and 5 replaced the proposed 7 and 18 because those cores had active host work. The DS26 fitter overlapped the DS29 raw lanes, which affects wall time.

The fresh Graph and fit consumed the same exact native product, original tile, tracking configuration, cutoff and catalogue as the previous whole ordinary measurement. All four fresh models matched the training, held-prefix and final ownership digests. [Stage and worker receipts](stage-receipts.json) · [Prediction seal](prediction-lock.json) · [Figure seal](figure-lock.json).

## Verify or replay

`python -m tools.pipeline_eval.qualification.clock_chain_trial verify` checks the published prediction and figure seals, the parent authorities, and both capture and Graph receipts. The original [raw runner](source/clock_chain_raw.py.txt) and [trial runner](source/clock_chain_trial.py.txt) are stored as exact byte copies. Their SHA-256 digests are recorded in the published [source lock](source-lock.json). To rehash the fresh native files and verify the actual mounted inputs as well, supply `--work /srv/bulk/leo-dev/20261119-clock-chain-full` while those expanded files are available.

For another complete saved-IQ run, choose new paths for both directories. The runnable raw wrapper binds each capture's start times and expected factors when creating its callback. It records the raw runner SHA-256 in the working directory, and the fitting and packaging commands check that receipt against the new report's source lock. The published measurement and seals retain their original source identity.

```sh
work=/path/to/new-clock-chain-work
report=/path/to/new-clock-chain-report
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
export NUMEXPR_NUM_THREADS=1 BLIS_NUM_THREADS=1
taskset -c 4,5 python -m tools.pipeline_eval.qualification.clock_chain_trial lock --report "$report"
taskset -c 4,5 python -m tools.pipeline_eval.qualification.clock_chain_raw --work "$work"
for case in DS26-0036 DS29-0082; do
  python -m tools.pipeline_eval.qualification.clock_chain_trial fit --case "$case" --work "$work" --report "$report"
done
python -m tools.pipeline_eval.qualification.clock_chain_trial package --work "$work" --report "$report"
python -m tools.pipeline_eval.qualification.clock_chain_controls --report "$report"
python -m tools.pipeline_eval.qualification.clock_chain_trial verify --work "$work" --report "$report"
```
