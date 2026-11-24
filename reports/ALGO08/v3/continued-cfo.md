# Pay signed CFO refinement only on continued short positives

The causal policy avoided **93 of 401** fixed-epoch refinements on physical DS30-0016, preserving **211 of 239** original CFO edits. The single saved publication completed with **0.976 km fixed-zero and 1.452 km fitted error**, improving on the original all-paid result by **33.6 m and 106.0 m**. North avoided **600 of 996** refinements and kept the complete payload of the all-paid history route, including all retained CFO measurements. [Frozen protocol](continued-cfo-protocol.md) · [Exact lane census and saved publication](measurements/continued-cfo.json.gz)

## Paid work and held-route margins

The released continuation advances on every original probe. It sees full anchors, weak short rows and empty or rejected opportunities at their actual counters. Only original supported short positives can request a 20 ms frequency update. The held-anchor EOF selector still scores the pre-refinement packets with its original masked anchor training. A history result uses the already recorded original chronological retention decisions. An unfiltered result retains every original factor and restores its original CFO wherever refinement was skipped. The policy receives no region, position or labels. [Receiver-side policy](continued_cfo.py) · [Released held-cycle selector](held-anchor-route-publication.md)

| Saved recording | Held log-score gain by radio, nats | Route | Short refinements, all-paid → selective | CFO edits, all-paid → selective | Selected factors |
| --- | ---: | --- | ---: | ---: | ---: |
| Physical DS30-0016 | −15.273 / −8.948 | Unfiltered | 401 → 308 | 239 → 211 | 475 |
| Public North | +28.366 / +26.345 | History | 996 → 396 | 460 → 396 | 456 |

Weak radio 0 avoided 59 of 272 calls and kept 150 of 169 changes. Radio 1 avoided 34 of 129 calls and kept 61 of 70 changes. North retained 198 short refinements per radio and avoided 304 and 296 calls respectively. Its 64 other CFO edits belong to lanes discarded by history. Both policies yield the same complete **456-factor** North history payload at SHA-256 `483155e97fc42ca00ee5ea19d5dc24385496aa056f5ad6298f52247f10fdabdc`. The new detector recipe identifies the causal work rule separately. No new North position run was required for this equality check.

The original all-paid receivers spent **319.136 CPU ms** on weak refinement and **899.564 CPU ms** on North refinement. Their receipts aggregate the clocks across lanes. Thus the **23.2% / 60.2%** avoided calls are exact work counts. Under equal per-call cost, they would correspond to about **74 / 542 CPU ms** before the added causal gate. The price driver spent **8.359 / 10.900 CPU ms** in its saved chronology and authenticated before/after lane join, outside the EOF selector and the saved solve. This is a separate diagnostic clock. The trial measured zero new raw refinements or raw speedup.

## One current weak saved publication

| Genuine measured input replay | Fixed-zero error (km) | Fitted error (km) | Fixed-zero RF RMS (Hz) | Fitted RF RMS (Hz) |
| --- | ---: | ---: | ---: | ---: |
| Original unrefined mixed packet | 1.311046 | 1.694025 | 121.526 | 120.291 |
| Original all-paid refined packet | 1.009776 | 1.557704 | 118.260 | 117.490 |
| Selective unfiltered | **0.976164** | **1.451671** | **116.340** | **115.526** |

All three retained the same **116 ordered owner and role rows per arm**. The selective packet changed only signed CFO on the 211 selected short rows. Its distinct native recipe, same acquisition authority and same issued/admitted timeline bound the original offer and staged causal archive. The ordinary current path paid the original final fit, exact Graph, paired 179-point grid and complete position path. All eight encoded PNGs and independently decoded hashes passed the standard store checks, and the numerical sidecars point to the actual position image. The saved subprocess took **5.386 s elapsed / 5.383 CPU s** through exit, including **2.726 CPU s** for the scientific solve. No other solve or original archive read occurred. Both originally attempted worker starts stopped during imports before any solver; the retained run reused the sealed price and verified packet. [Earlier genuine physical comparison](raw-cfo-0016.md)

The executable policy is a scoped opt-in for the existing fixed-epoch CLI. This trial exercised its exact measurement selection and EOF projection from sealed inputs. The optional live wrapper did not run. Eight component and adjacent tests passed, including causal advancement across rejected positives, full anchors, empty rows, and restoring pre-CFO signed chronology.

To reproduce on the existing saved inputs, run `continued_cfo_trial.py run NEW_TMPFS_ROOT` as the established archive-readable Gauss account, using the pinned release Python, shared low-priority CPU 2 lock, nice 15, I/O priority 7 and one numerical thread. Its only new publication consumes the sealed weak handoff and denies waveform calls. [Saved driver](continued_cfo_trial.py) · [Component tests](../../../tests/pipeline_eval/test_continued_cfo.py)
