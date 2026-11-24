# DS30-0086 verify-only member budget

The existing native drain is the closest qualified path for a wholly omitted member. It verifies the full encoded member and signed index, decodes each required byte once into a reusable scratch window, and checks the individual and whole decoded digests. It avoids native DSP and full decoded array construction. On DS30-0086, the archived drain's **decode and decoded SHA alone** would exceed the replacement budget even after generously crediting all old omitted-member verification and a proportional share of worker prefetch CPU. A new omitted-member port would add complexity without a supported path to 2×. [Read-only timing receipt](measurements/omitted-member-verification-0086.json) · [Existing native drain trial](native-verified-drain.md)

## What the three-of-four result already buys

The original matched comparison measured **91.270 s** for installed ALGO08v3 and **58.836 s** for the field 20/8 successor. The fixed member schedule omits receiver work on **26 of 106** originally signed members, comprising **1,664 visits**, **2,063,448,504 encoded bytes** and **2,662,400,000 decoded bytes**. It avoids the projected full/short costs for 300 / 2,044 actual radio opportunities. Its measured matched saved solver cost fell from **11.333 to 8.030 s**. These measurements do not include a new raw run. Subtracting the projected **3.740 s** detector reduction and measured **3.303 s** solver reduction gives **51.793 s** with full input verification, against **45.635 s** for half installed time. It would need a further **6.158 s**, or **237 ms net per omitted member** if the retained route stays fixed. The **44.882 s** skip-payload counterfactual gives away authentication and is unavailable under this scope.

The archive query ties the proposed members to their exact signed original whole-coverage receipts, including manifest, compressed, index and decoded digests, geometry and chronology. It reads the saved field timing and scientific envelopes. It does not read original payloads. Every omitted member was a real lookahead hit. No segment-start demand member is omitted.

| Archived original omitted-member envelope | CPU, s | Wall, s |
| --- | ---: | ---: |
| Signed member/index metadata | 0.055 | 0.095 |
| Encoded authentication including consumer handoff | 0.960 | 1.539 |
| Decoder setup and history preparation | 0.004 | 0.004 |
| Native decoded read | 1.821 | 1.920 |
| Per-window and whole decoded hashes | 0.745 | 0.771 |
| Sum of the above clocks | 3.586 | 4.329 |

The per-member phase clocks use process accounting; asynchronous worker work can be inside their elapsed/CPU intervals. Removing all **4.329 s** of recorded main-side envelopes and making their replacement free would still leave **47.464 s**, keeping worker time aside. The field worker has no per-member CPU split. A deliberately favorable model also subtracts **3.613 s** of old worker CPU by the omitted share of the **prefetched** bytes. This can credit overlapping work twice and assumes every reduced CPU second also reduces wall. The resulting **7.942 s** credit leaves only **1.784 s** for all replacement verification, or **68.6 ms per complete member**. The omitted compressed files still need to be read and hashed. This budget is a scale comparison against measured historical work, not a hardware lower bound for all possible decoders. [Lookahead accounting](rolling-input-budget.md)

## What the complete exact drain has paid

The two established dense physical reverse-order controls processed **128** wholly unpaid visits. Both compared the released reader against a native scratch drain using one reusable **1.6 MB** window; both sealed the same original opportunity and sparse detector document on that fixture. The native arm verifies frame completion and checksum, correct decoded byte counts and both levels of decoded SHA. Its test harness exposes metadata only after verification and gives back no omitted I/Q array. Replica trials started cold on the private staged dense extents and covered **204.800 MB** decoded per pair of members; DS30-0086 also has exactly 102.4 MB decoded per omitted member. Its omitted members are larger on average in encoded bytes. The table nevertheless scales by decoded-member count with no extra encoded-byte charge. [Measured reverse-order drain receipts](measurements/native-verified-drain.json)

| Previous fixture and conditional transfer | Reversed-order range |
| --- | ---: |
| Verified ordinary vs native tail, CPU per two members | 271.1–273.8 → 246.8–248.4 ms |
| Full native tail, wall per two members | 269.2–307.3 ms |
| Native tail decode + decoded SHA CPU per member | 79.5–79.8 ms |
| Paired CPU saving transferred to 26 members | 0.316–0.330 s |
| Full verified replacement CPU transferred to 26 members | 3.209–3.230 s |
| Full verified replacement wall transferred to 26 members | 3.500–3.994 s |
| Whole optimistic model with donor decode + decoded SHA only | 45.918–45.925 s |
| Whole optimistic model with full donor CPU treated as wall | 47.059–47.080 s |
| Whole optimistic model with the donor's measured elapsed | 47.350–47.845 s |

That optimistic model holds the saved solver improvement and all the already credited DSP suppression. It then replaces the real old omitted work rather than crediting the paired drain gain a second time. Even charging donor decode and decoded SHA alone, while giving away encoded read, encoded SHA, index, bookkeeping and any exposed I/O, takes the full model above the target. The prior paired CPU saving is against an older released reader and may not transfer to the field's optimized fused decoder. The warm first-third streaming trial also found only **1.8–2.8 ms CPU** saved outside native callbacks when it eliminated 86 CI16 arrays. Those effects overlap the drain path. [Warm boundary and required per-visit checks](first-third-ingress.md)

## Exact implementation boundary

- Keep the original read-only member and manifest authority. Authenticate the complete encoded byte string and original index using the normal storage port. Traverse the authenticated rows in sequence, validate geometry, consume the exact checksummed frame, and check every independent window hash and final whole-decoded hash. A single reusable scratch window is sufficient. The original member cap and unsupported-layout fallback in the native checker already provide this mechanism. [Native checker and original-reader fallback](native_verified_drain.py)
- Suppress omitted DSP and measured probe construction in a private acquisition port. Preserve the original signed per-visit metadata, exclusion classification, delivery clocks, global hardware counters and original modulo-eight admitted anchor progression. The 0086 sampling recipe uses strongest independently on retained lanes. It does not measure omitted lanes or feed them to continuation. The original drain timing fixture retained metadata and emitted explicit empty opportunities for its own different continuation policy. Those timing rows cannot be treated as measured negatives on the new recipe. Seal only after every retained and omitted member completes authentication.
- The prefix-SHA reuse work addresses private seekable encodings with independent prefix digests. Original DS30 members have no independent prefix hash to reuse. The paired decoded SHA already updates the window and whole decoded contexts in one pass. Existing legacy-seek sidecars authenticate selected windows using a separate derived validation statement. They cannot substitute for recomputing each original decoded check in this trial. If an unsupported native layout requires fallback, keep its already authenticated compressed snapshot through the released checking path using the existing snapshot borrower. This avoids the standalone drain fixture's fallback reread while retaining exact checks. It supplies no saving in the two donor runs, which had zero fallback. [CI16 prefix SHA context](ci16-sha-reuse.md) · [Original full-coverage requirements](authenticated-input-coverage.md) · [Same-snapshot fallback](legacy_first_map_input.py)

The saved data support the existing drain as an exact implementation reference. No additional raw trial or new intake port was warranted by the available budget. The ordinary field workflow and pending challenge remained untouched. The regenerated read-only receipt SHA-256 is `0e357a6c6eda13693d64cc1e586b42baf376de86cf3835034dd26a894be88684`.
