# ARM real-time scoring budget

## Motivation

Fit high-recovery GLRT analysis onto one PLUTO+ core without confusing the
already real-time reduced detector with exhaustive original-hit recovery.

## Problem

The earlier reduced native profile sustained saved-IQ RAM replay at 69.24 ms
per 120 ms dual-receiver dwell. It confirms one selected window per receiver;
it is not the exhaustive eleven-window, eight-candidate search. Its 31/31
native-profile positives are not full-search individual-hit recovery.
See [the original replay report](../2026_09_28_arm_ram_pipeline/REPORT.md).

The high-recovery boundary-fallback search costs about 25 seconds per dwell.
Before investing in another discovery strategy, establish whether its final
scoring kernel could fit the 72 ms budget even with perfect proposals.

## Solution

An **oracle-seeded cost diagnostic**, not a usable detector: supply every
original baseline epoch and acquired frequency, ingest the actual saved IQ,
and execute the existing final GLRT kernel. Baseline scores are used only for
checking results and retrospectively counting the cost of positive entries.
Discovery, frequency refinement and conditioned fallback are deliberately
excluded. No detection recovery claim may be inferred from these seeded runs.

Two input preparation variants were also measured: direct CI16-to-workspace
conversion, and conversion of the complete dual-RX dwell once with overlapping
windows referencing the converted memory. CI16 values are finite and exactly
representable as FP64, eliminating the floating-input validation and second
copy. The final scoring kernel is unchanged.

## Method

PLUTO+ 192.168.1.15, CPU0 affinity, saved IQ in RAM, no RF collection or
simultaneous capture. Reuse the four metadata-selected 2.5 MS/s DS7 dwells
from the boundary-fallback benchmark. Four unique dwells contain 88 windows,
704 original candidate entries and 119 original positives. Execute three
repeats per variant: 2,112 candidate evaluations per variant, 6,336 total.

Every candidate retains its original epoch and acquired CFO. Exact/control
scores agree with the original baseline within 2e-9 and tracking CFO within
2e-6 Hz; all gate decisions agree. Repeated evaluations are not additional
independent detections. Coordinates are oracle inputs, so this is numerical
kernel validation, not a candidate-discovery experiment.

File reading, allocation and workspace/template initialization are outside
timing. Input conversion is timed separately and charged once. The shared
dwell variant adds a 9.6 MB FP64 dual-RX buffer; this is research-only pointer
sharing with the original allocation restored before workspace destruction.
Candidate times exclude output formatting. Positive-only costs sum the timed
positive calls from the all-candidate run; there is no implemented scheduler
that knows which calls will be positive in advance.

## Results

Mean CPU milliseconds per 120 ms dual-RX dwell:

| Variant | Input preparation | All 176 final scores | Oracle-positive scores only | Input + oracle-positive scores |
|---|---:|---:|---:|---:|
| Original per-window floating-input path | 150.549 | 486.907 | 82.798 | 233.347 |
| Direct per-window CI16 conversion | 60.981 | 485.815 | 82.587 | 143.568 |
| Convert dwell once; share windows | 36.781 | 484.336 | 81.870 | 118.651 |

Input preparation improves 4.09x (75.6% less CPU). This is not a 4.09x
end-to-end search speedup. No production code or full-search implementation
was changed. All scores include 64 pilot symbols, the original residual FFT,
exact/control templates and original frame support.

The input-plus-positive-only diagnostic still exceeds the 72 ms target by
1.65x, with **zero discovery cost charged**. Scoring all eight candidates per
window plus the improved input path costs 521.117 ms, 7.24x that budget.
These are observed costs of this kernel, not mathematical lower bounds on
all possible GLRT implementations. Exact duplicate-result reuse could reduce
work further; `verification.json` records a retrospective unique-key cost
using window, receiver, epoch and exact CFO bits, preserving entry counts.
For the shared-dwell variant, this reduces the oracle-positive scoring
estimate to 67.002 ms, or **103.783 ms including input preparation**: still
1.44x the target, before any discovery or negative-proposal work. This is a
retrospective reuse estimate, not a separately benchmarked cache variant.

Consequently, cheap discovery alone does not establish the desired capacity.
The next implementation needs both inexpensive candidate proposals and a
cheaper or incrementally shared final scorer, including the cost of cold
acquisition, negative proposals and fallback. Prior simple adjacent-window
tracking and raw-PSD proposals already failed the high-recovery target; do not
repeat those policies as if they were untested.

## Evidence and reproduction

- `probe.c`: benchmark source; `run.py`: build, transport and baseline checks.
- `run-v2`: original ingestion; `run-v3`: direct CI16; `run-v4`: shared dwell.
- Each run archives sources, ARM binary, compiler command, raw outputs, seeds
  and summary. `verify.py` independently reconstructs accounting and checks
  numerical parity, identities, source/binary hashes and remote template hashes.
- `run-v1` is an abandoned setup attempt that failed on an incorrect local
  NPY path before executing any measured candidates. It is not timing evidence.

From the repository root, use a new output directory on every invocation:

```sh
.venv/bin/python reports/2026_09_29_arm_scoring_budget/run.py run-new-original
.venv/bin/python reports/2026_09_29_arm_scoring_budget/run.py run-new-direct --direct
.venv/bin/python reports/2026_09_29_arm_scoring_budget/run.py run-new-shared --shared
.venv/bin/python reports/2026_09_29_arm_scoring_budget/verify.py
```

The verifier audits the published v2/v3/v4 runs. Reproduction requires the
frozen original DS7 baseline, local saved NPY inputs, the existing device IQ
and template directory recorded in the boundary-fallback manifest, cross
compiler and FFTW libraries. Input payload hashes and baseline hashes are
checked. The diagnostic supports four input rates in C, but only 2.5 MS/s is
qualified here; no higher-rate or capture-concurrency claim is made.
