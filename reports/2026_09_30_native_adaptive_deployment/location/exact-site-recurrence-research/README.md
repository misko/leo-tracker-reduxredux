# Exact site recurrence across causal DS9 publications

This research-only test runs the production location scheduler and scorer over
three adjacent immutable causal publications. It uses the original Sacramento
C7 policy: latitude 38.5816 degrees, longitude -121.4944 degrees, a 250 km
radius, 100/50/25/12.5 km levels, and a 400-point budget. Each score uses the
complete 11,129-record TLE catalogue, the same 96-knot 10-second orbit snapshot,
and the production two-lane ordered score reduction.

The searches evaluate prefixes 58, 59, and 60, containing 11,389, 11,566, and
11,747 candidates. Each reconstructed publication has 64 location tracks. The
400-point searches take 55.319, 58.053, and 58.730 seconds on the recorded host
run.

Exact site recurrence is measured over all six binary64 ECEF/up components,
rather than rounded east/north text. Prefixes 58 to 59 share 384 of 400 sites;
prefixes 59 to 60 share 385. Their exact full-track authority overlaps are 55
and 52 of 64. A cache retaining only the immediately preceding completed
snapshot could therefore reuse 21,120 of 25,600 per-track evaluations (82.5%)
and 20,020 of 25,600 (78.203125%) at the sites the real adaptive searches
request. This is eligibility evidence, not a cached-search timing result.

The middle snapshot's track authority occupies an estimated 320,104 logical
bytes. A normalized cache that stores that authority once and stores only the
score/statistics payload for each of 400 sites is estimated at 1,779,304
logical bytes. Copying the roughly 320 KiB authority once per site is explicitly
excluded from the proposed design.

[site-inventory.tsv](site-inventory.tsv) contains all 1,200 requests in exact
evaluation order. It records east/north bits, all six site bits, weighted-MSE
bits, orbit generation, and every score configuration field. [host-result.json](host-result.json)
is the direct executable output. The harness models pinned publication policy:
each 400-point search completes against its immutable prefix, then the newest
adjacent publication begins. It does not demonstrate concurrent publication,
cache integration, ARM timing, convergence beyond 400 points, or RF behavior.

Reproduce with:

```sh
TMPDIR=/var/tmp/leo-site-recurrence-compiler-tmp \
  tests/native_adaptive/location/research/build_search_site_recurrence.sh \
  host /var/tmp/leo-site-recurrence-host-v1
```
