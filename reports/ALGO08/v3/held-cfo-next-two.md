# Enrolled half-shrink transfer after DS30-0218

| Frozen execution rank | Original | Issued visits | Official original arm order | Verified at enrollment |
| ---: | --- | ---: | --- | --- |
| 66 | **DS30-0442** | 6,774 | Candidate, installed | Neither role |
| 67 | **DS30-0212** | 6,773 | Installed, candidate | Neither role |

Both cases follow the first 65 already verified originals in the sealed combined export `3fb2f299…`. Selection used case labels, verification flags and the immutable plan order. The roster remains fixed through withholds, zero edits, unscorable outcomes or missing custody. All physical DS30 cases share the Gauss roof. Geographic transfer remains a separate experiment. [Protocol](held-cfo-next-two-protocol.md) · [Metadata-only selector](held_cfo_next_two.py) · [Verified enrollment and custody receipt](measurements/held-cfo-next-two.json)

## Exact original catalogue custody

At census, both original request authorities were available as local NVMe input metadata. The combined pool of seven pinned prior RAM donor manifests contains 144 distinct timestamped catalogue names. The comparison used only those manifests, each original field input's signed archive digest and strict cutoff, and the original historical binding from the committed audit. This produces the following input decisions.

- **DS30-0442 has no exact donor match.** Its cutoff is 2026-11-20 16:56:24.451600218 UTC. The latest name in the donor pool predates that cutoff by 17.911 hours. No eligible suffix reproduced the signed archive digest `be8f0436…`. The controller's input names `/srv/bulk/leo-dev/ds30-full-20261121/snapshot/inputs/DS30-0442/tle`, on XFS device 252:5. The original controller resolves the signed historical binding and archived baseline request, then checks `TleArchiveReader.list_snapshots("space-track")` against the complete original `causal_snapshots` map and cutoff. The local NVMe records bind that input to its archive digest, not a local archive copy. A later approved nonfaulting custody capture could qualify if the complete original roster and all exact bodies are available, with the same digest and cutoff. An observed read subset alone is insufficient for a corrected replay.
- **DS30-0212 has one exact 50-name metadata match** for archive `a1b0110c…` at its original cutoff, 2026-11-16 19:01:25.505581168 UTC. The 0218 stage's manifest covers 48 names. Either the 0086 or 0049 donor supplies the other two. The exact ordered roster and contributing manifest digests are sealed in the receipt. Body presence, residency and SHA verification remain admission checks.

The two raw identity fields for 0442 have separate custody roles. The signed plan accession manifest binds `b89714b4…`. The checked original historical input request binds `58f67db5…`. Both the recording path and issued count agree. Reuse of the 0218 scientific port requires a per-case custody binder that follows the historical request while retaining the independently pinned accession identity. The 0218 case-specific enrollment check requiring those digests to be equal would fail on 0442. The half-shrink algorithm and all its gates remain fixed. [0218 scientific entry](masked-cfo-0218-readiness.md) · [0218 replay and validation contract](masked-cfo-0218-capsule.md)

The resident 0218 controls took 22.876 and 23.521 seconds through exit against the 24-second per-child cap. This leaves less than half a second on the slower control and supports no reserved timing budget for either new case. Shared tmpfs had 176.5 MiB free at census, with a minimum 64 MiB required at later preflight. The 0107 and 0016 work and the 0049 work keep queue priority. Any later replay requires independent authorization, the original verified pair, a private `leo` stage and one idle, freshly deferred official window under the shared Gauss lease. This enrollment opened no post-prefix scientific results, detector packets, TLE bodies, survey or raw data, and took no lease. Five focused tests passed.

```sh
nice -n 15 taskset -c 3 python -m reports.ALGO08.v3.held_cfo_next_two "$frozen_snapshot"
```
