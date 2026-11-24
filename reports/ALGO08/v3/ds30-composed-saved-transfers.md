# Clean predictive grid and ordinary Agg on three saved DS30 recordings

The fixed DS30-0359 composition passed both additional transfers on original signed 20 ms packets. The three saved publication children took 42.343 s versus 77.266 s for installed v3, a 1.825× speedup by summed time and 1.884× by the reciprocal of the median paired time ratio. The installed comparator was fresh for DS30-0359 and historical for DS30-0163 and DS30-0173. Both arms fixed on all three recordings. This cohort measures saved publication through process exit and does not include receiver acquisition.

| Recording | Installed wall / CPU (s) | Earlier ordinary routed wall / CPU (s) | Clean child wall / CPU (s) | Clean with admission wall / CPU (s) | Child wall speedup vs installed |
|---|---:|---:|---:|---:|---:|
| DS30-0359, fresh installed | 29.703 / 29.677 | 17.171 / 17.123 | 15.558 / 15.553 | 16.159 / 16.106 | 1.909× |
| DS30-0163, historical installed | 20.767 / 20.745 | 11.866 / 11.862 | 11.025 / 10.888 | 11.630 / 11.444 | 1.884× |
| DS30-0173, historical installed | 26.796 / 26.630 | 15.256 / 15.215 | 15.760 / 15.473 | 16.478 / 16.040 | 1.700× |
| Total | 77.266 / 77.052 | 44.293 / 44.201 | 42.343 / 41.914 | 44.267 / 43.590 | 1.825× |

The fresh DS30-0359 installed worker started after its clean candidate. The older 31.947 s installed clock produced a 2.053× comparison on that case. Using historical installed children for all three gives 79.510 s and 1.878× by summed time, with the same 1.884× median. With each recorded source admission charge included, the clean and installed totals are 44.267 s and 80.445 s, a 1.817× sum speedup and a 1.875× median. The two historical admission charges include their original staging or readiness costs. The new transfer admissions verify existing tmpfs inputs. Charging only the new candidate admissions against the installed child clocks gives 1.745× by summed time. The corresponding CPU speedups are 1.838× child-only and 1.829× with both sides' recorded charges. The cohort clears 1.6× on these saved clocks and stays below 2×.

| Recording | Ordered owners per calibration arm, installed → clean | Horizontal error c0 / fitted (m), installed → clean | Conditional RF RMS c0 / fitted (Hz), installed → clean | Largest grid score delta vs ordinary routed |
|---|---|---|---|---:|
| DS30-0359 | 3,640 → 3,640, identical | 592.489 / 666.751 → 592.489 / 666.751 | 115.604 / 115.589 → 115.604 / 115.589 | 7.28e−12 |
| DS30-0163 | 3,055 → 3,055, identical | 989.288 / 858.765 → 981.881 / 854.018 | 135.159 / 135.047 → 135.158 / 135.046 | 3.64e−12 |
| DS30-0173 | 2,590 → 2,458, all shared owners agree | 1,367.309 / 1,373.967 → 1,258.548 / 1,247.373 | 124.242 / 124.071 → 126.416 / 126.277 | 3.64e−12 |

Both transfer cases preserved the earlier routed endpoints and RF values exactly, including the existing DS30-0173 reduction of 132 named-only rows per calibration arm. They preserved original input authority and offer, solver decisions and branch, graph proof, scientific path, and all 179 grid coordinates. DS30-0163 kept the ordinary lean finish. DS30-0173 kept its original lean discovery and exact named finish. Each arm's own endpoint sample and first minimizing index were unchanged. All eight PNGs on each transfer matched the earlier ordinary routed PNG bytes and decoded pixels. Each grid and path sidecar bound its own verified position PNG.

Each fresh transfer used all 356 native grid and reduced predictor calls, the guarded ordinary Agg layout for both orbit figures with 16 axes and two restores elided, and eight native PNG validations. No port fell back. The full grid CPU changed from 2.218 to 2.047 s on DS30-0163 and from 2.419 to 2.291 s on DS30-0173 against historical earlier routed measurements. The full solve changed from 8.323 to 7.740 CPU s and from 11.803 to 12.128 CPU s respectively. DS30-0173's complete child used 0.258 CPU s and 0.503 wall s more than its earlier ordinary routed child despite faster grid scoring. Both transfers admitted the full scientific input and native files as resident with at least 1.27 GB free tmpfs. DS30-0163 reported zero child input blocks and major faults. DS30-0173 reported 54,776 input blocks and 153 major faults compared with 1,032 and 15 for the earlier routed child. Those process counters include paging and code or library reads, with no file attribution. Admission residency is a snapshot. No waveform or original catalogue reads were performed.

## Reproduction and receipts

Use the isolated installed entry for a fresh result directory on the single low-priority shared Gauss lease. The timed calls for each transfer are recorded in its admission. The same source-pinned worker is bound to each prepared, digest-pinned case. Run the offline `score` action against the result root after the child exits. The DS30-0163 worker was frozen at `86f9eec20` and DS30-0173 at `94a309bd6`. The DS30-0359 algorithm and measured loader at `867c0bf7e` are unchanged.

| Saved artifact | Result JSON SHA-256 | Product seal SHA-256 |
|---|---|---|
| DS30-0359 fresh installed | `72ef5a5036a42e39ae558972414e61981d5dab030afc8a8042bb38ebf41c51cc` | `92e69d1addfbf701ed9b0971ea513a72c3e2997a88a5a0719bb6095a212485dd` |
| DS30-0163 clean | `e08d702e92753fe2bc274c39f742815cc23b8be74415b3476a13b3b7bfac4573` | `b274c007546f7c36fae3b17d31d5e870ca96c47d47bdd99bffc4b36b79272176` |
| DS30-0173 clean | `bcc23b375e87abf64c994c129e0e2b3922d8e5a537f3b7f6ab62ddd352322ce3` | `9a6191d1098d7b8793ef22ac7089b9779ce24a6919b32a494c75727a47174d7d` |

The two compressed transfer receipts under `measurements/` hold the original sealed result bytes. The limits and exact input pins are in the individual [DS30-0163 protocol](ds30-0163-composed-saved-protocol.md) and [DS30-0173 protocol](ds30-0173-composed-saved-protocol.md).
