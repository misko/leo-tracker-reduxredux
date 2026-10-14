# C001 warm initialization improves score but fails strict stationarity

Initializing the native-clock model at the original C001 winner finds a lower objective than both the original model and the augmented cold-start winner. The new endpoint nevertheless fails the unchanged stationarity threshold and is not an accepted fit or promoted result. Initialization explains part of the cold-search score shortfall; the experiment does not establish better localization.

| Measurement | Original-model repeat | Added native clocks |
|---|---:|---:|
| Objective | 41863.551059 | 41418.038342 |
| Training NLL | 41529.962579 | 41017.333803 |
| Posterior RMS Hz | 146.023317 | 133.582145 |
| Reported stationarity | 0.000157949 | 0.002061475 |
| Stationarity accepted at 0.001 | Yes | No |
| Optimizer reports success | Yes | Yes |
| Fit elapsed seconds | 0.705799 | 12.224815 |
| Evaluations | 18 | 260 |

The previous cold-start augmented winner had objective 42408.127844. The warm augmented endpoint improves that score by about 990.09 and improves the original objective by about 445.51, but these are training-score diagnostics of a rejected endpoint. Its failure was not a 20-second timeout. The independent original-repeat audit passed; the augmented endpoint remains explicitly marked optimizer-nonstationary. No reference or held observations were read, no geographic error was computed, and no failed call was retried.

Both arms use the original full-band training-selected geography, timing, fitted c and band offsets; only the augmented arm adds zero-initialized receiver clocks. The original winning 25 km disk, candidate bank, observations, priors, 20-second/600-iteration caps and likelihood are retained. This is two additional warm calls after the original searches, not an equal end-to-end search-budget comparison.

The first admission attempt (`ds22-native-clock-warm-v1`, source `60c34c34e`) stopped before any optimizer call because the fitter projects timing-bound endpoints inward. A read-only diagnostic measured a maximum adjustment of 1.053301446e-9 in timing coordinates, with no geography or receiver-calibration change. A distinct source and namespace (`d26bf7ac2`, `ds22-native-clock-warm-v2`) explicitly records this shared projection, rejects changes outside timing or at least 1e-8 in magnitude, checks both models' effective initialization, and verifies exact zero-clock nesting. The original failed admission is preserved. No frozen scientific source was edited.

The two-call experiment completed in 48.104311 seconds and sealed both outcomes before reporting. Tests cover identical starts/caps, zero added clocks, retention of nonconvergence, unexpected-error stop, and timing-only projection guards; four tests passed across the two versions, with Ruff clean. Receipts: `local/ds22-native-clock-warm-v2`; terminal SHA256 `b0c0aefb6297d7bbbeefeecc7bfd223f3db5966362979491e21e52a0e7c7d4cd` and seal SHA256 `83cc591e0b64fe680bc11cbdccee6992645b1308f92c30dc81e0b0bff26c8d61`.
