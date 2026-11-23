# Catalogue priming at outstanding member demand

The warm physical-prefix replay exposed **at most 4.214 µs** across both next-member joins. Every future was ready at demand, and the candidate did zero speculative TLE work. The combined run gives no evidence of a useful warm scheduling opportunity on this fixture. [Common-clock intervals](measurements/catalogue-read-overlap-DS30-0008.png) · [Full trace](measurements/catalogue-read-overlap-DS30-0008.json.gz)

## Combined replay boundary

The fixture uses the first 24 verified duplex DS30-0008 visits, split into three legacy members of eight visits. Setup reads the already-staged first original member under a 75 MiB compressed and 100 MiB decoded bound. The derived fixture occupies 29,173,861 bytes under a 32 MiB bound. Reframing preserves ordered I/Q hashes, target metadata, sample counters, and clock brackets. Every arm reproduced 48 full-short probe rows and 30 selected factors from the earlier signed prefix. Control and candidate emitted the same sealed packet SHA-256 `7e4c4424e904920dc93fc214d471afdcf3ffde83c34334ec32c59d6cba1e8c40`. All nine replays used the same fixture, CPU 2, nice 15, best-effort I/O priority 7, and the Gauss lock. [Signed receiver trace](ready-io.md) · [Fixture and receipts](measurements/catalogue-read-overlap-DS30-0008.json.gz)

When the next-member caller reaches `Future.result()`, the candidate offers one complete, past-only TLE body if the current member read is still active. The first verified I/Q index supplies the UTC cutoff, `1794556783056720638`. The later acquisition packet reauthenticates that same clock. The existing 48-hour catalogue query then selects and verifies every body in its ordinary order. Only the content-keyed parser cache crosses the handoff. The priming cap is 4 MiB and the ordinary archive query cap is 64 MiB. The measured scope includes signed acquisition, sealing its packet, the paid primer, and the resulting causal catalogue query. It ends before Graph-dependent orbit preparation and position inference. [Runner](catalogue_read_overlap.py)

## Real and controlled waits

All eight real warm demands arrived after their futures completed. Each join took **1.08–2.23 µs**, including the ready-future call overhead. There were no charged filesystem input blocks or block-device read bytes. The raw process timings ranged from 1.143 to 1.344 s with no work moved. Only join latency is eligible for overlap on this warm fixture. The separate earlier cold measurement remains evidence of real exposed demand wait on its larger original members. [Warm receipt](measurements/catalogue-read-overlap-DS30-0008.json.gz) · [Earlier original-member experiment](ready-io.md)

The controlled comparison lets each real `readv` complete, then delays its worker future by a requested 160 ms. It tests work placement while the caller waits for a completion. The delay is injected and supplies no estimate of physical read latency. Times below are elapsed unless marked CPU.

| Controlled pair | Remaining join 1 serial → overlap, ms | Remaining join 2 serial → overlap, ms | Priming CPU, ms | CPU inside scheduled holds, ms | Paid wall serial → overlap, s | Paid CPU serial → overlap, s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| A | 105.397 → 51.553 | 129.729 → 86.081 | 96.960 | 96.960 | 1.643 → 1.529 | 1.408 → 1.391 |
| B | 101.054 → 51.919 | 132.778 → 0.008 | 276.012 | 183.585–183.703 | 1.889 → 1.518 | 1.641 → 1.456 |

Pair B's second atomic operation ran 92.428 ms past the scheduled timer end. The worker reported completing that hold at 229.483 ms, later than the requested 160 ms. The interval calculation credits only CPU the monotonic entry and exit clocks can place inside the earlier of the scheduled and observed completion boundaries. It subtracts the maximum wall time that could house CPU outside that interval for the lower bound. The whole-path deltas include run variation in catalogue processing. They cannot isolate a production wall saving. [Timeline with scheduled hold ends](measurements/catalogue-read-overlap-DS30-0008.png) · [Per-call evidence](measurements/catalogue-read-overlap-DS30-0008.json.gz)

## Consumed work and fallback

Both controlled candidates read 3,577,452 extra verified TLE bytes and turned two first authoritative body accesses from misses into hits. Each branch still made the same 33 authoritative reads in the same order, totaling 59,005,989 bytes, and selected the same 11,177 past objects. The output digest covers provenance, ordered names, and canonical SGP4 element export. Every matched successful leg read the full 29,173,861-byte physical prefix through the same reader and verified each member. No deferred bytes or incomplete work contribute to the comparison.

The fault arm rejected the second speculative parser preparation after paying for its archive read. This cleared the speculative cache and restored the ordinary 18-hit, 15-miss query. A separate fault on the second prefetched I/Q buffer forced the released verified demand reader to reread 9,685,358 bytes. The ledger charged 38,859,219 member bytes, including the unsuccessful speculative read. The causal output and detection packet remained identical, and the patched ports were restored after each arm. [Byte ledger and outputs](measurements/catalogue-read-overlap-DS30-0008.json.gz)

Seven component and adjacent tests passed. The uncompressed complete receipt has SHA-256 `c26960aadf8cae74bec730260551f910634a4b547d7d0839dc390a317be9d44a`. The older benchmark priced priming separately and used a larger manifest-derived 48/72-hour plan. This measurement uses the verified first-window cutoff and stops at the ordinary 48-hour catalogue consumer. [Earlier priming boundary](catalogue-prime.md) · [Tests](../../../tests/pipeline_eval/test_catalogue_read_overlap.py)
