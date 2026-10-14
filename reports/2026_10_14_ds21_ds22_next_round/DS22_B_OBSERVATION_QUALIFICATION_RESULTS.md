# DS22 conditional-observation transfer: qualification passed

The frozen B conditional-CFO/detectability core passed actual-data qualification on original DS22-059 and DS22-071 training winners. Both retained their original full candidate banks and calibration frames. This verifies the mathematical transport; it does not demonstrate improved localization, predictive performance or repair of the broad 059 discovery/domain failure. No fit, held evaluation or reference join occurred.

| Case | Original candidates | Full/even/odd windows | Objective calls | Elapsed seconds | Maximum nonzero detectability FD error |
|---|---:|---|---:|---:|---:|
| 059 | 50 | 3499 / 1473 / 2026 | 307 | 33.897 | 1.3493e-7 |
| 071 | 59 | 2968 / 1752 / 1216 | 361 | 30.447 | 1.1522e-7 |

For both cases, full-mask legacy objective, physical gradient and original nuisance gradient replayed the unchanged original B model exactly (maximum differences zero). Posterior closure also passed. Across all three masks, conditional-minus-legacy equaled integrated event log-mass within 1.10e-11; the zero detectability tail preserved the conditional objective, original gradients and posterior. The nonzero-tail fixed-budget detection probabilities were interior and summed to 1.6 (within 2.3e-16), with every tail coordinate checked by centered finite difference. There were 49 tail coordinates on 059 and 58 on 071.

The original full-training state, bank, initialization and clock nodes are shared across masks. Consequently these parity subsets are a qualification device, not untouched validation. No new state or geography was selected, no candidate was added, and no prototype is promoted. Subsequent fitting requires its own prespecified controls and budgets.

Source and protocol: `5fae19162`; three component tests and Ruff passed. Frozen receipts are under `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-b-observation-qualification-v1`:

| Case | Protocol SHA256 | Report SHA256 |
|---|---|---|
| 059 | `087cbf5c0d786a30ebd8d93b69365c32de84533fb8475e19a4ed3ff8c5de16a2` | `03fcd420549b15a28bc49261511cd2d6a10d8ab18d04b234d13185d3535d8e36` |
| 071 | `d68275eff4ba8b7d2ea460ef6f481566420fac6b0685f9ce9a402eb42dc576be` | `0005fbc09b233af1ac1bd4d9ee7e823c227a059b83f1c9fb3429a691ff6c26bd` |

Each separate namespace retains its source archive, exact original-file inventory, durable launch and successful termination. Actual counts stayed within the prespecified 310/365 objective caps and 180-second internal bound; total optimizer calls were zero.
