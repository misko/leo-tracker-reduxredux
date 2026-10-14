# DS22 original-model cohort: thirteen completed development cases

DS22-045 adds a thirteenth sealed original A/B/C matrix. Distances remain relative to the configured station coordinate, whose continuity with DS22 is unconfirmed. They are not verified ground-truth errors. Experimental calibration and transport fits are excluded.

| Model | Median CH1–8 distance (km) | Below 1 km | Below 0.5 km | Full no worse than both halves | Full worse than both halves |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 1.820246 | 2/13 | 1/13 | — | — |
| B | 1.681891 | 5/13 | 2/13 | 10/13 | 1/13 |
| C | 2.827544 | 1/13 | 0/13 | 2/13 | 4/13 |

| DS22-045 | CH1–8 (km) | CH1–4 (km) | CH5–8 (km) |
| --- | ---: | ---: | ---: |
| A | 1.494744 | — | — |
| B | 0.154825 | 1.135759 | 2.361447 |
| C | 3.989009 | 1.101019 | 4.505678 |

All twelve units for the new case were sealed before the reference join. The unchanged fitted-`c` models and original budgets were used. B/C half views share full-band discovery and initialization; these are conditional channel comparisons, not independent half-only pipelines. A requires both bands and has no standalone half result.

The thirteen labels are 001, 003, 017, 019, 029, 031, 033, 035, 037, 039, 041, 043 and 045. They are an early development subset of 44 available development members, with one unavailable development member (137) and 24 locked fast-scan members. No locked cases were evaluated. DS22-047 is the next bounded preparation/discovery case.

The first twelve records and their authority are described in `DS22_TWELVE_CASE_RESULTS.md`. The new immutable matrix is `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-runtime-models-v1/DS22-045`; its comparison is `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-runtime-configured-comparison-v1/DS22-045/comparison.json`. The comparison binds protocol digest `sha256:1e9d4ec19441d21489a3bd9a6e33026f9fb7da37f48986b9be91d6ab96dad3a3` and explicitly prohibits an accuracy-target claim.
