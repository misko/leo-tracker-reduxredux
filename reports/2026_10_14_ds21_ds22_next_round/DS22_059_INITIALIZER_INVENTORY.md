# DS22-059: distinct basin and optimizer failures

A reference-free inventory of the sealed original initializer and endpoints completed with zero objective evaluations and zero fits. It identifies two separate facts: A/B and both C halves accepted poor configured-reference solutions, while C-all had no acceptable endpoint. The saved evidence does not demonstrate that the candidate bank lacks the correct satellites.

All views share the same 50-satellite candidate bank. There are 3499 training windows, split into 1990 low-band and 1509 high-band windows, with both receivers represented. The six original 25 km search disks have centers, in the original prior's local kilometre frame:

| Start | Center x | Center y |
| --- | ---: | ---: |
| 0 | 106.250000 | 156.250000 |
| 1 | 131.250000 | 156.250000 |
| 2 | 50.000000 | 150.000000 |
| 3 | 202.094104 | 147.166481 |
| 4 | 79.300496 | 49.710646 |
| 5 | 12.353311 | 13.708321 |

All 18 A stage fits, all 18 B view fits, and all 12 C half-view fits are stationary. A selects start 1; B all/low/high selects 2/1/0; C low/high selects 1/1. Their selected positions lie 4.91–14.55 km from the nearest original disk center, comfortably inside the 25 km disks. Widening the disk cannot be justified from an active boundary at these selected endpoints. This does not rule out an unsearched distant basin.

C-all is a different failure: none of its six endpoints passed stationarity, with KKT 82.789–2432.304, while disk radii were only 4.00–13.16 km. Its unavailable result is retained. A generic endpoint continuation would require a new training-only trigger and budget; this inventory performs no continuation and does not relax acceptance.

The recorded receiver-alias derivations are comparatively weak in several starts: modal fractions range roughly 0.36–0.68, and receiver 1 initializes in either the +1 or +2 alias representative depending on the proposal. That supports checking association/ambiguity evidence before another broad calibration modification; it does not establish an alias error. The existing physical offsets and receiver lifts are unchanged.

The broad configured-reference failure is already visible across the independently optimized shared-discovery halves. Therefore combining bands alone cannot explain 059. Candidate support, discovery basins and objective ranking remain plausible; this metadata audit does not distinguish them. No reference coordinate, held observation, posterior or new model score was read to compute the inventory.

Source `576617765`; two inventory/component tests passed, Ruff clean. Exact original source and terminal bindings, all six starts, receiver-lift derivations, per-endpoint KKT/radius values and candidate identities are recorded in `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-059-metadata-inventory-v1`. The configured-reference context is documented separately in `DS22_TWENTY_ONE_CASE_RESULTS.md`; station continuity is still unconfirmed.
