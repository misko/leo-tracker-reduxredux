# Endpoint-only transfer keeps the original DS30-0160 publication

The frozen endpoint rule made **zero trim checks and zero refits** on the reserved DS30-0160 recording. Both saved publications followed the original `history_support` retry and returned **923 identical ordered owners and roles per calibration arm**. Their terminal, complete 179-point grid, optimizer path and all eight PNG file and decoded pixel hashes match. [Prospective transfer protocol](endpoint-track-repair-0160-protocol.md) · [Sealed pair](measurements/endpoint-track-repair-0160.json.gz)

| Calibration | Horizontal error in both arms of the comparison (km) | RF RMS in both arms of the comparison (Hz) |
|---|---:|---:|
| `c = 0` | 1.915421 | 127.011780 |
| Fitted `c` | 2.021655 | 126.950084 |

The first inference attempt fell back after its original assertion, before an ordinary paired track fit. The recovered attempt completed with 861 conditional and 62 predictive observations. Both ordinary arms passed, and the signed phase adjustment was unqualified. Both traces include the abandoned attempt as well as the completed retry. The lost 114 named observations had already left the eligible support, and this late endpoint rule left them in the same state. [Original 0160 owner-loss trace](owner-0160-audit.md) · [Positive 0402 development case](endpoint-track-repair-0402.md)

| Saved timing boundary | Fresh cumulative control | Endpoint option enabled |
|---|---:|---:|
| Full launch through exit elapsed | 14.565 s | 14.206 s |
| Full launch through exit CPU | 14.558 s | 14.203 s |
| Numerical solve CPU | 12.073 s | 11.589 s |
| Filesystem input blocks | 24 | 0 |

Both fresh processes used the original sealed signed detector, causal archive and operator offer in tmpfs, with the same exact Graph and corrected Cairo options as the 0402 comparison. The older 0160 cumulative control used the previous renderer. The fresh control reproduced its terminal, ordered owners and numerical grid/path science. Both fresh renders used four native orbit sheets and two native residuals without fallback. The grid and path bind their own verified position PNG. The raw stage was outside this saved trial.

The timing difference occurred with zero endpoint activation. These clocks capture ordinary process and dependency variation, with 24 control input blocks versus zero for the enabled run. The comparison used one fresh control and one candidate under the single low-priority Gauss CPU2 lock and measured through exit. Fourteen focused and adjacent tests passed, including the audit of any paid repair in an abandoned inference before history retry. [Exact rule](endpoint_track_repair.py) · [Runner](endpoint_track_repair_0160.py) · [Tests](../../../tests/pipeline_eval/test_endpoint_track_repair.py)
