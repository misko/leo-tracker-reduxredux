# Opt-in exact location-score cache

The online coordinator now has an additive, disabled-by-default exact per-track
score cache. A nonzero `maximum_exact_score_cache_bytes` enables it. The cache
stores one central track-authority table and per-site score/statistics payloads;
it never copies the roughly 320 KiB authority once per site.

Reuse requires an exact stream generation, orbit generation, complete score
configuration, all six ECEF/up binary64 site components, and complete track
authority. Publication generation is intentionally absent, so unchanged tracks
can survive a newer immutable publication. Site mismatch is one site miss.
Stream, orbit, or score-policy replacement invalidates the cache scope.

Migration occurs only when `begin_search` binds the actual immutable search
snapshot, so a newer publication cannot mutate a pinned active search. The old
and proposed retained payloads are preflighted together before copies. Site
capacity is capped by `maximum_search_points`. The reported payload includes
container/string capacities and excludes allocator metadata. The qualified
libstdc++ copy behavior is assumed; short strings are conservatively charged 15
bytes. Allocation pressure falls back to the unchanged cold path. Dispatcher
errors remain fatal, and a failed point does not commit a cache entry.

The full host trace uses causal prefixes 58, 59, and 60, the complete 11,129 TLE
catalogue, two ordered score lanes, and the original Sacramento 400-point C7
policy. Warm searches take 8.189 and 8.754 seconds versus 51.795 and 54.634
seconds cold. Across both transitions the cache records 41,540 exact track hits
and 35,260 misses. A multi-publication cache explains why this exceeds the sum
of adjacent-pair eligibility: sites retained from prefix 58 can still contribute
after prefix 60 when their migrated track authority remains exact.

The link-wrapped diagnostic compares all 800 warm/cold submitted coordinate and
objective records, all 800 aggregate point scores, and 51,200 per-track winner
records field-for-field with binary64 bit equality. Final incumbent counters and
scores also match. The full host run peaked at 583,892 KiB because the diagnostic
holds the cache coordinator and one independent cold reference coordinator; it
is not an embedded-memory qualification.

`--cache-points 1` uses a clearly reduced one-root policy solely for bounded ARM
integration. The original Sacramento policy has 16 initial roots, so a two-point
budget correctly fails validation. The first ARM attempt retained the cache
coordinator while constructing a cold-reference coordinator; the kernel killed
that test harness for OOM at 436,292 KiB RSS. The v9 harness instead retains only
the small completed traces while running the cache and cold coordinators in
separate scopes. It passed on ARM in 191.133 seconds at 301,068 KiB RSS, with two
aggregate records and 128 per-track winners bit exact. Warm searches took 0.820
and 1.081 seconds versus 8.231 and 8.307 seconds cold. The production cache code
and every ARM archive member are byte-identical between those attempts.

The ARM result is a reduced one-site integration check. Full regional 400-point
ARM behavior, five-second continuous publication, concurrent capture, and live
cache enablement remain unqualified. No run used RF. Physical evidence, including
the preserved OOM, is bound by [physical-receipt.json](physical-receipt.json).

The durable package includes the exact v9 source tree and SHA-256 manifest in
`source-v9/`, fresh host and ASAN/UBSAN logs in `logs/`, fixture hashes in
`INPUTS.sha256`, and the original v7 full-trace executable in
`artifacts/host-v7/`. Reproduction commands are recorded in `COMMANDS.md`.
