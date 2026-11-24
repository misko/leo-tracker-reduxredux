# Repeated causal reads and predecessor traversal on the exact named route

The two scans read about 232–234 MB of logical TLE input during each preparation, but the earlier DS30-0316 timings place the **entire verified-read stage at 90–115 CPU ms**. It already parses each distinct body once within a preparation. On DS30-0160, sharing the genuine predecessor traversal with the ordinary predecessor traversal could remove at most **29.1 CPU ms** while keeping the original archive checks and export. The latter missed the frozen 0.10 s screen. Neither optimization was installed or run through a complete publication. [Frozen scope](predecessor-election-protocol.md) · [Bound counts and new preparation audit](measurements/predecessor-election.json.gz)

## Same-request verified reads

Reconstructing the current causal path from the signed local inventories reproduces each filename’s actual logical read bytes for both exact named publications. Starting from the original cutoff, the latest and ordinary previous elections each read the entire 48-hour sequence. The genuine previous election reads the newest publication per content digest within that window. The 72-hour phase history uses the earliest publication per digest. These last two elections deliberately keep different provenance stamps. [Exact named route](exact-named-route.md)

| One preparation of the exact named route | DS30-0160 | DS30-0316 |
|---|---:|---:|
| Latest / ordinary previous / genuine previous / phase reads | 35 / 35 / 25 / 36 | 31 / 31 / 28 / 40 |
| Total original reader calls | 131 | 130 |
| Distinct paths and inodes read | 46 | 43 |
| Distinct content digests read and parsed | 36 | 40 |
| Logical MiB verified | 223.261 | 221.491 |
| Same-path repeat reads | 85 | 87 |
| Same-path repeat logical MiB | 144.861 | 148.225 |

DS30-0316's corrected earlier preparation recorded **90.48 ms CPU** for all 130 original file reads, versus **115.07 ms** in its ordinary case with the same workload. Pricing same-path repeats by byte fraction gives **60.55–77.01 ms** before lookup, cache allocation, confinement and invalidation. These are transferred mean-cost estimates for the same read roster. The earlier full 0316 publication validated 42 native parse inputs, 40 original distinct bodies during preparation plus two derived prior catalogue texts. DS30-0160 showed 95 preparation cache hits from 131 calls and 36 distinct bodies in the actual scope. It lacked an independent read-substage clock on the prior full named publication. [Measured read and parse clocks](portable-orbit-0316.md) · [Native original parser and phase reuse](historical-orbit-index.py)

The installed archive reader checks path confinement, body digest, bound and ASCII on every read. Reusing text solely by filename, reference digest or stat fingerprint would bypass some of that contract. Separate pathnames that declare an identical digest can fail independently. An immutable request view strong enough to preserve the failure semantics would itself need verified setup, and its setup and memory would count against this small opportunity. The existing portable index still pays the original archive reads and recreates request-specific eligibility. [Earlier cross-request cache boundary](tle-source-cache-ceiling.md)

## Measured predecessor ceiling

The DS30-0160 probe used the exact saved named 20 ms detector, signed region, causal cutoff, the current trusted portable index and installed deferred-collection scope. The full preparation took **1.887 CPU s**. Its genuine previous catalogue digest `5cf0556c576ad0d43862118d8c9d90e15d59d93f7d0f3ced0d3b66b5bd7543f6` agrees with the earlier full exact named run. [Predecessor timing receipt](measurements/predecessor-election.json.gz) · [Named history receipt](measurements/named-history-once-DS30-0160.json.gz)

| Genuine predecessor scope, 25 distinct references and 279,708 rows | CPU ms |
|---|---:|
| Original function inclusive | 49.777 |
| Checked body reads | 16.502 |
| Cached parsed-body returns | 0.069 |
| 1,400 canonical TLE exports | 4.141 |
| **Traversal, formatting, receipt and observer remainder** | **29.065** |

A fused candidate could share inspection of the records from the 25 genuine references with the ordinary scan across all 35 references. It would still have to honor the exact ordinary epoch predecessor, the genuine one-second gap and near-duplicate rejection roster, both per-policy orderings under equal epoch and stamp, and the original no-predecessor failure. The 29.065 ms removes all genuine traversal and bookkeeping and therefore overstates what a valid implementation could save. The archived exact DS30-0160 path needs **0.3313 s more elapsed** to meet 1.6× saved, and DS30-0316 needs **5.41298 s**. Avoiding repeated verified reads or sharing these loops offers little leverage against those gaps. [Same-packet named comparison](exact-named-route.md)

For the larger exact preparation opportunity, DS30-0316’s latest combined route uses an earlier index with zero matching body digests. The already authenticated, causal DS30-0306 producer matches 37 of 40 and previously reduced DS30-0316 preparation by **0.381 CPU s** with exact prepared arrays. Applying that existing source election to the current exact route is distinct from avoiding repeated disk reads. It would need its own current-route parity and latency measurement. On 0160, the archived current exact clocks instead place **0.755 CPU s** in the already grouped catalogue rank. Any further useful exact reduction needs to address remaining likelihood work or comparable solver cost. [Previously matched DS30-0316 index](portable-orbit-0316.md) · [Current exact route](exact-named-route.md)

The CPU audit used the installed release Python and `predecessor_election_trial.py NEW_TMPFS_RECEIPT.json` on the shared Gauss lock at CPU 2, nice 15, I/O priority 7 and one numerical thread. It opened no backing catalogue or IQ. There was one preparation audit and no new solver, position or figure launch. Forty-one adjacent archive and index tests passed. [Driver](predecessor_election_trial.py)
