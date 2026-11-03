# Exact per-track score reuse research

This isolated experiment asks whether a location result for a complete track can
be reused across consecutive immutable publications. It does not change the
location ABI, scorer, online coordinator, search policy, fixtures, or goldens.

The test reconstructs causal five-second prefixes 58 and 59 from the deployed
tracking candidate and graph-authority fixtures. Prefix 58 contains 11,389
candidates and prefix 59 contains 11,566. Both reconstruct to 64 tracks. The
test passes each result through the production `pipeline::make_location_tracks`
path, builds the full 11,129-satellite orbit, and scores a fixed site with the
production tau and score policy.

A cache hit requires exact stream and orbit generations, bit-identical site and
floating score configuration, and a collision-checked complete location-track
input. The latter includes tracklet, support and partition identities,
observation identities, bit-identical times and measured CFOs, training mask,
track key, observation count, and weight. Publication generation is deliberately
not a key because an identical immutable track can survive publication. Stream
or orbit replacement clears the cache. The unit test also rejects changed site
bits, score configuration, support authority, mask, measured CFO, weight, and
stream or orbit generation.

Prefix 58 seeds 64 complete per-track winners and per-track integer statistics.
Prefix 59 reuses 55 and recomputes 9. The assembled 64 winners, final point
score, matched counts, and evaluated/rejected satellite-track counts are
bit-identical to a cold bulk prefix-59 score. The final logical retained payload
is 356,813 bytes. This is logical object and content size; it excludes allocator
metadata and spare capacities.

The final host sample measured 0.253213256 seconds for the cold prefix-59 score
and 0.034757043 seconds for the reuse stage. Those are one-run diagnostic
timings, not an ABBA performance qualification. ASAN/UBSAN reproduced the exact
science and hit inventory. Physical PLUTO+ execution also passed: cold scoring
took 15.020206535 seconds and reused scoring took 1.519702581 seconds, with
55 hits and 9 misses and bit-exact winners, score and statistics within ARM.
ARM logical retained payload was 351,557 bytes (object sizes differ by target).
The whole harness took 112.031 seconds and peaked at 126,448 KiB RSS, including
track reconstruction, orbit construction and cache seeding. See the
[physical receipt](physical-arm/receipt.json) and [raw log](physical-arm/ds9.log).
These remain single timing samples. The experiment only demonstrates
reuse at an exactly repeated site. A nearby but unequal site changes the horizon
and Doppler calculations and is always a miss.

Build and run with:

```sh
TMPDIR=/var/tmp/leo-score-reuse-compiler \
  tests/native_adaptive/location/research/build_exact_score_reuse.sh host \
  /var/tmp/leo-score-reuse-host-final2
TMPDIR=/var/tmp/leo-score-reuse-compiler \
  tests/native_adaptive/location/research/build_exact_score_reuse.sh sanitize \
  /var/tmp/leo-score-reuse-sanitize-final2
TMPDIR=/var/tmp/leo-score-reuse-compiler \
  tests/native_adaptive/location/research/build_exact_score_reuse.sh arm \
  /var/tmp/leo-score-reuse-arm-final2
```

The smallest next gate is a bounded search replay that records how many exact
site coordinates recur between consecutive snapshots. Per-track reuse cannot
improve new refinement coordinates, regardless of spatial proximity.
