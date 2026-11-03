# Native adaptive tracking

This component reconstructs alias-aware CFO tracklets from projected scanner
candidates.  It implements the bounded weighted Hough search used by the
published server path with the deployment profile frozen in `Config`.

`leo-tracking` accepts a tab-separated file with this header:

```
candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\tactual_rf_hz\tsupport_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\tmeasured_cfo_hz\texact_score\tcontrol_score\tmargin
```

Its `TRACK` rows contain the weighted-Hough segment identity, server-compatible
tracklet identity, geometry, and fit.  Its `POINT` rows contain membership and
alias choices.  A tracklet identity is emitted only for the frozen deployment
profile because that identity binds every server configuration field.  The
format is a private replay boundary for qualification; it is not an
application persistence contract.

The narrow input deliberately stops at track construction.  It lacks recording
authority, source sample bounds, uncertainty, and factorial support moments,
so it cannot truthfully create the server's complete episode graph, graph
content digest, support digest, or randomized partition mask.

Build and run the unit test with `./build.sh host`.  Use `sanitize` for the
address/undefined-behavior build, `thread` for ThreadSanitizer, and `arm` for the
Cortex-A9 cross build.

The additive `LaneExecution` overload accepts a borrowed synchronous dispatch
port. Existing overloads and a null port remain serial. The component creates
no threads and retains no executor state. A dispatcher must finish every
callback before returning or throwing; workers can process independent lanes,
while results and exceptions are consumed in original lane order. Duplicate,
out-of-range or omitted indexes are rejected. Callbacks that outlive dispatch
are forbidden because they borrow reconstruction state. Each concurrent lane
has its own bin and fit cache, so the caller must budget additional memory.

The production replay CLI accepts `CANDIDATES.tsv --workers 1..4`. Its optional
parallel strategy uses the existing bounded runtime executor and drains work
before releasing callback arguments, including on failure. The default stays
serial, and no live application worker count changes. The build enables this
CLI option explicitly; frozen research builds can still compile the historical
serial-only CLI against their frozen tracking implementations.

`test_lane_execution` compares reversed concurrent lane completion with serial
results, exercises cold/extended/reused persistent prefixes, injects a lane
allocation failure and verifies joined callbacks and cache recovery, and rejects
duplicate, missing and out-of-range dispatch. It also checks executor failure
propagation. Scientific configuration and persisted identities do not depend
on the execution strategy.

Source-group selection binds each lane's immutable candidate rows to dense
group indexes once, in the same lexical order as the original ordered map.
Each lane then reuses private best-index, touched-group and result vectors for
raw and refined hypotheses. Synthesized `time:<ns>` fallback groups still
collide with equal explicit IDs, and weight/residual/candidate ranking and the
final time/candidate sort are unchanged. `test_source_keys_internal` compares
the dense workspace with the original owning-map algorithm over boundary,
collision, tie, reset, lifetime, randomized and concurrent lane cases. The
production source is byte-identical to the qualified sidecar experiment, whose
60 causal prefixes and complete 11,747-candidate output match the frozen
source-key-view implementation exactly.

The internal `HoughBin` accelerator preserves the original integer bins. For
512 bins and normal bin width `w`, it first verifies that the spacing is exactly
`512*w`. It computes `q=value/w` only within `abs(q)<2^20`; converting this range
to a signed 32-bit integer and correcting negative truncation gives `floor(q)`.
When the fractional part is more than `2^-20` from either integer boundary,
the low nine bits give the same wrapped bin as the original remainder path.
For IEEE binary64 arithmetic, quotient error in this range is below `2^-32`,
including directed rounding; the original remainder normalization and division
add a much smaller error in bin coordinates. The exclusion zone is deliberately
far wider than their combined bound. Boundary cases, other bin counts, extreme
quotients, and subnormal widths use the original `fmod`/normalization/floor
expression. Residual calculations, histogram summation order, fitting, and tie
breaking are unchanged.

`test_hough_bin` compares the integer output against that original expression
across all four rounding modes, random inputs, adjacent representable values at
positive and negative boundaries, very large/small geometry, and fallback
profiles. Complete DS9 causal-prefix output is also compared byte for byte with
the frozen pre-optimization executable. The qualified accelerator is included
in application release `7f0aa67cbcd1b758`. Alternating physical ARM cold runs
measure 33.52–33.59 seconds versus 39.39–39.62 seconds for the frozen control,
with identical outputs. This does not close the five-second freshness target.

The lane-local exact-fit cache memoizes only refined fits. Its key contains the
ordered point indexes and the bitwise initial slope, intercept, and spacing. A
hash selects an open-address probe sequence, but a hit requires comparison of
the complete key; membership-only reuse is forbidden. The cache preserves fit
arithmetic, hypothesis order, and tie behavior. It has 4,096 slots and an 8 MiB
retained-payload cap per lane. A full table, capacity limit, table-allocation
failure, or optional entry-copy allocation failure runs the original fit and
returns that result. Mandatory fit and output allocations retain their prior
behavior. Each lane owns its cache, with no global mutable statistics.

The internal test injects both optional allocation failures and exercises hash
collisions, a full table, byte limits, ordered-membership changes, signed zero,
and adjacent representable numeric keys. Host and sanitizer tests pass, all 60
causal prefixes match the frozen executable byte for byte, and the ARM tests
pass. The production ARM component reconstructed the complete 11,747-row
fixture in 29.759 seconds with the same output, compared with 33.605 seconds for
the bracketed fast-bin-only control. Release `bc0ce529d530995f` includes this
cache. This remains above the five-second target and does not qualify continuous
real-time operation.
