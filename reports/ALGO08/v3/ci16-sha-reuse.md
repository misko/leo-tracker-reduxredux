# Reusing the CI16 prefix SHA-256 state

Sharing one SHA-256 prefix update saved **15.263 ms** on DS30-0008 and **30.223 ms** on North through the writer and fully verified first readback. Both pairs produced the exact same private capture and seek-table digests. The isolated hash profile and the parts of the paid run that changed support roughly **16–18 ms per 64-window member** across writing and reading. The larger North end-to-end difference includes about 12 ms outside the measured changed work. [Protocol](ci16-sha-reuse-protocol.md) · [Receipts](measurements/ci16-sha-reuse.json.gz)

## Disjoint cost estimate

Both inputs are authentic resident first members with 64 full stereo windows. Each has 40,960,000 bytes of 8 ms prefixes. The 12 ms tails and total decoded payload are respectively 61,440,000 and 102,400,000 bytes. The existing path hashes each prefix for its own pin, then reads it again through full-window SHA-256. Timed on actual owned input, North and DS30-0008 spent about 9.2–9.4 ms CPU hashing the standalone prefixes per pass. Extending the unfinished context through the tail avoids the second visit to those bytes. In opposite repeated orders it saved **8.694 ms** on North and **7.899 ms** on DS30-0008 in the complete isolated join-and-hash loop. Concatenating the two views into the full window separately cost about **5.3–6.3 ms** in the original passes. This estimate joins views of the original owned buffers. The timed first-use reader kept its existing join of decoded parts.

The prefix digest finalizes a snapshot of the live `hashlib` state. The continued context receives the real tail bytes. The tail SHA-256, both encoded-part checks, exact decoded lengths and each ordered member SHA-256 remain independent. There is no change to the format or authority. For the scoped private writer the full owned window is still verified before it is emitted. The existing partial read path still independently authenticates the requested prefix. The complete reader still returns the contiguous window already required by the native detector. Empty and shortened parts keep their original values and eligibility rules.

The installed paired SHA-NI helper shares the schedule for two independent contexts on a single contiguous input. Its current window API initializes a fresh window hash on each call. Using that API separately for the two parts cannot continue the prefix context for the original window digest. Combining the optimizations would require a separate native interface. The measured variant uses the existing `hashlib` interface and needs no new native code or CPU capability. [Existing paired SHA primitive](../../../tools/pipeline_eval/variants/experimental/paired_sha256.c)

## Writer through first complete readback

| Wall clock scope | North original → reuse | DS30-0008 original → reuse |
| --- | ---: | ---: |
| Durable writer and private root | 138.409 → 130.186 ms | 104.099 → 96.092 ms |
| First complete authenticated readback | 179.428 → 157.426 ms | 125.128 → 117.872 ms |
| Decode, join and decoded SHA checks within the readback | 113.215 → 103.579 ms | 78.929 → 70.024 ms |
| Writer through verified readback | 317.834 → 287.611 ms | 229.226 → 213.963 ms |

The single pair ran original first on North and reuse first on DS30-0008. Both consumed the same immutable owned CI16 bytes and original chronological index. Each complete readback authenticated all 128 encoded parts, 64 window digests and the original whole-member digest. Every paid phase recorded zero major faults and input blocks. The exact input bytes and RF/timing metadata offered to the receiver therefore stayed the same. This comparison ended at the verified source port, before DSP and solve.

Applying only the supported saving to the earlier 1,200-visit North prototype would recover about **0.31–0.34 s** if the first-member costs held. That is short of the **1.374 s** needed to reach 1.6×, and a full recording was outside this test. There is no saving on original unconverted Zstandard input from this change. [Full direct North result](north-direct-multichunk.md)

## Reproduction

The opt-in argument is `reuse_prefix_sha=True` on the private capture writer and reader. With the original CI16 test inputs, shared Gauss CPU 2 lock, installed Python and existing single-thread interpreter settings, run `python -Bm reports.ALGO08.v3.ci16_sha_reuse_trial /dev/shm/<fresh-root>` for the digest census and use `--compare` at a second fresh root for the paid pair. Commit `22f2bac18` contains the measured source. Forty-two focused tests passed, including genuine empty and partial extents, archive bytes, and wrong raw or encoded digests.
