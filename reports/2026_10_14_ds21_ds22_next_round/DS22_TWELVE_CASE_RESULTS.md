# DS22 original-model cohort: twelve completed development cases

DS22-043 adds a twelfth completely sealed A/B/C matrix to the eleven-case report. All distances use the configured station coordinate; continuity with DS22 is still unconfirmed, so these are not verified ground-truth errors. Experimental native-clock, prior and transport fits are excluded from this cohort.

| Model | Median full-band distance (km) | Full below 1 km | Full below 0.5 km | Full no worse than both halves | Full worse than both halves |
| --- | ---: | ---: | ---: | ---: | ---: |
| A | 1.861560 | 2/12 | 1/12 | — | — |
| B | 1.750567 | 4/12 | 1/12 | 9/12 | 1/12 |
| C | 2.609793 | 1/12 | 0/12 | 2/12 | 4/12 |

The new case has:

| DS22-043 | CH1–8 (km) | CH1–4 (km) | CH5–8 (km) |
| --- | ---: | ---: | ---: |
| A | 1.820246 | — | — |
| B | 1.946818 | 1.423684 | 2.658732 |
| C | 1.830070 | 1.510600 | 0.983972 |

All twelve model units were completed and sealed before the reference join. Fits use the unchanged original fitted-`c` model math and matched budget policy. Half views share full-band discovery and initialization; they are not independent half-only pipelines. A is a sequential two-band model and has no standalone half entry here.

The twelve labels are 001, 003, 017, 019, 029, 031, 033, 035, 037, 039, 041 and 043. They are an early development subset, not the complete DS22 distribution: the frozen inventory contains 44 available development cases, one unavailable development member (137), and 24 locked fast-scan members. DS22-045 is the next bounded pipeline case; no locked data were evaluated.

The existing eleven-case records remain under `local/ds22-configured-comparison-v1` and `local/ds22-runtime-configured-comparison-v1`. DS22-043 output was frozen directly on bulk storage after the root-filesystem capacity incident: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-runtime-models-v1/DS22-043`, with its postseal comparison in `ds22-runtime-configured-comparison-v1/DS22-043`. Its completed initialization remains at the original frozen research path. No historical scientific paths were rewritten.
