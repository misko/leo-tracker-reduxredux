# Native relative-phase DS21-039 result

All twelve fitted-c calls were stationary under the original **20-second / 600-iteration** caps. The complete preparation and fitting slice took 76.408678 seconds, including 24.418621 seconds of preparation. Native execution permitted 272/371 evaluations for the two all-band phase starts, which finished in 9.743403/12.890535 seconds; the retained Python phase attempts had exhausted their unchanged 20-second caps after 164/167 evaluations. This repairs evaluation cost, without increasing the scientific allowance.

Training objective selected each result before the paired terminal and aggregate seal. The post-seal evaluator then scored the unchanged randomized whole-block holdout and joined the configured station reference, with no fitting or reference selection.

| Training view | Epoch error km | Phase error km | Epoch held NLL/window | Phase held NLL/window |
|---|---:|---:|---:|---:|
| CH1–8 | 4.072514870 | 3.025481115 | 11.541803884 | 11.534481823 |
| CH1–4 | 3.758515266 | 2.793478814 | 11.642504458 | 11.653623693 |
| CH5–8 | 4.163056282 | 3.042027043 | 11.389862732 | 11.388908936 |

Phase improves position error against this matched epoch arm in all three views. It **does not satisfy the requested target**: all-band 3.025481115 km remains worse than low-band 2.793478814 km, and every view exceeds 0.5 km. The consistent historical C039 errors were all 4.29122720423374, low 3.7585152658957535 and high **2.556791953929764 km**. Both new high-band selections regress that historical high result; the warm donor selected by training score changes the geographic mode.

Frequency evidence is separate. All-band phase lowers training NLL by 275.793475 and full objective by 295.274158, but increases frequency RMS from 92.149562 to 94.492704 Hz. Low/high training NLL rises by 315.926360/26.589375. Held NLL/window changes by −0.007322061, +0.011119234 and −0.000953796 for all/low/high respectively: low-band held fit worsens, while the other differences are small. These results do not establish correct physical phase or generalization. The configured reference is not independently surveyed.

The source/binary qualification remains the nine-state audit (result SHA-256 `e51636996cd417f08d87417aa7db035243ea56db83b6e4a7c5ed3e605a4d992b`), with maximum full-gradient difference 4.547473508864641e-13. Added native physical-start oracles preceded every optimizer. The source freeze preceded preparation; both arms in all three views were sealed before held/reference access. The first namespace's source-import ordering failure is retained, with zero fits; the successful second namespace uses the reviewed ordering repair. The host metadata bursts had ended before launch; two baseline discoveries and other agents remained active, so durations are not isolated machine benchmarks.

Actual receipts reside in `local/native-phase-matched-039-v2`: `freeze.json` SHA-256 `a24babe8e1027e348dca6581b52288f1acd3d8add5cf749cba86ce4bdb3e726f`; `fits/terminal.json` `7c2e1557d0b6257541abc645f7980b8e4c445bce5b1c74c7bc6bed0890a332ff`; `fits/seal.json` `05bb5b75bb7c1383824aed5cae273a8e6d98e9169ad37f55b1bd6a8279b88394`; `held-prediction.json` `8ccf7f39d7aa08c9d3291fa419b62d475bd48b5af9b186a4df4f82494a433fdd`. The evaluator's `development-errors.json` binds the terminal, protocol and held score. Nine component-owned tests and Ruff passed before execution. Frozen scientific files remain unchanged.
