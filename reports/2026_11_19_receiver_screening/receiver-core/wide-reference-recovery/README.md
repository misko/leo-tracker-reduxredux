# Original-v5 numerical repeat on the same wide inputs

The official wide-factor run on DS26-0122 exceeded its 600-second deadline before publishing its final artifact. That outcome remains in the original report. This separately preregistered run used the existing `v5_lean` entry to obtain the final scientific selection without generating the full evidence archive. DS29-0082 was included as the independent positive check against the successful full original-v5 worker. [Primary wide-factor study](../wide-full-v5/README.md)

The repeats use the exact same native-factor bytes, original no-repair policy, tile, tracking settings, causal TLE members, calibration arms and frozen numerical engine. The copies to local ext4 changed only external paths. Both repeats ran on CPU 3, one numerical thread, nice 10, under enforced 4 GiB with zero swap and a 420-second cap. Original late recovery, admission and final decision still run. [`v5_lean` source](../../../../tools/pipeline_eval/variants/v5_lean.py) · [Protocol](PROTOCOL.md) · [Source lock](source-lock.json)

Initial staging flattened the copied TLE provider directory. The frozen archive reader could authenticate the file bytes but found no causal snapshots in that layout. Those two exits occurred before the fit. The corrected copy preserves the original provider directory structure. Setup failures and their source lock are retained separately. [Setup failures](setup-failures.json)

Fresh predictions were sealed before pairing with the primary outputs or opening the geographic references. Position error, conditional RF RMS and frequency scores are reported separately. The four capture-era v5 references use their archived observations. The direct inference comparison uses the exact same wide factors in all three same-input roles. [Prediction seal](prediction-lock.json) · [Paired authority](comparison-source.json) · [Scores](scores.csv) · [Both-arm charts](charts/index.html)

## Measured results

The numerical repeat returned both positions on DS26-0122 in 199.29 s. The exact same wide factors put compact 13.19 m and 15.07 m from the recovered original coordinates in `c = 0` and fitted-`c` order. Compact's errors were slightly lower than the recovered original's in both arms. The roughly 0.6 km geographic degradation against the capture-era v5 policies therefore remains when using the full original numerical stages on these wide factors.

| Recording | Calibration | Recovered original error km | Same-wide compact error km | Capture-era no-repair v5 error km | Capture-era omitted-track option error km |
| --- | --- | ---: | ---: | ---: | ---: |
| DS26-0122 | `c = 0` | 1.32150 | 1.32046 | 0.75144 | 0.67915 |
| DS26-0122 | Fitted `c` | 1.32048 | 1.31835 | 0.74685 | 0.67677 |
| DS29-0082 | `c = 0` | 2.49573 | 2.48917 | 0.56695 | 0.11542 |
| DS29-0082 | Fitted `c` | 2.34913 | 2.34573 | 0.51723 | 0.48617 |

The DS29-0082 positive check finished in 80.71 s. Its coordinates, associated observation counts, frequency scores and conditional RF RMS are exactly equal to the successful original full worker in both arms. The official evidence has 1,070 conditional and 346 predictive rows per arm. Recomputing conditional RMS from the sealed official rows gives 84.425805 and 84.248587 Hz. The official combined residuals, 137.947568 and 94.167738 Hz, remain separate. [Paired numerical checks](parity.json) · [Original residual evidence](original-residuals.json)

The repeats used 193.38 and 79.42 cgroup CPU seconds, with peak charged memory 2.18 and 1.84 GiB and no swap. Scientific-stage elapsed times also differed from the earlier worker, whose remaining evidence duties were only one contributor to the full 600-second timeout. These measurements establish the recovered prediction on the unchanged no-repair numerical path. [Resource receipts](resources.json)
