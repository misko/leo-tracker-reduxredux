# Full-frame matched-pilot qualification of the recent two-source hit

## Result

Visit 678 of `scan-hop-34c0b0e1ae062f97` is the only visit in the bounded 20-visit neighbor screen with two phase-blind RX0/RX1 candidate pairs. The existing covariance-corrected full-frame matched-pilot estimator was replayed on this saved IQ without collecting new RF.

The estimator **abstains**. None of the six fixed 20 ms blocks passes the phase-blind requirement that both source bands have coherence at least 0.1 and matched-to-wrong-source coherence ratio at least 2. Consequently there are zero eligible matched-pilot frames, zero qualified blocks, no symbol-alias winner, and no qualified double-difference phase.

The earlier asynchronous two-pair extractor reports a wrapped high-minus-low value of -13.92 degrees with a conditional 17.40-degree standard error. That value is retained as exploratory evidence, but it is not promoted: the same-source overlap gate required by the full-frame estimator failed before phase was considered.

## Gate evidence

The two RX0 candidate frequencies are 339,691.36 and 455,071.85 Hz. Their direct separation is 115,380.49 Hz. The common RX1-minus-RX0 broadband frequency authority is -675,572.31 Hz. All gates below were fixed before this replay and do not consume phase.

| Block start (ms) | Low matched | Low wrong | Low passes | High matched | High wrong | High passes |
|---:|---:|---:|:---:|---:|---:|:---:|
| 0 | 0.111 | 0.024 | yes | 0.064 | 0.083 | no |
| 20 | 0.079 | 0.093 | no | 0.057 | 0.111 | no |
| 40 | 0.171 | 0.098 | no | 0.105 | 0.102 | no |
| 60 | 0.036 | 0.076 | no | 0.095 | 0.074 | no |
| 80 | 0.155 | 0.090 | no | 0.037 | 0.078 | no |
| 100 | 0.079 | 0.063 | no | 0.054 | 0.059 | no |

At 0 ms the low-frequency source passes, but the high-frequency source is both below the coherence floor and weaker than its wrong-source control. At 40 ms each matched coherence exceeds 0.1, but neither achieves the required factor-of-two specificity. Relaxing those gates after seeing the phase would invalidate the qualification.

This result is limited to one dwell. It neither establishes a temporal double-difference trajectory nor proves that the two RF components are different satellites or sky directions. It does show why the apparent second-source hit cannot yet serve as the simultaneous reference needed to cancel the receiver/LNB phase in the recent long-track analysis.

## Frozen evidence

- Input manifest: `sha256:0b31d2c4307dfcd8394b955756f96da989960c0358502eac393f4f390597145f`.
- Phase-blind raw authority: `sha256:7ff8cf09fd6c5e6aafee83e510bceda122956a9cb37e9ee0811b8c80288d44ca`.
- Source-overlap evidence: `reports/figures/2026_09_21_recent34c0_matched_pilot_dd/scan-hop-34c0b0e1ae062f97-visit678-source-overlap-v1.json`; canonical digest `sha256:d8af0a24951a0d743651972758b6d2ab756ab0193660cbb816ddc96224bcb7aa`; file SHA-256 `68d3ba1798e416bad515ab88c90c00ddf4b7a8f38ec69f67abe6b44b74188cb0`.
- Matched-pilot result: `reports/figures/2026_09_21_recent34c0_matched_pilot_dd/scan-hop-34c0b0e1ae062f97-visit678-matched-pilot-dd-v1.json`; canonical digest `sha256:0ae66386a7986f3c2ecf5e7be27c38ee85034b7a4f4c2bd585cab8ec10c3868f`; file SHA-256 `5bab909bcad10a493814dff7fdff472477e60ff73ed2d7872f102ada12c35308`.
- The production phase product and persisted contracts were not modified.
