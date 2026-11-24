# Exact named inference on two saved physical recordings

The combined exact route reproduced the installed v3 results on **2 of 2** saved physical recordings. It retained both fixes, every ordered owner and role, both calibration arms, the full position grid and path, and all eight PNGs by encoded and decoded hash on each recording. Saved-input wall time improved **1.549× on DS30-0160** and **1.087× on DS30-0316**. Neither reached 1.6×. Each comparator is its previous installed-v3 saved worker on the same signed full-recording 20 ms packet and the original offer and cutoff. [Protocol](exact-named-route-protocol.md) · [DS30-0160 receipt](measurements/exact-named-DS30-0160.json.gz) · [DS30-0316 receipt](measurements/exact-named-DS30-0316.json.gz)

| Recording | Issued / admitted | Wall through exit, named → exact | CPU through exit, named → exact | Solve CPU, named → exact | Ordered owners per arm |
|---|---:|---:|---:|---:|---:|
| DS30-0160 | 3,691 / 2,354 | 15.999 → 10.330 s | 15.994 → 10.317 s | 12.565 → 6.886 s | 1,037 |
| DS30-0316 | 3,042 / 2,702 | 18.358 → 16.887 s | 18.353 → 16.829 s | 14.640 → 13.111 s | 1,976 |

| Recording | `c = 0` horizontal error | Fitted-`c` horizontal error | `c = 0` RF RMS | Fitted-`c` RF RMS |
|---|---:|---:|---:|---:|
| DS30-0160 | 798.498 m | 1,089.003 m | 126.335 Hz | 126.093 Hz |
| DS30-0316 | 1,944.726 m | 1,863.056 m | 99.232 Hz | 99.054 Hz |

Both gains are complete saved-process comparisons. The original named winner selection, repair, fit budgets, and standard layout stayed in use. There were zero withholds or accuracy degradations. DS30-0160 recovers the one locally confirmed previous-orbit fault and retains its named `history_support` provenance. Prior history recovery alone measured 11.120 s elapsed on this input. Its 0.790 s gap to the new composition is across separately timed worker runs. DS30-0316 took the ordinary `stock` route and paid no local recovery. Neither input activated the optional exact constrained gate preparation. [Earlier history-only evidence](named-history-once.md)

| Candidate work | DS30-0160 | DS30-0316 |
|---|---:|---:|
| Exact grouped rank curve calls | 416 | 624 |
| Catalogue curve rows removed by the visibility bound | 563,625 | 892,716 |
| Ordered Graph edges retained | 14,623 | 33,588 |
| Checked predictive geometry calls for the full standard map | 356 | 356 |
| Verified PNG readbacks reused | 8 / 8 | 8 / 8 |
| Earlier portable index hits / distinct consumed catalogue bodies | 4 / 36 | 0 / 40 |
| Verified causal reads and logical bytes | 131 / 234,106,417 | 130 / 232,250,492 |

All causal reads came from the earlier verified and fully resident tmpfs views. The experiment copied zero input bytes and issued no original waveform or backing catalogue reads. The process clocks include startup, guarded computation, rendering, and in-process verification. Independent scoring checked bindings and decoded products after exit. Both workers used the shared low-priority CPU 2 slot with one numerical thread. The historical controls bring cache and session variation. One successful scientific launch per case gives no within-case timing variance estimate and measures neither raw receiver performance nor a panelwide gain.

The initial DS30-0316 launcher stopped before inference because the signed prior request represented its entries as segment directories. The saved input binding independently encodes the same manifest path and digest sequence. A metadata-only normalization converted the old request syntax before the existing validator. The optimized solver scope stayed unchanged. The rejected startup cost 1.127 s elapsed and 1.121 CPU s. Including it gives 18.014 elapsed and 17.950 CPU s in total candidate attempts on DS30-0316. Thirteen component and adjacent tests passed, including the metadata compatibility and strict publication gate. [Preserved startup clock](measurements/exact-named-0316-rejected-startup.json) · [Driver](exact_named_route.py)
