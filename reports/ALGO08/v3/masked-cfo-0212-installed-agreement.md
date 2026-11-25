# Installed carrier agreement and position on four saved recordings

DS30-0212 gained **seven strict matches** with the independently acquired
20 ms receiver after the CFO edits. Its position error increased by
**17.50 m at fixed zero** and **34.14 m with fitted calibration**. This
recording shows that improved same-capture carrier agreement can coexist
with worse localization. [RF receipt](measurements/masked-cfo-0212-installed-agreement.json) ·
[Sealed position comparison](masked-cfo-next-two-results.md)

## Installed carrier agreement

| Recording | Installed winners / edited | Installed empty | Strict before → after | Restored / spoiled | Loose before → after | p95 absolute CFO difference, Hz |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0019 | 355 / 366 | 11 | 322 → 340 | 20 / 2 | 347 → 347 | 306.86 → 236.29 |
| DS30-0274 | 484 / 499 | 15 | 457 → 463 | 11 / 5 | 472 → 472 | 261.35 → 206.68 |
| DS30-0218 | 522 / 530 | 8 | 483 → 499 | 18 / 2 | 506 → 506 | 307.58 → 232.91 |
| DS30-0212 | 150 / 153 | 3 | 138 → 145 | 7 / 0 | 145 → 145 | 316.89 → 204.11 |

All four recordings improved in the frozen 250 Hz / 2-sample window and
had lower p95 absolute signed CFO differences. All four kept their
2,250 Hz / 6-sample match counts. Empty installed opportunities count in
coverage and the error distributions use all matched pairs. The installed
receiver provides a separately acquired measurement of the same capture.
[Earlier same-capture comparisons](held-installed-carrier-transfer.md) ·
[Prospective DS30-0218 readout](masked-cfo-0218-installed-agreement.md)

On DS30-0212, 83 of 150 matched edits moved closer to the installed CFO and
67 moved farther. Mean absolute error fell from 1,881.35 to 1,867.31 Hz,
while RMS moved from 13,301.26 to 13,303.31 Hz. One difference exceeded
half the CFO alias spacing before and after. A whole CFO alias added zero
joint matches in either window. Both ordinary calibration arms put 152
edits in the owner set, with 149 matched and three installed empty. The
strict owner count rose from 137 to 144, with all seven restored matches
in that subset. The single matched nonowner passed before and after.
[Frozen metric](masked-cfo-0212-installed-agreement-protocol.md) ·
[Bound numerical readout](measurements/masked-cfo-0212-installed-agreement.json)

## Position and ownership

| Recording | Fixed `c=0` error, m | Fitted `c` error, m |
|---|---:|---:|
| DS30-0019 | 434.87 → 121.05 | 375.18 → 54.06 |
| DS30-0274 | 888.61 → 718.79 | 933.51 → 752.27 |
| DS30-0218 | 1,056.80 → 819.41 | 1,124.69 → 873.47 |
| DS30-0212 | 1,068.12 → 1,085.62 | 977.18 → 1,011.31 |
| **Within 1 km** | **2/4 → 3/4** | **3/4 → 3/4** |

Three recordings improved their horizontal errors in both arms. DS30-0218
moved inside 1 km in both arms. DS30-0212 moved outside 1 km with fitted
calibration and stayed outside at fixed zero. The errors compare ordinary
and corrected saved-input publications. [0019 scores](held-shrink-0019-ram.md) ·
[0274 scores](held-shrink-0274.md) · [0218 scores](masked-cfo-0218-prospective.md) ·
[0212 scores](masked-cfo-next-two-results.md)

The two DS30-0212 calibration arms lost the same 12 ordinary owners and
gained zero. All 12 lost owners had unedited CFO. Their ordinary NORAD and
role counts were 53866 predictive ×1, 58033 conditional ×3, 58195
conditional ×6, 63069 conditional ×1, and 65367 conditional ×1. The 1,883
common owners retained their satellite and three changed residual role.
On fixed ordinary predictions, the 152 edited owners’ RMS fell from
178.49 to 140.96 Hz at fixed zero and from 172.06 to 129.90 Hz with
fitted calibration. The assignment and support changes are observed
alongside the positional shifts. This audit does not isolate their
individual contribution. [Fixed-residual receipt](measurements/masked-cfo-0212-fixed-residuals.json) ·
[Authenticated lost-owner groups](measurements/masked-cfo-0212-installed-agreement.json)

The offline CPU 3 readout reproduced the original and corrected winner
hashes and sealed edit digest. The masked Graph readback took 0.423 CPU s.
It ran zero new receiver or position fits and opened no orbit, waveform or
survey input. Official acquisition timings and the saved experimental
publication timings are reported at their separate boundaries. DS30-0442
remains a custody refusal in the enrolled panel and contributes no pair
to the four-row comparisons. [Runner](masked_cfo_0212_installed_agreement.py) ·
[Tests](../../../tests/pipeline_eval/test_masked_cfo_0212_installed_agreement.py) ·
[Field and saved publication clocks](masked-cfo-next-two-results.md) ·
[Custody receipt](measurements/0442-cache-custody.json)
