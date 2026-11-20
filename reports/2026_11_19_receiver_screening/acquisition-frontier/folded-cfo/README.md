# Folded CFO screening on the differential timing hint

The phase mask removed **2.60% of coarse complex tap evaluations** across 16 new saved-IQ visits. The measured phase, unpruned timing hint and half-period phase sham all recovered the same five of 12 missed archive targets at matching absolute CFO. The masked detector lost four other gated candidates from the unpruned result. Median scout-plus-detector CPU stayed near 27.6 ms for a 20 ms dual-receiver window. These results support the timing hint and show little detector benefit from this phase mask. Position was unmeasured. [Stage figure](stage.pdf) · [Per-visit measurements](stage.csv)

| Native target gate | Misses recovered | Retained controls kept | Other gated candidates lost vs unpruned |
| --- | ---: | ---: | ---: |
| Stock wide | 0/12 | 4/4 | — |
| Differential timing, all 21 bins | 5/12 | 3/4 | 0 |
| Timing plus measured folded phase | 5/12 | 3/4 | 4 |
| Timing plus half-period phase sham | 5/12 | 3/4 | 3 |

All five recovered misses also became the largest-fractional-margin candidate in each hinted arm. At the retained target hits, phase preserved exact epoch, CFO and margin and changed the original candidate index once. DS29-0082 visit 157 lost its matched target in every hinted arm, including unpruned. Phase and sham added no unmatched gated candidates relative to unpruned. The five new real positives comprise four strong and one middle archived margin case. [Full gate, rank and factor outcomes](qualification.json)

## Native work

A 44-sample phase measurement is modulo 227,272.7 Hz. On a newly inserted fourth center the overlay only visits the original physical CFO bins within ±80 kHz of the phase modulo that period. Every compatible alias stays eligible. Existing timing regions and their neighboring peak scores keep all bins. The same native fine/fractional search, control reference and gate then evaluate the retained hypotheses. The overlay with screening disabled reproduced every public field of the pinned unpruned hinted detector, and all arms preserved the unhinted physical receiver. [Frozen protocol](PROTOCOL.md) · [ABI and build receipt](build-lock.json)

| Both receivers, 16 visits | Unpruned | Measured phase | Phase sham |
| --- | ---: | ---: | ---: |
| Physical regional CFO cells | 8,043 | 7,833 | 7,836 |
| Nonzero physical anchor-bin updates | 1,406,013 | 1,369,408 | 1,369,920 |
| Complex tap evaluations at physical CFO bins | 61,864,572 | 60,253,952 | 60,276,480 |
| Median native coarse CPU | 1.786 ms | 1.817 ms | 1.810 ms |
| Median native CPU | 15.960 ms | 15.702 ms | 15.925 ms |
| P90 native CPU | 18.216 ms | 17.327 ms | 17.331 ms |
| Median CPU, scout plus native | 27.527 ms | 27.577 ms | 27.758 ms |
| P90 CPU, scout plus native | 30.932 ms | 29.676 ms | 29.495 ms |

The C overlay counts actual nonzero physical anchor-bin updates and their tap lengths. Padding lanes are excluded. Four warm runs per arm on CPU 4 at nice 10 compared the identical same-IQ scout and gate. The reduced cell count had no measurable median end-to-end CPU benefit, and the sham showed a similar P90 change. Host timings exclude the authenticated archive read and any tracking or positioning. [Detailed CPU and wall timing](qualification.json)

## Controls and provenance

Four chronologically later distinct visits per case were scheduled after the prior differential-pilot confirmation. All 16 waveform and stock-projection identities verified. Both signs of the ±790 kHz edge controls passed as absolute-CFO matches. Strong and weak planted lanes likewise passed. The phase arm kept all four one-live-frame plant positives, and the phase sham lost one. Gaussian noise, zero and lower-edge CW produced no gated positives. Upper-edge CW still passed, with the same six gated candidates in unpruned and both phase arms. [Locked raw roster](input-lock.json.gz) · [Full synthetic controls](controls.csv)

The isolated build and the replay source are recorded in the seals. Run `folded_cfo_build`, then `folded_cfo_eval freeze`, `folded_cfo_eval synthetic` and `folded_cfo_eval replay --case CASE` using the same new ext4 `--work` directory, before `folded_cfo_results`. These are modules under `tools.pipeline_eval.qualification`. Use the original hinted-wide prerequisites and keep its source unchanged. The measurement used saved IQ only. [Prediction and evidence seal](prediction-lock.json)
