# Bounded owned-window literal pairs

The bounded decoder **increased complete signed-reader CPU by 11.682 ms per paired repetition** on the resident dense member. Complete wall increased by 10.696 ms. Both order splits regress. The candidate stays out of the combined path. [Six paid pairs and admission](measurements/zstd-literal-pair-clock-0008.json)

The paired reader matched every byte and signed index row of the field's existing verified-once owned-window path on genuine DS30-0008 and DS30-0016 first members, including the dense mixed block. Both copies reached verified EOF. The first yielded read-only window remained valid after all 64 windows and stream closure checks. These two off-slot checks reused detached existing tmpfs files with complete resident pages at both boundaries. No receiver or solver ran. [Dense byte equality](measurements/zstd-literal-pair-owned-0008.json) · [Weak byte equality](measurements/zstd-literal-pair-owned-0016.json) · [Earlier arena prototype](zstd-literal-pair.md)

| Cost or scope | DS30-0008 | DS30-0016 |
| --- | ---: | ---: |
| Paired literal blocks / total | 780 / 782 | 782 / 782 |
| New Huffman tables / actual mixed blocks | 495 / 1 | 304 / 0 |
| Primary resident paired state and plan | 131,320 B | 131,320 B |
| Stock decoder state for the mixed seam | 95,992 B | 0 B |
| Borrowed original history at the seam | 524,288 B | 0 B |
| Bytes copied at the seam | 0 B | 0 B |
| Owned window allocation, stock → paired | 1,731,072 → 1,862,144 B | 1,731,072 → 1,862,144 B |
| Pending remainder copies between owned buffers | 8,732,672 B | 8,732,672 B |

At each window the released reader can decode one original block beyond its signed boundary. With the witnessed original frame block lengths, its equivalent carry copies total 4,276,224 B, so the paired implementation pays an extra 4,456,448 B per member. Its workspace bound no longer includes the 102.4 MB arena. The table parser runs once per new DTable outside the mixed seam. In the paired bitstream tails, each first symbol occupies one aligned canonical prefix run, so the exact terminal bit width follows by finding its sibling boundaries in the existing X2 table. The stock mixed seam uses its own ordinary table parse. A single native structural planning pass determines eligibility, and checksum accumulation follows original ordered windows. Peak process RSS from the untimed byte comparisons includes both complete encoded snapshots, and the dense process observed 1,320 input blocks after setup; all eligible waveform paths are resident tmpfs. [Owned context and checksum](zstd_literal_pair.c) · [Existing owned-window layout](legacy_fused_history.c)

The small adapter changes only the unindexed native decode functions of the existing `FusedMember` in a controlled opt-in call. Window ownership, compressed and decoded SHA-256, index verification, read-only output and publication placement remain existing behavior. Unfamiliar framing uses the unchanged decoder immediately. A native read or EOF refusal can reopen only the same vetted compressed snapshot, burn and discard already delivered original ordinals, and resume at the next undelivered window. A generated backreference begins on a caller window boundary and exercises the bounded extra slab. Component tests cover this path, an injected restart after one already delivered window, and original CRC failure on both routes. [Owned decoder adapter](zstd_literal_pair_owned.py) · [Tests](../../../tests/pipeline_eval/test_zstd_literal_pair.py)

The timed comparison is six AB/BA repetitions per fixed member with the exact field history and paired SHA-256 libraries. Clocks begin before the fresh signed manifest reader and end after its decoded EOF, full digest and close. Native read, handoff, compressed authentication, faults and complete CPU/wall are available separately. The detached fixture is explicitly resident, and the comparator does no cold read or DSP. Each source is opened by its original owning account so the two fixtures have separate trial scopes. The dense mixed member is the primary timing fixture. Its isolated launcher admits only a fresh official DS30-0218 storage deferral with completed stock, pending successor and no child, then inherits one nonblocking Gauss lease in one 12-second slot. Ordinary field work retains priority. [Paid comparator](zstd_literal_pair_clock.py) · [Admission capsule](zstd_literal_pair_clock_capsule.py)

The older dense stock model priced up to 23.76 ms/member from a hypothetical 2× within isolated Huffman traversal. The measured first 62 candidate pairs spent 458.486 s on 5,758 complete decode members, averaging 79.63 ms/member across the field mix. The remaining 213.127 s target requires average **37.01 ms of additional paid gain per field member** if all were eligible. A measured resident per-member delta cannot certify either field eligibility or that whole-stage reduction. [Dense kernel measurements and separate decoder ceiling](zstd-literal-pair.md)

## Paid resident dense comparison

The first capsule obtained the correct official deferral and released its nonblocking lease, then exited before any waveform bytes or measured arms because its own Python open hook trapped the intentional mount-denial probes. The corrected shared startup runs the kernel isolation probes first, then installs the Python path allowlist, loads the exact library bindings and verifies the inherited Gauss FD. The no-waveform preflight runs these same checks at the same file-owner privileges on CPU6. It opens and closes the three approved paths without reading any payload. The authorized retry used fresh official deferral age 410 ms and exited zero after 3.440 s, before the next ordinary event at a 32.10 s interval. [First startup refusal](measurements/zstd-literal-pair-clock-startup-refusal.json) · [Shared-startup readiness proof](measurements/zstd-literal-pair-clock-ready-0008.json)

| Paid scope | Stock median | Paired median | Median within-pair change, paired minus stock |
| --- | ---: | ---: | ---: |
| Verified member total, CPU | 172.435 ms | 185.042 ms | +11.682 ms |
| Verified member total, wall | 174.148 ms | 185.046 ms | +10.696 ms |
| Native read, including window handoff and frame EOF, CPU | 56.026 ms | 70.016 ms | +13.894 ms |
| Paired complete and per-window decoded SHA-256, CPU | 23.957 ms | 23.835 ms | −0.112 ms |
| Complete encoded read and SHA-256, CPU | 90.286 ms | 89.173 ms | −2.347 ms |
| Native plan and state setup, CPU | 0.177 ms | 0.186 ms | +0.012 ms |

The paired CPU penalties were **+11.698 ms stock-first** and **+10.156 ms paired-first**. Across all six repetitions stock/paired totaled 1.036127/1.108453 CPU s and 1.043611/1.117093 wall s, corresponding to 0.9348× and 0.9342× paid speed. All 12 arms verified the original 77,442,779 encoded bytes, 102,400,000 decoded bytes and 64 ordered windows. Each candidate activates the same 390 paired calls, stock mixed block and singleton, with no restart. Host residency shows complete fixture pages before and after. The first stock arm incurred 528 process input blocks, retained in the sums, and the remaining arms had zero. The detached fixture's residency does not price a cold source. [Per-arm and split clocks](measurements/zstd-literal-pair-clock-0008.json)

The wall clock covers the sandbox launch through exit. CPU inside the actual numerical child is directly measured in each arm and totals 2.144580 s for all 12 paid arms. The wait-level `external_process.cpu_s` field counts only helper processes accounted to the host launcher and omits CPU below the detached namespace boundary. The outer field cannot represent complete trial CPU. DS30-0016 has exact byte parity only. The experiment measures no decoder savings and provides no estimate of a full-recording improvement.
