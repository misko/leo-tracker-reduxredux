# Six-member physical prefetch admission on Gauss

The six-member cold-XFS comparison stopped before staging on 2026-11-23. Gauss had **69.1–71.8%** full I/O pressure over the previous ten seconds across repeated observations. The `/srv/bulk` XFS logical device was fully utilized in both one-second observations, with **120.45–126.52 ms** mean read wait. The mount had 1.1396 TB free. No compressed waveform payload was copied or charged, no cache advice was issued, and neither reader ran. Staging CPU and elapsed, acquisition rate and signed packet equality for six members remain unmeasured. [Prior two-member cold comparison](physical-short-prefetch.md)

## Authenticated prefix and work budget

The original DS30-0008 segment manifest at SHA-256 `5ffe3ed98feb37f7f7ada44dbf34d2af9d3fcadce567fd3cdbb7e31965a02759` assigns six consecutive 64-visit members, chunk indexes 0–5. Their compressed lengths are 77,442,779, 77,279,318, 77,361,596, 77,371,804, 77,326,904 and 77,527,168 bytes. The compressed total is **464,309,569 bytes (442.800 MiB)**. The decoded extent is **614,400,000 bytes**. Indexes add 1,036,689 bytes and the manifest adds 6,812. One complete private copy would stage **465,353,070 logical bytes** in each direction. The corpus remained read-only. [Original whole-recording receiver](dense-full-short-raw.md)

The signed full-short packet at SHA-256 `ad13073239fe7e4e276debf3c667c0a997408d9efb5e07e309b5ab6fff4d0a85` has **766 probes and 406 verified factors** on this prefix. It records one original exclusion, visit 366, with I/Q digest `sha256:8cf403e9bb6bcc86daadebe0e0f2a1e3dc90bb49114df71570a4b0d66e432f9c`. The same receiver schedule would make 96 full and 670 short 12 ms antenna calls on 383 admitted stereo visits. Reproducing this prefix requires the original exclusion, exact chronological probes, all 384 I/Q digests and both validation layers. The existing two-member validator assumes no excluded visits. [Existing cold protocol](physical-short-prefetch-protocol.md)

Four cold acquisition passes in advice–prefetch and prefetch–advice order would read **1,857,238,276 compressed logical bytes** in total, or **2,321,547,845** including the original compressed staging read. Staging writes and metadata are separate. The one-member worker would read five next members, totaling **386,866,790 bytes per prefetch pass**, inside that pass's total. Matching cache states would require zero payload pages and fully resident indexes on private XFS files before each fresh arm. The planned execution would use the shared low-priority Gauss lock, CPU 2 for both main and helper threads, and a short outer timeout. [Prior resource accounting](physical-short-prefetch.md)

| Complete acquisition rate target | Maximum elapsed on these six members |
|---|---:|
| 231 decimal compressed MB/s | 2.0100 s |
| 250 decimal compressed MB/s | 1.8572 s |

The previous two-member run reached 224.74 and 248.29 MB/s with prefetch and reproduced its original signed factors. Those historical results remain the available cold comparison. [Original measured receipt, SHA-256 `a22f0a1e18be120b3f9cf1f0a620d793d777c24eeb306908697f52bfc40e6765`](measurements/physical-short-prefetch.json.gz)
