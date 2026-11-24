# DS30-0163 measured sparse first-member intervention

Replacing the first signed member's detections with actual sparse 20/8 ms selections moved the fixed- and fitted-`c` endpoints by 7.812 and 9.256 m. Surveyed horizontal error rose by 4.706 and 3.510 m. Restoring the one disputed installed singleton recovered its original conditional owner in both calibration arms and reduced those error increases to 2.291 and 0.849 m.

| Input to the same clean saved publication | Error, fixed / fitted (m) | Conditional RF RMS, fixed / fitted (Hz) | Owners per arm | Child wall / CPU (s) |
|---|---:|---:|---:|---:|
| Original all-20, previously sealed | 981.881 / 854.018 | 135.158131 / 135.045776 | 3,055 | 11.025 / 10.888 |
| Measured first-member hybrid | 986.586 / 857.528 | 135.288662 / 135.176911 | 3,067 | 11.565 / 11.453 |
| Hybrid plus original visit 61 singleton | 984.171 / 854.867 | 135.300481 / 135.189151 | 3,068 | 12.193 / 12.142 |

The 64-visit member had 55 admitted stereo visits. Its installed rows reproduced the full original 20 ms packet exactly. The sparse packet changed 36 of the 110 admitted lanes, with 28 newly nonempty lanes and eight nonempty lanes whose factors differed. All measured candidate lists went into the hybrid, including the 74 empty lists. All nine exclusions and the remaining 6,708 scheduled visits were carried through unchanged. Matching used the digest-bound original index, absolute visit, RF, radio, clock and hardware counters. The full recording retained its original authority, offer and causal archive. The two derived detector recipes bind their measured parent packets and identify the specific lane restoration.

At visit 61, RX0, channel 6, the installed singleton reported −49,126.353 Hz at rank 1 and the sparse singleton reported +68,872.210 Hz at rank 0. The otherwise untouched restoration makes a single probe-row change. Both hybrid arms initially lost exactly that observation and added 13; the restored run regained it as conditional support for NORAD 67635 while keeping those 13 and every other hybrid owner. No shared observation changed satellite or role. The one observation moves the hybrid endpoints by 2.933 and 2.818 m and reduces surveyed error by 2.415 and 2.661 m, while slightly worsening the in-sample RF RMS. Even with all original owners recovered, the 13 additional conditional rows remain and the endpoints differ from the all-20 control.

Both children exited zero, fixed in both arms, produced 179 grid points and a path whose sidecars bound their own verified position PNG, and supplied eight independently decoded PNGs. Both used all 356 reduced predictive evaluations, both guarded ordinary Agg orbit figures and all eight native PNG verifications with zero fallback. The same healthy-orbit lean path accepted both hybrids. The rank race reported a winner on the original and an ambiguous gap on both replacements, with cold branch 1 retained. The full solve consumed 7.740, 8.360 and 8.830 CPU seconds in the table's order. Common admission and preparation for both interventions took 0.291 wall s and 0.288 CPU s. Child input blocks were 0, 63,768 and 8,560 and major faults were 0, 92 and 75. These counters have no file attribution. The experiment read only existing local metadata, signed native packets and causal catalogue files, with no waveform or backing archive reads.

The substitution covers one member of this recording. The singleton choice uses an already observed receiver disagreement. Its conditional effect gives no estimate of full-recording sparse accuracy or a general singleton repair rule. The historical saved control used the same clean publication code. Its acquisition and the two detector acquisitions are outside the child clocks.

## Reproduction and sealed evidence

Use `prefix_transfer_0163_sparse.py` with the genuine digest-pinned inputs in the [frozen protocol](0163-sparse-prefix-hybrid-protocol.md). The `prepare` action stages both variants and writes a pre-fit seal. Then run `launch … hybrid` under the shared low-priority lease followed by `score … hybrid`. The `restore-singleton` launch accepts only a qualified primary result with changed endpoints or ordered owners. The source and run rules were frozen at `52d560b31` and the isolated source path corrected before evaluation at `37dd1980e`. The compressed receipts preserve the original result bytes.

| Receipt | Uncompressed SHA-256 | Product seal SHA-256 |
|---|---|---|
| [Pre-fit evidence](measurements/0163-sparse-prefix-prefit.json.gz) | `270411527ace4587660c74c597f2199fd84f85f4ec47930302d39b969d8c5db4` | — |
| [Signed lane overlap](measurements/0163-sparse-prefix-overlap.json.gz) | `70d8a6eacda7dce887f1b4c879bb0d8c877587f68b00cdba61e05cf66a6a0650` | — |
| [Measured prefix](measurements/0163-sparse-prefix-hybrid.json.gz) | `c0b4979a3ed778d18649c1fa6cfb4fa98ce3210460eeb9ac9ac6269cd967ab95` | `71fad1b93b889927fd50f28250f81552d37510e49f5af76d152e6bdf254f59a2` |
| [Restored singleton](measurements/0163-sparse-prefix-singleton.json.gz) | `49fe61b4a1aca0f2b4ef7bd186a9abe82306d7c8b57846c13a71775ffcb73c84` | `9ca867191c4f47e30b7456e0ae59ee22d4a1a874afee298c47c976728769d6ed` |

The unchanged candidate sources and earlier [all-20 control](ds30-composed-saved-transfers.md) remain available in their respective worktrees. Six component tests covered signed row substitution, empty and moved lanes, installed parity, singleton admission and the earlier composed comparison.
