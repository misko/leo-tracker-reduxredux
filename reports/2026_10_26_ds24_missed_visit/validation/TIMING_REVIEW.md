# Independent timing source review before numerical freeze

2026-10-26 21:40 UTC. These are pre-outcome findings; no timing control/raw
outcomes were opened here. The callable staging adapter already reflects the
agreed confirmation-only gate and same-mode comparison requirements.

1. **Whole-bank raw ownership:** current interval partition and geometry appear
   to keep interpolation guards inside a single preassigned native interval.
   Independent audit must regenerate geometry for every coarse/fine mode and
   point alternative, not only `native_search_blocks` of the final winner.
   Full public scorer parity, including wrapping/fractional epoch, remains
   required before raw comparisons.
2. **Same-mode point comparator:** the source currently inspected still chooses
   primary mode0 at offset0. Root's requested revision must select the best
   zero-offset proposal among the same earlier modes on search frames, then
   seal and confirm it once. Otherwise a search/point gain mixes timing search
   with mode selection. Preserve primary rank0 as descriptive if desired.
3. **Selection callback:** inspect the actual harness callback and durable
   artifact. A returned `confirmation_accessed=False` field alone does not prove
   order. Both point and search selections must be bound by the callback before
   any confirmation call. An instrumented call-order test and full confirmation
   redaction test are appropriate independent checks.
4. **Search threshold:** current `confirmed` now correctly uses confirmation
   margin plus earlier-frequency compatibility; search margin is diagnostic.
   This is consistent with the split-power clarification. Nulls must repeat
   the actual selection, confirmation and compatibility policy.
5. **Enriched generation mapping:** `prediction_packets.json` now has integer
   `header.generation` and string `header.stream_generation`; each donor has the
   same two distinct fields. The inspected timing `adapter.py` still copies
   `donor['generation']` into its `support.stream_generation` and similarly
   `header['generation']` into target stream_generation. When given the enriched
   packet, this relabels the integer generation as the stream label. Preserve
   `stream_generation` explicitly (fall back to old generation only for the
   original unenriched input), while native_generation comes from each public
   native authority. No numerical forecast needs to change.
6. **Reference times and interpretation:** midpoint CFO/rate conversion and
   midpoint-anchored constant epoch are explicit. The per-frame CFO model removes
   earlier predicted evolution, not a donor posterior. Confirmed pilot and
   earlier-width compatibility remain separate; a far FFT winner is not proof
   of donor continuity or satellite identity.

Resolution after the pre-freeze source amendments: point and search now share
the mode set, search gate is diagnostic, and enriched stream/native generation
mapping is preserved. Four independent mocked-call/geometry/metadata tests pass
in0.27s (`test_timing_boundary.py`). They verify a durable callback before both
confirmations and union-of-bank guard disjointness, without running RF controls.
The actual final harness, callback artifacts, parity and null/known-truth controls
still need review. See `timing_review_resolution.json`.

The predictor ownership handoff is independently audited by `packet_audit.json`;
all576numerical forecasts remain exactly unchanged after removing the added
metadata. These review notes do not authorize raw scoring or position execution.
