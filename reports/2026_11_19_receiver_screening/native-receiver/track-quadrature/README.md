# Eight Doppler samples for native joint orbit screening

Eight positive Gauss–Lobatto nodes reduced the orbit-time evaluations before joint fitting by **70.6%** and median process CPU from **5.280 to 4.655 seconds**. The six authenticated DS26 and DS29 captures all published in both calibration arms. The Lobatto and eight-point uniform modes reproduced every geographic endpoint and final orbit and alias assignment from the all-sample native joint receiver. The shared receiver missed the 10% original v5 accuracy gate in both arms. [Matched positions](charts/README.md) · [Measured stages](track-quadrature-actual-stage.pdf) · [Prediction seal](prediction-lock.json)

## Which work was removed

The Lobatto rule fits the actual, irregular time support of each track with positive weights, including its first and last samples. The degree-seven interpolant for orbit Doppler and phase derivative uses eight range-rate projections per orbit. A small QR transform evaluates the profiled score in the original correlated-noise metric. Each track keeps its actual RF and receiver lane. The uniform control interpolates over eight original samples equally spaced in sample index, with the same GLS metric and exact correction. All three modes evaluate short tracks with up to eight points directly. [Protocol](PROTOCOL.md)

The 16-orbit nomination budget stays fixed. Both compressed modes recompute visibility, Doppler, phase derivatives, and position gradients on every original point for each retained candidate. Downstream joint phase and alias assignment, synchronized held-block validation, paired RF nuisance fits, and nonlinear position corrections still run. Coarse sky propagation and the regional state grid also remain in the clock. These runs begin at the saved native GLRT archive and include integrity checks and fresh Graph reconstruction. IQ acquisition and the detector itself sit upstream of this boundary. [Stage times and work counts](stage.csv)

| Measured host work | All samples | Uniform eight | Lobatto eight |
| --- | ---: | ---: | ---: |
| All-orbit projection cells, six runs | 21,707,476 | 6,031,208 | 6,031,208 |
| Exact shortlist rescore cells, six runs | 0 | 345,872 | 345,872 |
| Exact final correction cells, six runs | 328,688 | 328,688 | 328,688 |
| Median screen CPU, including node packing and rescore (s) | 0.770 | 0.246 | 0.269 |
| Median worker CPU (s) | 5.280 | 4.686 | 4.655 |
| Median supervisor wall time (s) | 5.580 | 4.952 | 4.950 |

Lobatto reduced worker CPU by 0.127–0.626 seconds across all six matched runs. The paired median reduction was 0.548 seconds. Graph accounted for 2.792 seconds median CPU in the all-sample worker. That stage and the unchanged final fit limited full-worker savings. The two eight-node modes differ by 31 ms in median worker CPU and have mixed paired order, with one run per mode per capture. Peak resident memory across all 18 runs was 158.7 MiB, and peak virtual memory was 393.8 MiB under the 512 MiB address-space cap. [Stage CSV](stage.csv) · [Stage chart seal](stage-figure-lock.json)

## Shortlist parity and calibration

Lobatto recovered the exact all-sample candidate sets on **756/756 tracks**. Uniform recovered **753/756**, omitting one lower-ranked alternative in DS26-0084, DS26-0168, and DS29-0519. On DS26-0084 the changed held shortlist reduced one rival margin in each calibration arm while preserving the winning orbit, alias and frequency loss. All modes retained the same 714 final track assignments and 20,593 fit points. Of those assignments, 233 used a nonzero alias. No candidate was removed by the exact second visibility check on this roster. [Per-capture shortlist and alias audit](alias-and-shortlist-audit.json) · [Original-point assignment rows](positions.jsonl.gz)

Fitting calibration `c` reduced median conditional CFO RMS from **217.03 to 190.70 Hz** with the same final observations and discrete assignments. The median held compatibility score rose from 0.664 to 0.689 and the median held normalized mean loss rose from 3.589 to 3.806. Median geographic error increased from 1.158 to 1.270 km. The lower conditional frequency residual did not improve this roster’s median geographic error. [Per-arm frequency and geographic scores](scores.csv)

| Position result | c = 0 median / P95 (km) | Fitted c median / P95 (km) |
| --- | ---: | ---: |
| Native joint, each of the three modes | 1.158 / 3.888 | 1.270 / 3.963 |
| Original v5 baseline | 0.892 / 3.645 | 0.889 / 3.635 |
| Original v5 selective gap | 0.892 / 3.645 | 0.889 / 3.635 |
| Original v5 one omitted track | 0.826 / 3.645 | 0.873 / 3.635 |
| Original v5 omitted tracks | 0.826 / 3.645 | 0.873 / 3.635 |
| Archived compact v5 projector | 0.892 / 3.645 | 0.889 / 3.635 |

All methods were within 5 km on all six captures. Relative to the original v5 baseline, the native receiver’s median errors were 29.8% and 42.9% higher for zero and fitted `c`. Its P95 errors were 6.7% and 9.0% higher. DS26-0168 had the largest absolute increase, from 1.515 to 4.667 km with zero `c` and from 1.551 to 4.699 km with fitted `c`. DS26-0072 had the largest improvement. The compact projector was separately authenticated on the same stored GLRT archive, catalogue and tile and uses its own derived tracks and inference priors. Its historical worker clocks are recorded for provenance. Fresh matched speed claims apply to the native joint receiver. [Zero-c chart](charts/c0/modifications.pdf) · [Fitted-c chart](charts/fitted_c/modifications.pdf) · [Archived projector binding](archived-projector-binding.json)

## Replay

The capture hash selected six original roof offers from the frozen track inventory. The counts range from 1,526 to 4,674 points and from 61 to 151 tracks. Each mode used one of CPUs 14 and 15, one numerical thread, and a 180-second deadline per attempt. The three modes ran in rotated order and predictions were sealed before geographic scoring. No scheduled capture failed or withheld. Off-tile offers lie outside this roster. [Source and capture roster](source-lock.json) · [Score seal](score-lock.json)

```sh
work=/dev/shm/leo-track-quadrature-replay
out=/dev/shm/leo-track-quadrature-figures
.venv/bin/python -m tools.pipeline_eval.qualification.track_quadrature_trial lock "$work"
.venv/bin/python -m tools.pipeline_eval.qualification.track_quadrature_trial predict "$work" --output "$out"
.venv/bin/python -m tools.pipeline_eval.qualification.track_quadrature_results --output "$out"
```
