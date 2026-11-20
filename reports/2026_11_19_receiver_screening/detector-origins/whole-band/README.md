# Frequency search from recorded IQ to position

Widening the fast GLRT frequency search from ±400 to ±800 kHz returned a position on all six recordings. With fitted calibration, three of six fixes met the target of at most 1.10 times that recording's original v5 error. The narrow search met it on one of six. Both new searches used the same four proposed start-time neighborhoods, the same receiver program and the original supplied region. DS26 and DS29 used one physical roof. [Fitted position distributions](../charts/fitted_c/whole-band-six.png) · [Zero calibration](../charts/c0/whole-band-six.png) · [Additional reserves](../charts/fitted_c/whole-band-reserve.png)

| Recording | Original v5, km | Narrow, km | Wide, km | Narrow / wide whole wall, s |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036, development | 1.208 | 0.180 | 0.935 | 150.9 / 118.8 |
| DS29-0082, development | 0.517 | 2.654 | 2.346 | 118.3 / 133.7 |
| DS26-0237, earlier confirmation | 0.271 | 0.814 | 0.323 | 194.2 / 215.7 |
| DS29-0174, earlier confirmation | 0.917 | 1.224 | 0.806 | 202.4 / 194.2 |
| DS26-0122, additional reserve | 0.747 | 1.329 | 1.318 | 212.0 / 198.1 |
| DS29-0247, additional reserve | 1.458 | Out of memory | 1.338 | 144.9 to failure / 136.2 |

The table uses fitted calibration and the original no-repair v5 reference. The plots include all four v5 options with paired recordings. Error decreases count as meeting either target. Each calibration arm used identical observations and search budgets within its method. The DS29-0247 narrow service reached every eligible visit and handed its factors to the position process. Linux recorded an out-of-memory kill at the 512 MiB limit. It contributes a failed attempt to the plotted denominator. [Every score](scores.csv) · [Resource and input receipts](resources.json) · [Protocol](PROTOCOL.md)

| Method | Fixes | Median returned error, km, zero / fitted | Within 5%, zero / fitted | Within 10%, zero / fitted | Median conditional Doppler RMS, Hz, zero / fitted |
| --- | ---: | ---: | ---: | ---: | ---: |
| Original v5, no repair | 6/6 | 0.818 / 0.832 | 6 / 6 | 6 / 6 | 99.95 / 93.74 |
| Narrow search | 5/6 | 1.161 / 1.224 | 1 / 1 | 1 / 1 | 110.25 / 110.12 |
| Wide search | 6/6 | 1.162 / 1.127 | 3 / 3 | 4 / 3 | 85.48 / 85.50 |

The wide detector lowered conditional Doppler RMS on each of the five jointly returned positions. On DS26-0036 the fitted RMS fell from 102.29 to 85.49 Hz while position error grew from 0.180 to 0.935 km. The changes in the selected peaks and orbit assignments make the RMS conditional on each method's own fit. [Per-recording RF and position scores](scores.csv)

Both detectors processed the same 38,641 eligible 20 ms dual-receiver visits. They preserved the same 1,989 capture exclusions, sampled waveforms, timestamps and probe identities across all six pairs. The narrow detector produced 100,769 passing peak records and the wide detector produced 110,458. Mean native CPU per eligible visit was 18.87 and 20.52 ms respectively. Across these full host services, 53.3% and 38.4% of native calls finished within 20 ms wall time. Each whole service used two pinned cores for replay, one for positioning, and a 512 MiB cgroup with zero swap. [Source identities](source-lock.json) · [Prediction seal](prediction-lock.json) · [Stage timings and call distributions](resources.json)

On the five pairs where both completed, total CPU increased from 1,115.66 to 1,177.31 s. Summed elapsed time was 877.72 and 860.63 s. Each whole service ran once per method and recording on the shared x86 host, with the order reversed on three recordings. Those elapsed measurements do not establish a repeatable speedup. Physical embedded throughput remains unmeasured. [Host and emulated Cortex-A9 detector trials](../wide-regional/README.md)

The subsequent full-IQ trial released the constrained-fit buffers on DS29-0247 and obtained a narrow-detector fix. Its prediction has a separate receipt and chart. The public replay command now also verifies the two installed C source files before reading the radio data. The compressed harness below reproduces the precise source hash in this study's lock. The stock installer used for these measurements is in commit `9012b76f6`. [Follow-up chart](../charts/fitted_c/whole-pressure.png) · [Measured harness](measured-whole-iq.py.gz)
