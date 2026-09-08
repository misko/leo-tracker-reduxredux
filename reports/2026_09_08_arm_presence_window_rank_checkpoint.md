# Whole-dwell screening and frame-contract checkpoint

Date: 2026-09-08. **Implementation progress, not a deployed classifier.**
The goal remains realtime per-dwell Starlink classification carried in LIBIIO
frame data without reducing scanner duty. No RF collection, production change,
FPGA/kernel change, or flashed-firmware change occurred in this checkpoint.

## Results and decision

Two independent pieces now exist:

1. A versioned C/Python frame codec and a fault-isolated host binding, committed
   as `fec7ecfc`. Its 74 tests pass, and the C codec cross-compiles for ARM.
   These modules do **not** yet change the installed LIBIIO transport.
2. A native whole-120ms window-ranking screen with exact CI16 lag accumulation,
   optional exact ARM NEON acceleration, and FP32 proposal FFTs. Fractional
   GLRT remains unchanged and is still required for confirmation.

The smallest screen grid measures about **20.0/40.01 ms CPU p99** on ARM at
2.5/5 MS/s, before confirmation. All 1,000 optimized ARM outputs match desktop
exactly, including scores, selected order, and projected epochs.

Selecting one window improves reference-associated coverage from 15/35 to
20/35 development dwells. Selecting three reaches 28/35, versus 30/35 for the
existing detector run on all six. This is **not sufficient to qualify the
single-window policy**, and executing multiple unchanged confirmations is not
qualified within the compute budget. No screen-only result is a Starlink verdict.

## Full-dwell experiment

Each retained 120 ms single-RX dwell is divided into six 20 ms intervals.
For each interval, lag-four products are folded on independently rounded frame
starts, mean-centered after circular projection, and correlated with the Qin
pilot differential template. The maximum normalized correlation ranks windows.
No reference epoch/CFO, previous visit, or score label influences selection.

This tests grids of 512, 1024, 2048, 4096, and 8192 bins. Projection to a smaller
grid is an approximation, not lossless decimation. A projected epoch is a
proposal, not fractional timing evidence. A score's normalization is not a
probability or an independently calibrated false-alarm threshold.

The complete previously examined corpus is 96 dwells / 576 probes from four
scans, RX1 only, with both rates and all eight channel edges. It is explicitly
**development data for this new algorithm**, not a newly untouched holdout.
Recorded fractional GLRT outputs are looked up only after ranking. The tool
checks source hashes, template bytes, counters, contiguous six-window geometry,
and recomputes the saved reference/association labels before reporting counts.

For the 512-bin screen, which had the best combined single-window association
count among the tested grids:

| Confirmation policy | Reference-positive dwells whose selected windows contain reference evidence | Dwells with a native reference association |
|---|---:|---:|
| First window only | 15/35 | 15/35 |
| Ranked top one | 23/35 | 20/35 |
| Ranked top two | 26/35 | 24/35 |
| Ranked top three | 31/35 | 28/35 |
| All six windows | 35/35 | 30/35 |

The 35-dwell denominator comprises 22 at 2.5 MS/s and 13 at 5 MS/s. Top-one
associations are 14/22 and 6/13. There are also 21 dwells with selected-window
native flags but no selected-window reference association. These are unresolved
RF flags, not established false alarms or established new detections. Dense
reference evidence is itself not independent signal truth; these counts do not
establish sensitivity/specificity with independent confidence intervals.

The [complete grid comparison](evidence/2026_09_08_arm_presence_window_rank/development-summary.json)
and [per-dwell outputs](evidence/2026_09_08_arm_presence_window_rank/development-results.jsonl)
retain unsuccessful settings rather than only the best result.

## Actual ARM measurements

Saved IQ was replayed on spare serial `104000b29905000e17000800065934759d`,
over its pinned SSH connection at `192.168.1.15`. The excluded serial was not
accessed. The replay executable contains no IIO calls or radio-control path.
Inputs and binaries stayed in an owned temporary directory.

The optimized comparison is **10 inputs × 5 grids × 20 executions = 1,000**:
eight recorded dwells (first two in metadata order per rate/edge) plus two
synthetic CI16-extrema inputs. Thus 1,000 does not mean 1,000 distinct RF dwells.
Inputs and templates load before timing; the screen processes all 120 ms on
each invocation. This is not DMA/metadata-arrival replay or a concurrent live
acquisition measurement. Runs use one process at nice 19, with no affinity
reservation, and bounded 30 s wall / 25 s CPU / 64 MiB address-space limits.

Recorded-input results for the exact-integer NEON version:

| Proposal bins | 2.5 MS/s mean / p99 CPU | 5 MS/s mean / p99 CPU |
|---|---:|---:|
| 512 | 16.6 / 20.0 ms | 34.1 / 40.01 ms |
| 1024 | 19.7 / 24.7 ms | 37.1 / 40.1 ms |
| 2048 | 26.0 / 30.0 ms | 43.6 / 50.0 ms |
| 4096 | 39.7 / 49.9 ms | 58.3 / 69.8 ms |
| 8192 | 73.6 / 80.0 ms | 93.0 / 100.02 ms |

CPU timing is visibly quantized on this ARM; these are small-sample repeated-
input observations, not worst-case guarantees. The
[verified summary](evidence/2026_09_08_arm_presence_window_rank/verified-neon.json)
also retains wall-time tails, per-stage times, and separate extrema controls.
All pre/post checks around each of the 50 optimized replay invocations found
the identity correct and both receive buffers disabled. The original scalar
experiment completed 800 outputs but its final combined guard returned status
1 without identifying the failed check. Immediate subsequent read-only checks
found the expected serial, both buffers disabled, and no replay process. That
earlier run is retained as context, not clean-idle qualification.

The optimized ARM binary SHA-256 is
`d945873d16b2ebdc28923b777177b5ae24852030ba4d756c4f938be53aaa717c`.
The retrieved ARM output SHA-256 matches its remote value:
`d4a12d6f38e8b4e0f79c7ccc21111f06ee0ef754bc70960d39ae5c803043bf5a`.
Build receipts and raw scalar/optimized outputs are stored beside the summary.
No binaries or raw IQ are included in Git.

## Frame metadata and host binding

The new opt-in envelope preserves existing legacy metadata as opaque bytes.
It carries bounded batches of results keyed to their original session,
generation, visit, RX, channel/edge, rate, and exact sample-counter interval.
Fractional timing remains separate from the integer epoch, including counters
above 2^53. Algorithm/configuration hashes and explicit loss accounting prevent
silently applying stale or different classifier settings.

A host binding validates every result against independently attested hop
geometry. Recoverable classification errors disable classification while
passing through unchanged IQ and legacy metadata; they do not fabricate
negative results. Metadata-only drain/final frames are encoded and tested,
but implementing them in the pinned LIBIIO client/provider is still required:
the current client rejects zero-IQ frames.

## Tests and next implementation step

640 focused numerical, worker, frame/host, ranking, packet, and accounting tests
pass. Ranking tests include an independent FP64 NumPy oracle, every temporal
slice, both edges/rates, CI16 extrema, degenerate templates, stable ties, caller
IQ immutability, incomplete inputs, and counters above 2^53. The ARM verifier
requires every expected identity/grid/iteration exactly once and rejects
changed ordering, epochs, nonfinite values, malformed geometry, and timing.
An ASan/UBSan-instrumented shared library completed all ten replay inputs at
all five grids (50 full-dwell screens) without diagnostics; leak checking was
disabled for the embedding Python runtime. The
[execution receipt](evidence/2026_09_08_arm_presence_window_rank/execution-receipt.json)
records scope, identities, guards, and the unresolved scalar-run caveat.

The next useful experiment is **reusing the screen's timing proposals in
fractional confirmation**, with explicit local uncertainty search, instead of
paying the existing full coarse-search cost again. It must be measured end to
end and compared with the frozen blind detector. Improved window selection or
bounded additional confirmations may still be necessary; neither sensitivity
nor speedup is assumed. Existing screen settings remain research comparators.

Still unfinished: qualified whole-dwell decisions; integrated ARM confirmation
budget; full-dwell collector/worker sizing; actual negotiated LIBIIO transport
and final drain; host persistence/UI wiring; original capture-arrival replay;
authorized live duty comparison; release/rollback and deployment. No task
completion, unchanged-live-duty claim, or deployment is asserted here.
