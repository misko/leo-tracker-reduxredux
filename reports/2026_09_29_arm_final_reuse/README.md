# Exact final-score reuse

This prototype adds window-local exact-key caches to the preferred fine-2
integrated scorer. Final GLRT keys contain refined epoch, the exact binary64 CFO
bits, and sample count. Boundary-conditioned keys contain refined epoch, the
initial fine-CFO bits, and sample count. Cached values are copied bit-for-bit.

Candidate objects, logical conditioned-fallback flags/counts, and logical
conditioned screened/rechecked-bin counters remain unchanged. New row fields
report physical `actual_executed_glrt_calls`, `glrt_cache_hits`, and
`conditioned_cache_hits`; GLRT and conditioned CPU timings contain executed work
only. Both caches are automatic variables inside one `leo_full_search_run`, so
they reset between every window and receiver call.

The component test covers exact cache parity, adjacent representable CFOs,
different sample counts, logical counter replay, cache reset, and all four
sample rates. Host and sanitizer tests execute locally. ARM is cross-build only.
