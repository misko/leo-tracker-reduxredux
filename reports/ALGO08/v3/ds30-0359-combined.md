# Combined successor on blind DS30-0359

The sixth hash-enrolled case fixed in **17.171 s** with the frozen
combined solver and **31.947 s** with installed ALGO08v3. Both
workers returned exactly the same positions, RF RMS, ordered owners,
179-location grid and fit path. Across three independently assigned
cases on this build, both workers fixed **3/3**. Summed saved-worker
wall time fell from **79.510 to 44.293 s**, a **1.795×** speedup.
Including local input admission, the speedup was **1.739×**.
[Frozen assignment and input](ds30-0359-combined-protocol.md)

## Signed inputs and paid clocks

Both workers used the same original signed full-20 ms packet,
inventory, 25 km operator offer and causal cutoff. The packet
contains **6,774 issued visits**, **5,160 admitted visits**,
**10,320 radio probes** and **4,941 factors**. The 47 causal archive
files, **83,998,561 bytes**, came from two already resident tmpfs
stages. Direct hard links preserved the signed roster and all body
digests. Linking and verifying took **0.033 wall / 0.033 CPU s**,
within cold admission, with zero new archive copy bytes and zero
process-charged device bytes at archive staging. The run made no
waveform, RAID or archive backing reads.

Both isolated entry probes passed before either timed child. The
installed help probe took **0.044 s** and the candidate's signed
job probe **0.050 s**. The candidate ran first as assigned. Both
children ran under one Gauss lease on CPU 2 with nice 15, I/O
priority 7 and one numerical thread. The candidate recorded zero
process input blocks and major faults. Installed recorded 336
input blocks and three major faults. These process counters have
no file-level attribution. The historical installed raw clock of
**89.017 s** includes acquisition. This comparison starts from
saved detector output.

| Paid scope | Installed wall / CPU s | Combined wall / CPU s |
| --- | ---: | ---: |
| Local input admission | 0.597 / 0.548 shared | 0.597 / 0.548 shared |
| Warm guard and both smoke processes | 0.153 / 0.103 shared | 0.153 / 0.103 shared |
| Numerical solve, including preparation and grid | 27.289 / 25.367 | 13.454 / 13.408 |
| Official publication within each worker, including solve | 30.311 / 28.389 | 15.794 / 15.748 |
| **Child through verified exit** | **31.947 / 30.024** | **17.171 / 17.123** |
| **Child plus complete common admission** | **32.698 / 30.675** | **17.921 / 17.774** |

## Route and verified outputs

The candidate spent **2.395 wall / 2.394 CPU s** on regional
preparation. The regional reader verified 134 reads over 41
distinct bodies and used 22,494 distinct scan objects. The
history census chose lean from the two qualifying earlier
catalogues. Evaluation of both nomination centres cost **2.481
wall / 2.436 CPU s** and produced three distinct finalists.
The guard excluded one speculative rank and one speculative
prefix set from the named handoff. The cold race reported an
ambiguous gap. The lean path completed with both named survivor
refits accepted, costing **0.543 and 0.552 s** for fixed and fitted
`c`. There was no named rollback, nomination checkpoint reuse,
live orbit extension or exterior veto evaluation.

| Calibration | Installed horizontal error | Combined horizontal error | Installed conditional RF RMS | Combined conditional RF RMS |
| --- | ---: | ---: | ---: | ---: |
| Fixed zero | 592.489 m | 592.489 m | 115.604323 Hz | 115.604323 Hz |
| Fitted | 666.751 m | 666.751 m | 115.588647 Hz | 115.588647 Hz |

Each calibration arm kept the same **3,640 ordered owners** in
both workers, with zero additions, drops, changed roles or NORAD
reassignments. Fitting `c` lowered conditional RF RMS by **0.0157
Hz** and increased horizontal error by **74.262 m** in both
workers. Both complete grids had zero endpoint objective replay
error. The routed grid took **3.774 s** for all 179 locations,
including 356 template assemblies, 708 native projections,
356 selections, four exact projection checks and two exact
assembly checks. The numerical grid and fit path digests matched
after separating the position figure binding.

Both workers exited zero and published eight PNGs. The four
ordinary orbit figures matched byte for byte. The two residual
figures, position figure and track RMS figure used the switched
renderers and differed. The fresh installed worker exactly
reproduced the archived signed terminal, both arms, all owners,
grid, path and eight encoded and decoded PNGs.

## Three independent saved pairs on this build

| Case | Actual measured order | Installed wall s | Combined wall s | Horizontal error difference, fixed / fitted |
| --- | --- | ---: | ---: | ---: |
| DS30-0163 | Installed, combined | 20.767 | 11.866 | −7.408 / −4.747 m |
| DS30-0173 | Combined, installed | 26.796 | 15.256 | −108.762 / −126.593 m |
| DS30-0359 | Combined, installed | 31.947 | 17.171 | 0.000 / 0.000 m |

There were three measured clock pairs and three comparable
position pairs in each calibration arm. Both workers fixed all
three cases, with zero withdrawals, withholds and failed
measured workers. DS30-0173 still incurred conditional RF RMS
increases of **2.175 / 2.206 Hz** and dropped 132 owner rows in
each arm despite its geographic improvements. The DS30-0163
candidate's **0.053 wall / 0.052 CPU s** failed import before its
scientific job caused the recorded reversal in measured order.
[DS30-0163](ds30-0163-combined.md) · [DS30-0173](ds30-0173-combined.md)

| Pooled paid boundary | Installed wall / CPU s | Combined wall / CPU s | Summed wall / CPU ratio | Reciprocal median wall / CPU ratio |
| --- | ---: | ---: | ---: | ---: |
| Through verified child exits | 79.510 / 77.399 | 44.293 / 44.201 | **1.795× / 1.751×** | **1.756× / 1.750×** |
| Including common admission for each child | 82.852 / 80.204 | 47.634 / 47.005 | **1.739× / 1.706×** | **1.721× / 1.720×** |
| Also charging the failed start to the candidate | 82.852 / 80.204 | 47.687 / 47.057 | **1.737× / 1.704×** | **1.721× / 1.720×** |

The reciprocal median is one divided by the median per-case
candidate-to-installed time ratio. The older candidate's other
cases, combined development on DS30-0289, acquisition and raw
file benchmarks are outside this denominator.

The experiment ran with freeze
`0faad684194e49e78c59b35d96631e8d42228c15`, using scientific
source `ad319307d` with telemetry correction `d0f399eb1` and the
same native libraries as ranks four and five. Predictions sealed
before scoring at
`0f7fac1871530a19a67dd2a6a425d290f1354c6cff51211a8635dedcab3f2763`.
Forty component and adjacent tests passed.
[Case driver](ds30_0359_combined.py) ·
[Shared launcher and scorer](ds30_0163_combined.py) ·
[Tests](../../../tests/pipeline_eval/test_ds30_0359_combined.py) ·
[Machine receipt](measurements/ds30-0359-combined.json.gz),
uncompressed SHA-256
`f226ee36a27b16fcd0b99b375a9a9fe22e56fa34531eec5e3fb1253173bd08da`.
