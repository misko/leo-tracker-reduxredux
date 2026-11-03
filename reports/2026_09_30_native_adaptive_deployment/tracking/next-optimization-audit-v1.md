# Next tracking optimization audit v1

## Subsequent physical result

The [root-owned ARM ABBA receipt](one-per-source-rank-arm-v1/physical-arm/receipt.json)
confirms a benefit for the isolated rank-only delta. Control runs take
26.2540/26.1654 seconds; candidate runs take 24.4408/24.2954 seconds, a 7.0265%
mean wall reduction. All four complete serializations have the expected SHA-256
`6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`.
Both physical component tests pass, and peak RSS remains about 22.2 MiB as
reported in KiB by the receipt. These are single-worker standalone tracking
measurements, not application or continuous qualification. Production promotion
and a coherent application rebuild are now the next gate; the audit below
records the pre-promotion investigation.

## Investigation

Production remains unchanged at tracking source SHA-256
`b8f2dff142a190622de5299e229b0ff82c5fe2aa465e386957496dfc8115b1c5`.
The current physical boundary is still far above five seconds: the qualified
standalone two-worker reconstruction is about 14.08 seconds, and the current
integrated two-worker replay reports a 15.476-second maximum publication. The
integrated exact score cache still misses 23 of 59 cadence requests. This audit
does not reinterpret any of those results as continuous qualification.

Prior work leaves one small exact candidate. Fast Hough bin calculation,
bounded bin-index caching, contiguous chosen-point storage, the top-peak cutoff,
exact refined-fit caching, predicate pushdown, and lane parallelism are already
implemented or qualified. The low-memory incremental Hough-prefix experiment
was 22.1% slower on host and is rejected. Dense histogram retention exceeds the
accepted memory tradeoff. The tested lean solver substitutions did not preserve
the remaining DGELSD-sensitive identities. Repeating those paths, changing thresholds, or
approximating residual arithmetic is not justified.

The untried candidate is to make only the two rank tuples in `one_per_source`
borrow their candidate-ID strings. The current `std::make_tuple` expressions
copy the candidate ID into an owning tuple even when weight or residual settles
the comparison. The isolated source instead uses
`std::tuple<double,double,const std::string&>`: both double values remain owned,
the referenced strings live in the unchanged candidate vector, and the same
`std::tuple::operator<` performs the comparison. Group-key construction,
`std::map` type and order, final sorting, residuals, fits, hashes, and all
scientific policy remain unchanged. The research source is
`research/tracking_one_per_source_rank.cpp`, SHA-256
`eeefee63d956a1aeaeb88ee0b2f2560876107a9f5f79e3b5aa28616036d7b96c`.

The rationale is measured rather than inferred. The prior cycle profile assigns
6.5% self and approximately 18.9% inclusive work to `one_per_source`. A single
instrumented full 11,747-candidate run of the current production source emitted
the exact 64-track SHA-256
`6819cb39151bb2cbe894e5d427244aa95d1eae73e17469e5033659d2b0a30084`
and counted 9,923 deduplication calls over 1,054,816 admitted indexes. The old
rank expressions copied 121,588,281 candidate-ID bytes; 657,695 indexes found
an existing group, while only 185,722 comparisons reached an equal numeric rank
where candidate ID could decide the result. The same run also measured group
key copies, but this prototype deliberately leaves that separate change out.

The focused owning-versus-borrowed rank test checks 147,456 combinations of
weights, residuals, and IDs, including equal numerical keys, string prefixes,
embedded NUL, signed zero, and infinities. Production rejects non-finite
candidate inputs, but exercising infinity confirms that the tuple storage
change itself does not alter ordering; NaN remains outside the accepted input
contract. Host and ASAN/UBSAN focused tests and the normal tracking component
test pass. The test source is
`tests/native_adaptive/tracking/test_one_per_source_rank_research.cpp`, SHA-256
`487e177ad4340524a6d4a27e986a4e6e8f6e0e5d25e39480073c3a537d0e65f9`.

All 60 causal support-end prefixes serialize bit for bit against the production
binary. The aggregate output SHA-256 is
`e9642606acf84a8b4e4817ec082a0381ac51857afb8950cca8ec68cca0014108`;
the receipt is `one-per-source-rank-prefix-parity.json`. A same-compiler
control/candidate/control bracket over twelve full-fixture host executions also
kept every output exact. Mean wall time was 0.5887 versus 0.5716 seconds and
mean child CPU time was 0.5868 versus 0.5688 seconds, reductions of 2.89% and
3.06%. Individual wall times ranged from about 0.50 to 0.73 seconds on the
shared host, so this is a small diagnostic signal rather than a qualified speed
claim. Full measurements are in `one-per-source-rank-host-timing.json`.

This is the only next tracking experiment justified by the present evidence.
It is a two-expression, allocation-reducing change with exact host coverage,
but its likely benefit is bounded well below the five-second gap. If root elects
to continue, the validation plan is one compiler-matched ARM control/candidate/
candidate/control full-fixture bracket, with exact serialized output and RSS,
followed by production component and application rebuilds only if ARM confirms
a repeatable gain. Do not combine source-key precomputation, map replacement,
threshold changes, or another cache experiment into that measurement.
