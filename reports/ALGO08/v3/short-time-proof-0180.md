# Insufficient track duration halves one complete raw recording

The candidate finished DS30-0180 in **0.805 s** on one warm Gauss core, including signed original I/Q, publication and exit. Named ALGO08v3 took **1.772 s** on the same recording in the preceding session. The cumulative candidate had taken **1.569 s** before this change. All seven files under the four standard publication directories, including detections, terminal and withheld sidecar, matched the preceding cumulative output byte for byte. Both calibration arms withheld with reason `no_active_curvature`. [Measured receipt](measurements/short-time-proof-0180.json.gz) · [Ordinary raw pair](short-raw-0180.md)

| DS30-0180, 92 issued / 76 admitted visits | Wall to exit | CPU to exit | Chosen receiver factors |
|---|---:|---:|---:|
| Named v3, earlier warm pair | 1.772 s | 1.770 s | 30 |
| Mixed receiver and ordinary graph, earlier warm pair | 1.569 s | 1.568 s | 72 |
| Same mixed receiver and time proof | **0.805 s** | **0.803 s** | **72** |

The only frequency/antenna/channel group with the required eight observations covered **2.834 s**. The installed track graph requires a seed spanning at least **6 s**. The new option uses the installed winning-observation adapter, track configuration and pinned graph sources. Within each physical lane, it splits observations at a time gap the graph cannot cross. If every resulting group is too short or has too few observations to seed even one track, it publishes through the ordinary withheld-output writer before loading the solver or plotting library. On inconclusive input it continues with the normal solver. The additional check has a budget of 256 winning observations. Neither position nor orbit identity enters the proof. [Implementation](short_graph_guard.py) · [Frozen protocol](short-time-proof-protocol.md)

All 27,214 compressed pages were already resident. The follow-up did no conditioning and used tmpfs for output. The new run spent **0.414 s** in authenticated acquisition and **0.015 s** inside the final decision/publication interval. The earlier v3 and ordinary cumulative runs were separate launches on the same inputs. The first follow-up preflight stopped before starting any analysis because the cache observer required a tuple of signed manifests. The driver now supplies that contract. The next launch completed. [Trial and checks](short_time_proof_trial.py)

The saved DS30-0016 fix, with 475 winning observations, correctly continued to the solver. On 20 generated lanes the proof rejected 12, the installed graph emitted tracks in seven, and all seven continued. Eight new unit cases cover threshold equality, one-ULP separation, disconnected times, separate receivers and nonfinite input. Eleven unit cases passed including the existing count-proof suite.

One development withdrawal exceeded 2×. There are only ten DS30 recordings with fewer than 128 issued visits among the published 455. Substituting this one measured time into the previous three-pair calculation gives a **0.454 median** but a **0.712 summed ratio**, still 2.940 s above the total half-time allowance. This substitution mixes executions from separate builds; a complete three-recording fresh timing of the new build is pending. The other two original recordings were not replayed here. [Prior three-pair ledger](short-raw-0180.md)
