# Where lean and exact named localization agree

The lean and exact named solvers published **identical terminals** from the same signed all-visit 20/8 ms receiver packet on North and DS30-0016. Each arm kept the exact ordered observation, NORAD and role rows and the exact recorded optimizer path across five phase refreshes. The archived paths expose accepted positions and phase-change scalars. They do not record the full phase vector in these two standard publications. Both routes differ on the identical detector packets for DS30-0160, DS30-0316 and DS30-0374. These examples give no preselection rule that guarantees named science. [Audit and source pins](lean_named_parity.py) · [Joined receipt](measurements/lean-named-parity.json.gz)

## Matching scientific quantities

| Same 20/8 ms packet | Owners per arm, conditional + predictive | Position error, zero / fitted `c` | Conditional RMS, Hz | Published all-owned RMS, Hz | Raw predictive RMS from the role sums, Hz |
|---|---:|---:|---:|---:|---:|
| North containing simulation | 323 + 19 | 111.954 / 128.086 m | 9.133 / 8.921 | 44.983 / 50.415 | 187.094 / 210.707 |
| DS30-0016 physical containing | 92 + 23 | 490.071 / 980.010 m | 134.021 / 133.740 | 135.547 / 136.859 | 141.485 / 148.684 |

Every entry in the table agrees between lean and exact named for the corresponding packet. The earlier North reports used different quantities under the RF RMS label. The terminal computes RMS from the conditional residuals of the retained curved fit. The standard publication computes it over all reported owners, including the raw predictive residuals. The two accepted partitions have only conditional and predictive roles. The last column derives the raw predictive RMS by subtracting the conditional sum of squares from the all-owned sum and dividing by the predictive count before taking the square root. It is an aggregate reconstruction from archived summaries, without saved independent residual vectors. The distinction matters on North even though just 19 of 342 owners are predictive. [New North report](exact-named-raw.md) · [Earlier North report](eight-ms-native-live.md) · [Physical same-packet named report](named-weak-all8.md)

North used the same ordered **137** grid coordinates in both runs. The largest score difference was **4.55 × 10⁻¹³** in either arm. DS30-0016 used the same ordered **179** coordinates with at most **1.14 × 10⁻¹³** score difference. There were no different failure positions. Both sidecars point to their own terminal, input and position image. Each route produced all eight figures. The corresponding archived PNG byte digests differ for all eight under the distinct renderer settings. The audit joins published manifests and pinned earlier verification receipts without decoding new images.

## Counterexamples on identical full-20 ms detector packets

| Case | Exact → lean owners per arm | Lost / added | NORAD or role changes on common IDs | Lean finish | Exact and lean path |
|---|---:|---:|---:|---|---|
| DS30-0160 | 1,037 → 988 | 49 / 0 | 0 | Signed prior unqualified; ordinary lean pair accepted | Different |
| DS30-0316 | 1,976 → 2,002 | 0 / 26 | 0 | Original signed final refit accepted in both arms | Different |
| DS30-0374 | 2,905 → 2,822 | 83 / 0 | 0 | Signed prior unqualified; ordinary lean pair accepted | Different |

The 0160 loss includes 32 conditional and 17 predictive points. 0316 adds 26 conditional points while keeping all 533 predictive points. 0374 loses 83 conditional points across three fragments while retaining all 411 predictive points. Each lean run passed its own paired support checks. The 0316 acceptance is the decisive counterexample to using signed qualification, the released final continuous fit and the paired gates as an exactness certificate. They certify a fit on the supplied roster, and the lean proposal supplies a different roster. The earlier retrospective audit also observed no named cavity offer on that packet, so adding a zero-offer requirement would still leave this counterexample. [0316 shared solver inputs](original-final-fit-transfer.md) · [0316 named cavity profile](named-inference-budget.md) · [0374 track audit](named-final-0374.md) · [0160 saved divergence](held-adaptive-0160.md)

## What the clocks establish

| Previously measured scope, seconds | Exact named elapsed / CPU | Lean elapsed / CPU |
|---|---:|---:|
| North raw process through exit | 15.561 / 15.555 | 10.828 / 10.826 |
| North authenticated acquisition inside those processes | 6.144 / 6.143 | 5.074 / 5.073 |
| North numerical solve, including grid | 6.082 / 6.080 | 3.346 / 3.345 |
| DS30-0016 saved process through exit | 6.453 / 6.434 | 4.166 / 4.136 |
| DS30-0016 saved numerical solve | 3.127 / 3.119 | 2.098 / 2.097 |
| DS30-0016 saved render | 1.701 / 1.692 | 0.481 / 0.478 |

The North programs genuinely acquired the same original waveform on separate days and emitted the same signed packet. Both reported zero input blocks and major faults. The **4.728 CPU s** process gap includes **1.069 s** in authenticated acquisition with the receiver recipe held fixed and **2.735 s** in numerical solve. These clocks also include different verification and rendering configurations, so the difference does not isolate the solver or establish a matched raw speedup. The physical 0016 entries are separately recorded saved runs on one pinned packet and offer. Its **2.298 CPU s** process gap contains **1.022 s** in the numerical solve and **1.214 s** in rendering. There is no matched 20/8 ms named/lean raw pair on DS30-0016. [North raw receipts](exact-named-raw.md) · [Weak saved stage receipts](weak-all8-combined.md)

## Limit of a structural shortcut

Lean discovery can choose a different branch, reject or salvage different support, recompute confidence and predictive rows, and change the payload passed to the released signed fit. The fitted-`c` and fixed-zero admissions apply to that lean payload. Exact substitution of the released final fit requires equality of the ordered curved and predictive rows, aliases, masks, powers, nuisance and causal prior state, region, and initial numerical state at its input. Even when that equality is established, named held-family and exterior policy still need their original decisions or their own proofs. The archived endpoints and phase changes arrive after these choices. They cannot establish the same upstream conditions on a new packet.

Dominating the original held-family alternatives with a certified score bound would address the later cavity tail only. The earlier confidence-based pre-signed hybrid intentionally uses a heuristic here. Its frozen-radio five-anchor confidence excludes the full held covariance and physical modes. This audit found no checkable certificate that can establish named discovery and downstream decisions cheaply enough to admit lean on a fresh recording. There was no prototype activation, new numerical launch, waveform read or archive staging. [Earlier pre-signed hybrid](pre-signed-hybrid.md)

Run `lean_named_parity.py FRESH_TMPFS_RECEIPT.json` as the archived output owner. It validates the five saved detector and offer bindings, source-pinned ordered owners, and sidecar and terminal digests before making the comparisons. The initial read-only pass stopped when it encountered the direct adaptive 0160 sidecar format. The final audit validates both standard and adaptive formats. The uncompressed receipt SHA-256 is `0685e4ccbeb6af69b39563329cef014ab4a8eef18f7f6dffa8412f1b0a0b42fd`. Three component tests cover owner deltas, role-weighted RMS and same-coordinate grid comparison. [Tests](../../../tests/pipeline_eval/test_lean_named_parity.py)
