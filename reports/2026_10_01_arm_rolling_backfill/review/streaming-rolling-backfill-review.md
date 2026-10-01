# Read-only rolling-backfill review

Scope: `native/adaptive/tracking/research/streaming_rolling_backfill/` as read on
2026-10-01. No implementation edits or board benchmarks were performed. The
already-reported source-group mean/earliest-candidate issue and actual-time gap
and 32-point fit fixes are not repeated below.

## Final focused rereview

No material backfill correctness blocker remains in the reviewed offline
post-pass scope. The final correction resolves the prior causality, cache, and
atomic-source findings:

- Both the fitted membership and source exclusion set stop at the confirmation
  prefix. Post-confirmation membership no longer affects backfill decisions.
- The cache signature includes lane, confirmation-prefix candidate IDs,
  aliases, and dealiased CFO values. A cache hit checks prefix source-group
  uniqueness and fails closed on an inconsistent entry.
- Candidates are grouped before pre-beginning eligibility is decided. A group
  is eligible only when its complete confirmation-visible time extent lies
  inside the bounded history interval and strictly before the forward
  beginning. Together with the enforced 20 ms group-span limit and the minimum
  four-second confirmation span, this prevents a backfilled source group from
  reappearing in the later continuation.
- Configuration validation now requires finite positive RF/alias and timing
  values, caps history at 32 s and backfill at 16 s, and limits source-group
  center spread to 20 ms.
- Forward and backward fits both honor `maximum_fit_points`, capped at 32.

## Residual offline limitations

1. **Finished/output work is not bounded by the active-bank limit.** Expired
   hypotheses accumulate in `finished` in the forward loop, and finalization emits every
   qualifying unique candidate-ID sequence. Backfill then scans the complete
   input once per emitted track at lines 58-68. Worst-case retained work is
   `O(groups * active)` hypotheses and backfill is `O(output_tracks * input)`;
   `maximum_active_per_lane=24` does not bound either quantity. This is the main
   runtime and memory hotspot on dense inputs.

2. **Rolling births stop after the nearest prior source group even if it cannot
   seed.** The unconditional `break` at line 75 exits after inspecting one
   prior group. If that group has nonpositive candidate time deltas or no
   rate-valid pair, an older group within the maximum gap is never tried. This
   can prevent a causal birth after a timestamp-tied or incompatible group.

This birth behavior is inherited forward-tracker scope and does not invalidate
the backfill experiment, but it can reduce recall.

## Properties confirmed

- Candidate discovery for backfill explicitly restricts centers to the
  confirmation time or earlier.
- Backfill mutates only serialized `Track` memberships after forward tracking;
  it does not feed points or fitted state back into the forward active bank.
- Forward hypotheses add at most one candidate while processing a source
  group. The non-cache backfill path also maintains a source-group exclusion
  set.
- Default forward and backward innovation gates are capped at 5 kHz
  (`2.5 kHz residual + 2.5 kHz uncertainty`), and accepted local fits enforce
  the configured rate and residual limits.
- Backfill remains an offline post-pass. It does not claim bounded streaming
  memory or deployment readiness, and qualification should keep input and
  output sizes explicit.
