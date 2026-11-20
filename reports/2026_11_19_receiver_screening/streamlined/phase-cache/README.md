# Exact native normal-solve reuse

A one-entry exact memo skipped 757 of 3,388 native solves across three capped compact-v5 recording pairs. All six position and RF results matched the unrestricted compact control exactly. The memo saved about one CPU second at the native solve boundary per recording. Whole-worker CPU fell by 1.15 and 1.44 s in two pairs and rose by 0.05 s in the third.

The DS29-0316 profile measured 1,193 native calls taking 16.96 CPU seconds, including 266 adjacent calls with matching argument fingerprints that took 3.01 seconds. It measured 6,344 compact projector calls taking 10.43 seconds with no adjacent exact grid/observer identity, and marginal phase geometry took 2.23 seconds with 0.36 seconds of adjacent repeats. The earlier endpoint-only experiment saved 0.09–0.74 CPU seconds per recording. The confirmatory cache spans the native backend call boundary and leaves the existing orbital, phase-geometry and symbolic factor caches in place. [Capped profile](profile.json) · [Earlier endpoint study](../../../2026_11_19_receiver_convergence/likelihood/README.md)

| Recording | Actual native calls, ordinary → memo | Solve CPU, s | Whole CPU, s | Whole wall, s | Cgroup peak, MiB |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0146 | 1,196 → 946 | 11.25 → 10.18 | 79.03 → 77.88 | 85.24 → 79.84 | 445.3 → 439.0 |
| DS26-0026 | 1,185 → 914 | 11.47 → 10.30 | 74.43 → 74.48 | 75.60 → 77.17 | 428.0 → 424.9 |
| DS29-0174 | 1,007 → 771 | 10.44 → 9.56 | 78.69 → 77.25 | 82.99 → 79.12 | 501.8 → 508.4 |

Keys contain exact backend and process identity, argument order, array representation and values. An eligible call compares bytes directly against privately owned copies. Reused result arrays are private to the caller. A miss preserves the ordinary validation and numerical path. The largest retained array payload observed was 3.99 MiB. The kernel peak includes file pages. DS29-0174 retained its position under the 512 MiB cap with only 3.6 MiB of measured headroom.

Each candidate and control published 3/3 roof fixes in both calibration arms. The zero-c and fitted-c median errors were 0.886 and 0.918 km, and the corresponding P95 values were 1.549 and 1.488 km. Median conditional RF RMS was 72.218 and 72.084 Hz. The replay starts at complete stored GLRT, with matched observations, hypotheses and five phase refreshes. The three measured host pairs support the scoped repeated-solve reduction and a small, mixed end-to-end gain.

The RSS check sampled Linux per-process high-water during one repeated leg per case and took an in-flight reading during each complementary primary leg. The complementary values are lower bounds, and cgroup peaks in the table come from both complete primary calls. All three RSS repeats reproduced their respective paired coordinates and RF exactly.

| Recording | Ordinary process high-water, MiB | Memo process high-water, MiB |
| --- | ---: | ---: |
| DS26-0146 | 480.7 in repeat | ≥476.0 in primary |
| DS26-0026 | ≥444.7 in primary | 474.0 in repeat |
| DS29-0174 | 488.5 in repeat | ≥471.5 in primary |

The exact measured source is preserved in [the source snapshot](variant-at-measurement.py.gz). The live source combines the same two array checks into one condition for lint.

[Protocol](PROTOCOL.md) · [Sealed predictions](confirmation/paired.jsonl.gz) · [Detailed scores](confirmation/scores.json) · [Native backend receipts](confirmation/native-backend-receipts.json)
