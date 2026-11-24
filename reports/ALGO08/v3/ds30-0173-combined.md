# Combined successor on blind DS30-0173

Both workers fixed the fifth hash-enrolled DS30 case. The frozen
combined solver completed in **15.256 wall s**, compared with
**26.796 s** for installed ALGO08v3. Horizontal error fell by
**108.762 m** at fixed zero and **126.593 m** with fitted `c`.
Across the two independent cases measured on this same combined
build, both workers fixed **2/2** and the candidate improved both
calibration arms on both recordings. Summed saved-worker wall time
fell from **47.563 to 27.122 s**. [Frozen assignment and input](ds30-0173-combined-protocol.md) ·
[Earlier blind case](ds30-0163-combined.md)

## Input admission and actual clocks

The original signed 20 ms packet includes **6,773 issued**, **4,733
admitted**, **9,466 radio probes** and **3,393 factors**. Both
workers used its original inventory, 25 km operator offer and
cutoff. The local NVMe collector supplied all **51** signed causal
files, **91,144,362 bytes**. Verification and copying took
**0.060 wall / 0.051 CPU s** and charged **5,369,856 physical input
bytes** to the staging process. All admitted input files were
resident for the children. No original waveform or RAID access
entered the study.

The actual isolated `python -IB` candidate probe and installed
entry help probe both returned zero before either measured worker.
Their wall clocks were **0.053 / 0.049 s**, respectively. The
shared admission charges both probes, the complete validated archive
and runtime preparation. The candidate then ran first as assigned.
Both children ran under one Gauss lease on CPU 2, nice 15, I/O
priority 7 and one numerical thread. Their process-wide input
blocks were 1,032 and 12,296, with 15 and 131 major faults, in that
order. The counters do not attribute traffic to files. The earlier
installed raw clock of **101.711 s** includes acquisition and stays
outside this saved measurement.

| Paid scope | Installed wall / CPU s | Combined wall / CPU s |
| --- | ---: | ---: |
| Local input admission | 0.597 / 0.539 shared | 0.597 / 0.539 shared |
| Warm checks including both smoke processes | 0.163 / 0.111 shared | 0.163 / 0.111 shared |
| Numerical solve, including preparation and grid | 22.308 / 22.211 | 11.834 / 11.803 |
| Official publication within the worker, including solve | 25.077 / 24.980 | 13.887 / 13.848 |
| **Child through verified exit** | **26.796 / 26.630** | **15.256 / 15.215** |
| **Child plus complete common admission** | **27.556 / 27.280** | **16.016 / 15.865** |

## Route, repair and outputs

The combined worker charged **2.270 s** for regional preparation
and **1.890 s** to evaluate its two nomination centres. The latter
produced three distinct finalists. The guard excluded the speculative
rank and prefix set from the trusted handoff. The cold race found an
ambiguous gap. The existing paired repair retained both arms after
removing **67 of 2,114 curved rows**, no predictive rows, and one
of 78 tracks. Repair preparation and its two refits took **0.101
and 0.210 wall s**. No named rollback, checkpoint consumption or
live orbit extension occurred.

The native standard grid covered **179 points** in **2.427 s**,
including **356** template assemblies, **708** native projections,
356 selections, four exact projection checks and two exact assembly
checks. The worker used the identical compiled libraries and
scientific source pins as DS30-0163.

| Calibration | Installed horizontal error | Combined horizontal error | Installed conditional RF RMS | Combined conditional RF RMS |
| --- | ---: | ---: | ---: | ---: |
| Fixed zero | 1,367.309 m | 1,258.548 m | 124.241526 Hz | 126.416450 Hz |
| Fitted | 1,373.967 m | 1,247.373 m | 124.070843 Hz | 126.276594 Hz |

The paired c arms within each worker used the same support and
ordered owner rows. Relative to installed, the candidate retained
**2,458 of 2,590** rows per arm and dropped 132. It added no rows
and changed no retained satellite identity or role. Horizontal
error and conditional RF RMS moved in opposite directions across
workers. Both workers published complete grids with zero endpoint
replay error, the fit paths and eight individually verified PNGs.
The candidate outputs differ from installed in both positions,
grid, path and all images. The fresh installed child exactly
reproduced the archived terminal, owners, RF fits, grid, path and
all eight encoded and decoded PNGs.

## Independent cohort on this build

| Case | Actual measured order | Installed wall s | Combined wall s | Horizontal error difference, fixed / fitted |
| --- | --- | ---: | ---: | ---: |
| DS30-0163 | Installed, combined | 20.767 | 11.866 | −7.408 / −4.747 m |
| DS30-0173 | Combined, installed | 26.796 | 15.256 | −108.762 / −126.593 m |
| **Both** | Two clock pairs | **47.563** | **27.122** | Two comparable pairs per arm |

There were zero withdrawals, withholds and failed measured workers
in this two-case denominator. One earlier DS30-0163 candidate
startup failed before opening its scientific job. That **0.053 s**
attempt and resulting order deviation are retained separately.

| Pooled paid boundary | Installed wall / CPU s | Combined wall / CPU s | Summed wall / CPU ratio | Reciprocal median wall / CPU ratio |
| --- | ---: | ---: | ---: | ---: |
| Through verified child exits | 47.563 / 47.375 | 27.122 / 27.077 | **1.754× / 1.750×** | **1.753× / 1.750×** |
| Including shared admissions for each case | 50.154 / 49.529 | 29.713 / 29.231 | **1.688× / 1.694×** | **1.684× / 1.692×** |

Adding the failed start only to the candidate's admission-charged
time gives **29.766 wall s**, **1.685×** by summed time and
**1.681×** by the reciprocal median paired wall ratio. The
order-deviating 0163 entry remains visible in each reduction.
These are two saved cases. The older variant's independent cases,
the 0289 combined development run, raw acquisition and Cairo
qualification are outside this denominator.

The workers froze in `32ff01a2f72364e5c8892c7c7fea1930c5def606`.
The two predictions sealed before scoring at
`5d0986b9ca7feb19e209044dada76d62d933f5851eae4fd86a9a872f8a173d3b`.
Thirty-eight component and adjacent tests passed.
[Case driver](ds30_0173_combined.py) ·
[Shared launcher and scorer](ds30_0163_combined.py) ·
[Tests](../../../tests/pipeline_eval/test_ds30_0173_combined.py) ·
[Machine receipt](measurements/ds30-0173-combined.json.gz),
uncompressed SHA-256
`e2a7eb8a10886c3de720e1ab97d7efbdfd706161b67f06aa6249417083c4c180`.
