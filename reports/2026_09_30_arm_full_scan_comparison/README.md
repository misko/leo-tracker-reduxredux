# Full saved-scan ARM / standard-server GLRT comparison

Both detectors freshly processed all 2,215 original dwells in
`scan-fw-f363c7f29141d0b1`: 299.8609428 seconds of capture, 2.5 MS/s,
dual receivers, lower-edge channels 1–4. Each 120 ms dwell contributes its first
20 ms per receiver, giving 4,430 receiver windows. Every raw-IQ hash and complete
recording event agrees between the ARM and server receipts.

| Measurement | Optimized ordinary ARM | Standard server |
|---|---:|---:|
| Retained candidate entries | 9,977 | 35,440 |
| Passing candidate entries | 9,728 | 10,066 |
| Mean detector wall time / dwell | 56.940 ms | 246.140 ms |
| p95 detector wall time / dwell | 87.165 ms | 419.995 ms |
| Maximum detector wall time / dwell | 144.837 ms | 738.921 ms |
| Calls at or above 120 ms | 3 / 2,215 | 2,079 / 2,215 |

ARM uses the original frozen optimized ordinary binary, SHA
`9b0c777653a97766ef060e4945c840308e3d6b48365b1412f6219a335d572d3e`,
on physical PLUTO+ `192.168.1.15`. Its gate uses the integer GLRT margin.
The standard server uses the maintained public detector with its fractional
refinement and gate. Both gates are 0.025, but these are different search and
scoring algorithms; the runtime comparison is not a same-algorithm speedup.

The ARM figure excludes file transfer, preload and context setup. Its summed
detector-call wall time is 126.122 seconds; the saved-data replay including
staging and verification took 1,183.26 seconds. Server per-dwell times surround
its detector invocation, excluding raw reading/hashing. Four server worker
processes finished the full replay in 215.112 seconds; summed detector-call wall
time is 545.200 seconds because those calls overlap. Neither run collected RF
or qualifies capture-concurrent real-time operation.

Passing-only diagnostic pairing finds 7,136 matches, or 70.89% of the server's
passing entries. The deterministic greedy rule pairs within the same dwell and
receiver, with circular integer-epoch distance at most two samples (period
3,333) and acquired-CFO distance at most 10 kHz. Endpoints cannot be reused.
This is not exact rank equivalence, maximum-cardinality matching, or a measured
false-positive rate. Similar total hit counts therefore do not imply identical
hits or scientific parity.

## Plots

- [GLRT margin versus original dwell time](glrt-vs-time.png): all retained ARM
  candidate margins and all available server fractional margins, including
  values below the gate. The server has 10,066 unavailable fractional results;
  those have no fractional score and are not plotted as zero.
- [Passing-candidate frequency versus time](detections-vs-time.png): tracking
  CFO, split by receiver and colored by channel. Markers are assigned to their
  original probe/dwell start, preserving retune gaps.
- [Counts and detector runtime versus time](counts-and-runtime.png): passing
  entries per one-second capture bin and per-dwell detector wall time.

PDF versions have the same filenames. `comparison.json` contains the totals,
`matched-passing.json` contains diagnostic pairs, and
`comparison-input-hashes.json` binds the plotted inputs. `plot_comparison.py`
checks full coverage, source equality, finite values and server task/configuration
bindings before generating output. Its three matching tests pass.

## Execution evidence

`arm-v2/` is the accepted complete ARM run. It contains 139 batches, the original
capture manifest, the original-visit/counter/raw-hash inventory and completion
receipt. The earlier `arm/` directory is an excluded partial attempt: the frozen
benchmark requires batch-local sequence numbers; the v2 harness fixed those
numbers and retained original visit identities separately. No detector setting
or IQ sample changed. Four previously benchmarked dwells have identical
non-timing scientific outputs in the complete replay.

`server/` contains the fresh standard-server implementation and receipts.
`device-after-hashes.log` verifies the ARM binary and FFTW runtime after the run;
FFTW remains `1331a476804e5812490f15c18f4b087859552716fb5933413606482642d61a19`.
The independent audit is in `rootreport/independent-review.json`.
