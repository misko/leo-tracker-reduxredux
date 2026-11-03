# Native scanner v2 timing audit

The post-fix 120 ms-ceiling smoke passes every source-counter timing check. The
audit covers 374 visit records (373 intact, one wall-deadline partial visit),
with zero missing samples in the run receipt. It validates the maintained
physical-validity formula, profile/recall transitions, non-overlapping visit
intervals, stable target/profile/frequency bindings, counter ordering, and the
3,000 ms committed-valid-start revisit bound.

The largest post-fix revisit was 2,799.8296 ms, from target 2 visit 316 to visit
334. That leaves 200.1704 ms below the configured limit. No timing violation was
found.

The subsequent 360 ms-ceiling run also passes with zero violations across 374
visit records. Its maximum revisit was 2,660.1236 ms; all 286 recalls used the
nominal branch and none were late. This ceiling did not activate during the
run because all completed feedback was quiet, so observed dwells remained 120
ms; it still supplies an independent post-fix timing trace.

Fresh source snapshots materially changed the counters used for admission. In
the post-fix log, every one of the 373 selections after the first visit is newer
than the preceding valid end. The selection-minus-previous-end interval has a
19.9960 ms median, 21.0580 ms p95, and 35.7584 ms maximum. For recalled visits,
the fresh selection-to-recall-before age has a 2.3856 ms median, 2.5140 ms p95,
and 12.4696 ms maximum. In the pre-fix 180-second log, the latter median was
19.9682 ms and its maximum was 45.3284 ms, showing that admission commonly used
the prior DMA watermark before the per-visit snapshot was added.

All 285 post-fix recalls completed before the nominal `selection + 20 ms`
boundary; there were zero late recalls and 89 same-profile visits with zero
transition. Recall counter duration had a 0.0612 ms median and 0.4652 ms
maximum. Because all recalls took the nominal branch, the measured
post-recall-to-valid-start guard ranged from 7.4804 to 18.3212 ms, with a
17.5532 ms median. This is consistent with the maintained formula: a recall
that completes before the nominal boundary consumes part of the 20 ms
selection-to-valid interval; a late recall would receive a full 20 ms guard
after `counter_after`.

The historical failure remains present and unchanged in the comparison
receipt. `corrected-120ms-ceiling.jsonl` still reports its sole violation:
target 2 visits 560 to 580 span 3,020.152 ms, exceeding the bound by 20.152 ms.
That log contains 485 late recalls. Its event file SHA-256 is
`0df475403cee833612afc60baa0d4963cc35c0c95e00b0039b0c416ebefb649c`.
The post-fix event file SHA-256 is
`b30ee2b5e313a5666436845483ba32a246fa3cf71e20891778850a297d517bc3`.

The reusable auditor is `audit_v2_timing.py`. It returns zero for clean logs and
one when any invariant fails. Run it over a later event/v2 log with:

```sh
python3 audit_v2_timing.py --output later-timing-audit.json later.jsonl
```

Use `--allow-failures` only when producing a historical comparison that is
expected to retain known failures. `timing-audit.json` is such a comparison: its
top-level status is `fail` because the old breach is deliberately included,
while both post-fix log entries are independently marked `pass` with zero
violations. The post-fix release is `32c6f7df4158814778d7`; the live receipts
confirm clean source close, owner deactivation/release, and radio restoration.
