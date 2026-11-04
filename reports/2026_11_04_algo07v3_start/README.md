# ALGO07v3 implementation: standalone track and orbit components

Update: [causal preparation and exact parsing reuse](../2026_11_04_algo07v3_preparation/README.md)
are now implemented. The full track comparison finished: 158/158 available DS26
fast inputs match exactly, with one unavailable member retained in the 159-member
denominator. The text below records the original implementation checkpoint;
the full localization engine is still unfinished.

**Complete-pipeline speedup: unavailable. ALGO07v3 is not yet a complete
localizer or a production release.** This first implementation extracts native
track preparation and regional orbit propagation, and introduces exact reuse of
phase geometry. The causal catalogue adapter, complete initial fit, ordered
recovery/reassociation, final publication and full DS26 equivalence remain work
to do. The [standalone plan](../../docs/operations/algo07v3-plan.md) remains the
acceptance contract, including the 10× target.

## Implemented components

`leo.analysis.localization_v3.tracks` takes the native tracking contract and an
explicit polynomial configuration. It selects the original gated maximum-margin
peak, constructs RF-separated graph tracks, retains aliases/IDs/order, validates
residual gates and identifies active curvature. It imports existing pure
numerical components, not any older ALGO worker, storage or CLI. The shared graph
and input components were verified byte-identical to their pinned production
counterparts before extraction.

`leo.analysis.localization_v3.orbits` performs the original time rounding, SGP4
propagation, Earth rotation and regional elevation screening. Screening coordinates
are explicit inputs; there is no evaluation-site constant. It accepts a supplied
catalogue and does not read an archive or select post-observation elements.
The application-level causal catalogue preparation is not implemented yet, so
this component alone is not a causal-association pipeline.

`leo.analysis.localization_v3.geometry.ScanGeometry` privately freezes its bank
and reuses phase-geometry calculations for exactly identical requests. Keys
include times, phases, their dtype/shape/bytes, and derivative-step representation.
Cold queries preserve the original numerical implementation. Returned arrays are
backed by immutable bytes, so callers cannot re-enable writes and poison later
hits. An LRU byte budget evicts entries; oversize results bypass caching.

Thirty component/tool tests pass, covering native timing/input rejection, peak
ties, RF separation, graph ownership, curvature, propagation sampling/screening,
bitwise geometry equality, input mutation, immutable returns, eviction and
domain failures. The candidate test-process guard rejects legacy worker imports,
historical installation reads and subprocess launches. This guard is a research
test, not a claim that the not-yet-built complete deployment has passed isolation.

## DS26 track-preparation comparison

The declared cohort is all **159 DS26 fast members**, including **158 available
native inputs** and the retained unavailable member. Inputs were copied through
the native public port and checked against the existing frozen cohort hashes.
The complete input plan is at
`/srv/bulk/leo/research/algo07v3-20261104/tracks001/plan.json`.

The [runner](../../tools/check_algo07v3_track_preparation.py) executes each side
in its own Python environment, reference first and candidate second, with a
1,200-second per-side external bound. The reference uses the original installed
functions. The candidate uses only the standalone track module and shared pure
numerical libraries. Every polynomial, coefficient, piece, observation, alias,
metadata value and curvature selection is serialized for exact comparison.
Failed/unavailable members remain in the denominator.

The reference has completed all 158 available scans, with zero failures and its
source pins intact. The candidate is running; its first 34 results were compared
as complete serialized bytes and matched exactly. This cohort comparison remains
in progress. Its receipts are authoritative; no full track-cohort pass or
complete-localization pass is claimed here. The original track arithmetic has
not been optimized in this extraction. The [frozen plan](track-cohort-plan.json)
and [progress snapshot](track-progress.json) retain the complete denominator.

## Exact orbit-bank reconstruction

The extracted kernel reproduces the saved DS26-0084 bank bit-for-bit:

| Array | Shape | Maximum absolute difference |
|---|---|---:|
| Time grid | 335 | 0 |
| ECEF positions | 1,559 × 335 × 3 | 0 |
| ECEF velocities | 1,559 × 335 × 3 | 0 |
| Satellite identifiers | 1,559 | 0 |
| Phase scale | 1,559 | 0 |

This test uses the original selected TLE export as a **component oracle input**.
It does not qualify fresh catalogue selection, nor allow the eventual production
engine to depend on preselected satellites. Source files were checked against
the public evidence descriptor. See [reproduction script](check_orbit_bank.py)
and [result](orbit-bank.json).

## Exact phase-geometry reuse experiment

The real DS26-0084 bank contains 1,559 satellites and 2,679 distinct observation
times. A deliberately repeated-query experiment compares three identical
phase-geometry preparations, in reference/candidate/candidate/reference order.
All twelve returned geometry results match exactly, including array bytes,
shapes and dtypes. Setup time is included; verification hashing is outside the
counted time. The host remains shared, and this is not a representative cache-hit
rate measurement.

| Trial | Three-query time, including setup | Hits / misses |
|---|---:|---:|
| Original, first | 7.836 s | 0 / 3 |
| Cached, first | 2.017 s | 2 / 1 |
| Cached, second | 2.066 s | 2 / 1 |
| Original, second | 5.637 s | 0 / 3 |

The cold cached calculation is approximately 2.0 seconds; the gain comes from
avoiding repeated identical work. It is **not** a tenfold whole-pipeline gain.
The next integration must measure actual repeat frequency and complete-path
latency rather than assuming this deliberately favorable workload occurs.

This full-bank cache entry accounts for 534,621,256 bytes, about 510 MiB, including
key bytes. The experiment explicitly allows 1 GiB of cached arrays/keys. The
component's conservative 256 MiB default would bypass this oversized full-bank
entry; smaller satellite subsets can fit. These counters exclude bank storage,
Python overhead and transient arrays, so they are not peak process memory.
Memory cost and cache-hit rates must be evaluated at integration.

See [benchmark script](benchmark_geometry.py) and [raw result](geometry-result.json).
No legacy scientific policy, production service, TLE eligibility rule, GPS use or
golden fixture changed. The next implementation work is causal preparation and
the standalone initial fit, followed by all existing recovery policies.
