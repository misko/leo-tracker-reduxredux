# DS30-0218 held CFO edits and installed carrier agreement

The 530 sealed edits increased strict signed agreement with the independently acquired ALGO08v3 full-aperture winners from **483 to 499** on DS30-0218. The strict window restored 18 matches and spoiled two. The wider window stayed at **506**. Of the matched edits, **328** moved closer to the installed CFO and **194** moved farther. [Protocol](masked-cfo-0218-installed-agreement-protocol.md) · [Bound numerical receipt](measurements/masked-cfo-0218-installed-agreement.json)

| Edited scope | Edited opportunities | Installed winners / empty | Coverage | 250 Hz / 2 samples, before → after | 2,250 Hz / 6 samples, before → after | Closer / farther |
|---|---:|---:|---:|---:|---:|---:|
| All | 530 | 522 / 8 | 98.49% | 483 → 499 | 506 → 506 | 328 / 194 |
| Ordinary owners, both calibration arms | 442 | 435 / 7 | 98.42% | 407 → 419 | 424 → 424 | 278 / 157 |
| Ordinary nonowners, both calibration arms | 88 | 87 / 1 | 98.86% | 76 → 80 | 82 → 82 | 50 / 37 |

The split was checked separately with `c = 0` and fitted `c`. Both arms had identical edited owner membership. The edits changed CFO alone, and 506 matched rows were within both arrival tolerances. The score joins the same native hardware opportunity across packets, then compares physical pilot arrival on its `40,000/3`-sample cycle. It uses the signed published CFO without a wrap adjustment. Five differences exceeded half the 227.273 kHz CFO alias spacing before and after. Allowing a whole CFO alias would add zero joint matches in either window. The eight installed empty opportunities remained in coverage and supplied no reference CFO. [Original agreement implementation](held_short_cfo_shrink.py)

| Edited scope with installed winners | Signed mean error (Hz) | MAE (Hz) | RMS (Hz) | p95 absolute error (Hz) |
|---|---:|---:|---:|---:|
| All | 2,986.92 → 2,977.20 | 3,333.97 → 3,311.04 | 21,929.47 → 21,928.55 | 307.58 → 232.91 |
| Ordinary owners | 2,846.73 → 2,836.16 | 2,953.12 → 2,929.57 | 20,546.73 → 20,546.25 | 288.89 → 220.09 |
| Ordinary nonowners | 3,687.85 → 3,682.44 | 5,238.26 → 5,218.40 | 27,831.06 → 27,828.50 | 32,717.54 → 32,571.04 |

Signed errors are mixed minus installed CFO. All matched pairs enter these distributions, including the large separations. On the earlier fixed ordinary position and nuisance state, the 442 edited owners went from **140.625 to 93.045 Hz** RMS with `c = 0` and **141.610 to 95.178 Hz** with fitted `c`. The independent strict agreement gain on the 435 owners with a full winner shows that the improvement extends beyond residuals against the candidate’s own model. The full receiver measures the same RF capture and can choose a different peak. This single recording supports tighter carrier agreement and leaves the relative contributions of measurement, Graph rebuild and refitting to position accuracy unresolved. [Sealed fixed-state comparison](measurements/masked-cfo-0218-prospective-fixed-residuals.json)

The CPU 3 readback reproduced the sealed edit digest and original and corrected winning-row hashes in **0.898 CPU s**. Both native packets authenticated against the original field pair and matched radio, tuning, hardware counters and capture authority. The installed winner extraction matched the pinned numerical extractor. No new detector, position fit, orbit read or additional case ran. Nine focused tests passed. [Runner](masked_cfo_0218_installed_agreement.py) · [Tests](../../../tests/pipeline_eval/test_masked_cfo_0218_installed_agreement.py)
