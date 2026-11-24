# Earlier filtering of historical orbit elements on a weak physical fix

On the saved DS30-0016 selective receiver output, using the regional satellite list earlier reduced historical row visits from **750,044 to 97,083**. The whole saved process was **0.05 s faster** in candidate-first order and **0.02 s slower** in baseline-first order. Both calibration solutions, all 116 ordered observations in each arm, the full 179-point numerical grid, the path and all eight figures reproduced the reference. These results give no repeatable through-exit gain for integrating the change. [Protocol](weak-finish-profile-protocol.md) · [Four-process receipt and publication digests](measurements/regional-history-rows.json)

An instrumented replay of the current selective positive put about 2.15 s in preparing the scientific scan inputs, including 1.36 s in the initial sky. The profile located 99 parser calls and 223,913 requests for individual orbital elements. It motivates the experiment. Python tracing changes runtime, and its nested clocks cannot be added to the uninstrumented results.

The prototype applies the ordinary parser, complete causal catalogue and regional orbit screen. From that point forward, it exposes only the regional satellite numbers to the historical policies that already discard every other satellite. It preserves the ordering and multiplicity of every retained row and obtains the orbit objects and epochs from the current snapshot. A bounded cache maps each distinct sequence of satellite numbers to indices. The key is independent of coordinates, and changing the selected satellite set invalidates the lookup. The control enters the same timed sky and history operations with the original parser. [Scoped implementation](regional_history_rows.py) · [Component tests](../../../tests/pipeline_eval/test_regional_history_rows.py)

| Execution order | Sky and phase history CPU | Entire solve CPU | Fresh process elapsed | Process CPU |
|---|---:|---:|---:|---:|
| Candidate 1 | 1.256 s | 2.480 s | 4.54 s | 4.53 s |
| Baseline 1 | 1.332 s | 2.542 s | 4.59 s | 4.58 s |
| Baseline 2 | 1.223 s | 2.432 s | 4.41 s | 4.40 s |
| Candidate 2 | 1.223 s | 2.437 s | 4.43 s | 4.42 s |

Every process used one low-priority core and the same signed detector, regional offer, libraries and causal archive. The first candidate process reported 376 input blocks and 10 major faults, the other three reported zero. No process had waveform access. Both original estimates remain **976 m fixed-zero and 1,452 m fitted**, with RF RMS **116.340 and 115.526 Hz**. Terminal, detector, position path, manifest and all eight encoded/decoded PNGs matched. The comparison of every grid field excludes the measured grid duration. [Selective receiver inputs and original geographic score](continued-cfo.md) · [Verification script](regional_history_score.py)
