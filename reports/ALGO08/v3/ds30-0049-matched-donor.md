# DS30-0049 matched-carrier measurement substitution

Substituting genuine 20 ms measurements on eligible short lanes reduced fitted horizontal error by **193 m**, recovering **7.36%** of the original 2.620 km gap. The fixed-zero error improved by **275 m**. The fitted improvement misses the frozen 250 m gate, leaving **2.427 km** of excess fitted error. This result deprioritizes matched-winner remeasurement as the main repair for this case. [Sealed clocks and evidence](measurements/ds30-0049-matched-donor.json.gz)

| Calibration | Installed error | Sparse error | Donor error | Installed / sparse / donor conditional RF RMS |
| --- | ---: | ---: | ---: | ---: |
| Fixed zero | 1.826 km | 4.472 km | 4.196 km | 129.663 / 168.634 / 152.677 Hz |
| Fitted | 1.420 km | 4.040 km | 3.847 km | 129.671 / 168.814 / 152.869 Hz |

The ordinary sparse and substituted solves both published a lean fix from the original offer. Both classified the endpoints as interior. Both retained two satellites and seven tracks in each calibration arm. All 268 original sparse owners kept their satellite and role, and the substituted measurement on one previously unowned lane added a 269th owner. The result uses 184 donated owners in each arm. It shares 250 owners with installed with no shared reassignment. Sparse and donor all-owned RF RMS equals their conditional RF RMS on this case, with one extra owner in the donor comparison. Both calibrations produced the standard 179-point grid with zero endpoint replay discrepancies, the position path bound to the same terminal and position image, and all eight independently checked standard PNGs.

The [frozen protocol](ds30-0049-matched-donor-protocol.md) changes only the measured factor on short lanes where the independently measured installed and sparse winners already agree within 250 Hz in original signed frequency and two samples in wrapped pilot epoch. Both source packets and the original clock and offer are authenticated. The genuine installed 20 ms winner supplies all factor fields, including the original rank, epoch, signed CFO, exact and control scores, and margin. No chance of acquiring a different carrier is offered to the sparse packet. This is a mechanism test with perfect prior identification of eligible carriers.

All 986 issued visits, 932 admitted stereo opportunities, 54 invalid visits, and 600 sparse winners are held fixed. No full-anchor winner, opportunity timestamp, or unchanged lane is rewritten. The 284 measurements donated by the installed packet are 17.5% of the 1,622 short opportunities and 47.3% of the 600 sparse winners. They cover 183 of 268 sparse owners and 185 of 320 installed owners in each archived calibration arm. The two original signed estimates differ by 114.378 Hz RMS over these 284 lanes. The integer epoch changes in 116 tuples and the original native rank changes in three.

| Lane | Opportunities | Donated | Two positives disagree | Installed only | Sparse only | Both empty |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| RX0 short | 811 | 237 | 59 | 30 | 78 | 407 |
| RX1 short | 811 | 47 | 13 | 74 | 83 | 594 |
| RX0 anchor | 121 | 0 | 0 | 0 | 8 | 65 |
| RX1 anchor | 121 | 0 | 0 | 0 | 4 | 94 |

The 71 anchor pairs with two positives are included in the 242 unchanged anchor lanes. The 104 installed-only short positives, 161 sparse-only short positives, and 72 two-positive short carrier disagreements remain in their original sparse states. The full candidate keeps the original geographic offer and reruns ordinary association and the two calibration fits. Neither donor selection nor packet preparation uses owners, reference coordinates, or score.

## Reproduction and custody

The original [saved crossover](ds30-0049-saved-crossover.md) certifies both diagonal controls against their archived raw publications, including both arms, terminal, owner digests, the complete grid, path, and all eight encoded and decoded figures. The derived receiver research recipe is `sha256:2c91eaf9533f0082e5ea63e3b4bb0857153fc02a8992b01a7c232732178746f7`. Its detection packet is `sha256:39355be9ab7c5db5efa9371ac7f999b963aaa48f1a4323de4343e5e0abdf24c8`. Both original native packet digests and the ordered list of paired full tuples bind the new identity. The original raw and inventory identities remain intact. `prepare` seals the pair and derivation, `smoke` checks the installed runtime and all 48 existing local causal files without a solver, `launch` holds the shared single-core lease for the candidate, and `score` reads the sealed publication independently.

The one measured saved worker took **7.561 s wall / 6.973 s CPU** through exit. The authentic archived sparse diagonal saved worker took **6.36 / 6.31 s** in a different lease. The substituted worker used the bound portable index, with 17 sidecar hits and eight ordinary bodies in the portable path. No port-level fallback was recorded. It reported 99,000 process input blocks and 214 major faults, versus 10,064 and 76 on the historical control. Both scopes start with saved detections. The substituted worker denied all waveform access and accepted one handoff. It ran neither a detector nor an EOF receiver selector. Creating and sealing the small derived packet took another 0.116 s wall / 0.065 s CPU. Nonblocking admissions yielded to the production campaign without launching workers until the candidate could acquire the shared lease.

The protocol lived at `d0b5a7120` and the child ran `85b6c9390`. The prediction seal is `70bb04a825dbf2b67b1c708dfa82abb4841a366fb5daab486e545e6d9ac17d24`, the independent score is `85db02e32181357ce465ab8c17c80f45ed9b81876d841cfa72960600a0b375a6`, and the compressed receipt is `9e129a016bdd533d7c82706b402665bea6cd2d34c0628c0bda62fe414cae1a6a`. Three component tests passed. [Derivation](matched_donor_0049.py) · [Worker and scorer](matched_donor_0049_trial.py) · [Tests](../../../tests/pipeline_eval/test_matched_donor_0049.py)
