# Native weighted-Hough DS9 qualification

The maintained public `ScannerTrackingInputStore` loaded
`scan-fw-3cfdaa6d75762cad` read-only from `/srv/bulk/leo`.  The export contains
24,681 retained raw fractional candidate rows and 11,747 server-projected
candidates.  With the adaptive TLE profile (six observations, three-second
span), the Python oracle and portable C++ implementation both produce 64
tracks containing 3,372 source observations.

Every native track has the exact server lane, source-group membership, support
start/end/reference times, and alias indices.  Fitted values agree within
`3.2e-9 Hz/s` in slope and `9.4e-7 Hz` in intercept.  Candidate IDs and bound
tracklet IDs agree for 3,366 observations and 58 tracks.  The remaining six
source groups each contain two duplicated server candidates whose measured CFO
differs by no more than `1.2e-10 Hz`; NumPy LAPACK and the dependency-free
closed-form fit resolve those residual ties to opposite candidate ranks.  The
physical membership, time, CFO, and alias are unchanged.  `comparison.json`
records the exact limits and fixture hashes.

`projection-inputs.jsonl` preserves the input/analysis digests, numeric stream
generation, counter/UTC anchor, probe window counter, sample rate, receiver,
channel, edge, actual RF, timing bracket, qualification state, and raw
fractional candidate fields.  Each row includes the maintained server
projection or `null` when the candidate did not project.

The tracking API does not accept recording authority, source sample bounds,
uncertainty, or factorial support moments.  Those values are required for the
server episode graph and support digest.  Full graph IDs and randomized
partition masks therefore remain at the graph-authority boundary; this report
does not claim parity for them.

## Bounded intercept-bin cache

The full 11,971-observation native scan exposed a measured tracking cost.  A
lane-local cache now computes the existing scalar `fmod`/`floor` intercept-bin
index once for each eligible point and slope, then reuses that integer across
peel iterations.  Histogram weights are still added in the original ascending
chosen-point order.  The cache does not subtract peeled weights or replace the
floating-point bin calculation.

The matrix uses 16-bit indexes only when `intercept_bins <= 65,536`, is capped
at 32 MiB, checks multiplication overflow, and falls back to the original
calculation on an oversized matrix or allocation failure.  It is not allocated
when eligible support is insufficient, and initially ineligible points are not
precomputed.  The largest complete-scan lane used 19,135,714 cache bytes.

Host ABBA runs fell from 1.65/1.66 seconds to 0.75/0.75 seconds and remained
byte-identical.  The first guarded-design prototype ran the saved input on the
physical ARM CPU in 39.502 seconds versus the separate 78.070-second
uninstrumented baseline, with byte-identical output.  The final source adds
only the insufficient-support and initially-ineligible work guards.  Its host
and sanitizer tests pass, its host complete-scan output is byte-identical, and
its ARM unit test passes.  The final binary did not receive another physical
full-scan timing run, so 39.502 seconds is prototype evidence rather than a
final-binary timing claim.  No five-second tracking claim is made.

`bin-cache-optimization.json` binds the inputs, binaries, source hashes,
timings, memory bounds, and test results.  The original gprof limitation still
applies: most whole-process time was outside the instrumented executable, so
that profile alone does not directly attribute the missing samples to `fmod`.

## Persistent exact-prefix cache research

An additive, move-only `Reconstructor` keeps the exact 16-bit intercept-bin
indexes for an ordered, append-only candidate prefix.  The stateless
`reconstruct` entry point remains unchanged.  Candidate fields, caller order,
lane order, configuration, reference time, RF geometry, and derived bin
geometry must all match before reuse.  Insertions, reorder, expiry, changed
configuration or geometry, and capacity exhaustion discard the cache and use
the cold oracle path.  Histogram values are rebuilt in the original ascending
point order on every call; the cache neither stores histograms nor subtracts
expired weights.

The default 96 MiB limit accounts for retained cache payload and observed
vector capacities, including the candidate copies.  It is not a bound on
allocator metadata or process RSS.  Allocation-size checks run before bin work,
and the tiny-budget test confirms that an input which cannot fit performs no
bin-index computation.

On the 11,747 saved projected observations, 60 five-second center-time growing
prefixes were bit-exact and reduced cumulative host reconstruction time from
26.302 seconds to 18.405 seconds.  Peak retained cache accounting was
88,570,966 bytes and whole-process peak RSS was 130,268 KiB.  This is
center-time grouping in existing input order, so it is not causal publication
evidence.  It is also only a growing-window accelerator: when a 600-second
rolling window expires observations or changes its reference, exact
invalidation pays the cold reconstruction cost.  The 30.0 percent host
reduction does not close the measured ARM gap and makes no five-second or
continuous steady-state claim.

The host and sanitizer component tests pass and the ARM component cross-build
is frozen under `builds/arm-prefix-cache-v1`.  No production caller enables the
stateful API.
`prefix-cache-qualification.json` binds source, input, artifact hashes, exact
test coverage, measurements, and limitations.

The separate causal support-end benchmark sorts candidates by support end and
candidate ID, matching the Coordinator's publication order.  All 60 host
prefixes were bit-exact, with 25.758 seconds cumulative cold time and 18.276
seconds stateful time.  Its bounded physical ARM tail run was also bit-exact
for both prefixes and produced 64 final tracks.  The final cold reconstruction
took 39.333 seconds and the warm append took 24.045 seconds; seeding the cache
took 62.850 seconds.  Accounted retained cache was 88,221,442 bytes and the
whole test reached 111,164 KiB RSS.  These measurements confirm exact reuse
and a warm speedup, while also showing that it remains far above the five-second
target.  `prefix-cache-causal-qualification.json` binds the causal host and ARM
results.  The cache remains experimental and disabled.

## Exact refined-fit cache

The production tracker now keeps a bounded exact-fit cache for one lane
reconstruction.  Its key contains the ordered point indexes and the bitwise
initial slope, intercept, and spacing.  A hash selects the probe sequence, but
every hit compares the full key.  This preserves fit arithmetic, hypothesis
order, and tie behavior; membership alone is never enough for reuse.  The
table has 4,096 slots and an 8 MiB retained-payload cap.  A full table,
capacity limit, table-allocation failure, or optional entry-copy allocation
failure runs the original fit and leaves its result unchanged.  The cache is
lane-local and has no shared statistics or mutable global state.

Component tests cover deliberate hash collisions, table and byte limits,
ordered-membership changes, signed zero, adjacent numeric values, and injected
optional allocation failures.  Host and sanitizer tests pass, and an
independent frozen-baseline comparison matched all 60 causal support-end
prefixes byte for byte.  On the physical ARM CPU, the production component
processed the complete 11,747-observation fixture in 29.759 seconds with the
same `6819cb39...` serialized output; the bracketed fast-bin-only control took
33.605 seconds.  The production tracking and internal cache tests also passed
on ARM.  This is an 11.4 percent incremental cold-run improvement, but it
remains far above five seconds and does not establish continuous real-time
operation.  `exact-fit-cache-qualification.json` binds the research evidence,
production sources, builds, tests, causal prefixes, and physical timing.
