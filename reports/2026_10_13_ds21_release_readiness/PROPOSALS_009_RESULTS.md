# DS21-009 fitted-only initialization

DS21-009 completed the full initialization chain and exported six physical
proposals for each of CH1–8, CH1–4 and CH5–8. The shared candidate bank contains
41 satellites. This is preparation for the three-model comparison, not an
evaluated position result. No reference or held observations were used.

| Stage | Completed work | Stationary fits | Elapsed seconds |
| --- | --- | ---: | ---: |
| Discovery | 100 geographical points; 300 per-view fits | 298 / 300 | 333.150 |
| Doppler shape | Three starts in each view | 9 / 9 | 21.982 |
| Fresh bootstrap | Nine calls; all complete | — | 26.992 |
| Absolute-frequency hybrid | Nine fits at shape proposals | 9 / 9 | 40.703 |
| Cold bootstrap | Nine calls; all complete | — | 27.741 |
| Six-proposal export | 18 physical exports; zero optimizer calls | — | 27.947 |

Each stage ran in its own explicit bounded slice. The two nonstationary discovery
fits remain in the receipts; there were no retries. Timings are each stage's
reported runtime, including its preparation, and exclude separate freeze commands.

The causal catalogue contained 11,129 Starlinks; the regional bank retained 983
and took 4.455 seconds to build. The original discovery selector produced three
points and a 38-satellite initial candidate union. Fresh bootstrap expanded the
union to 41; cold bootstrap retained that fixed bank. Training preparation matches
the existing census exactly: 2,780 all-band, 1,506 low-band and 1,274 high-band
windows.

Export order is `cold-0`, `cold-1`, `cold-2`, `shape-low`, `shape-high`,
`shape-all`. All views preserve those source identities and original physical
correction functions. Maximum export closure error is `7.28e-12 Hz` for all-band
and zero for both halves. These seeds share discovery and cross-view initialization
information; they do not define independent end-to-end half-band pipelines.

All new fit arms are fitted c. As in the DS21-007 chain, the shape projection
removes RF-constant offsets, so its fitted-arm label is not evidence that it
identifies the RF calibration coefficient. The subsequent absolute-frequency
fits retain fitted c. Hybrid coefficients remain a required parent diagnostic;
they are not silently substituted for the original bootstrap seed exports.

The reusable runner is `tools/ds21_fitted_initialization.py`, commit `7928ec683`.
It preserves the original numerical ports, candidate ordering and budgets while
replacing the DS21-007-specific orchestration with one explicit case/stage API.
Its source closure binds 402 files, including the actual native binary and C++
source. The closure follows reachable dependencies rather than unrelated loaded
modules, allowing future model consumers to read these frozen proposals.

Validation passed: 15 owned tests, the focused source-consumer regression, and
four integration checks covering both synthetic labels, physical exports, actual
source closure and required artifact bindings. Every real stage's completion,
source, predecessor and artifact validators also passed. Compact stage timings,
counts and immutable source/result hashes are in
[PROPOSALS_009_RESULTS.json](PROPOSALS_009_RESULTS.json).

Seven of 34 fast development recordings now have complete proposal sets; 27
still need initialization. The original matched A/B/C accuracy table remains five
recordings, with a separate sixth Model C baseline on DS21-007. DS21-009's final
A/B/C fits and accuracy evaluation have not yet run. The 20 locked fast recordings
remain unopened for inference, and the full-DS21 0.5 km target remains unmet.
