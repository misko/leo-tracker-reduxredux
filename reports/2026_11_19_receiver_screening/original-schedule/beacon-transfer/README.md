# Carrier-level transfer between physical StarLoc sites

No target had two identifiable donor carriers. The earliest-only bank matched one beacon at site 07. Its carried, shuffled and free-offset held residuals were numerically identical. Allowing later donors added two more sites with a single match each. All transfer branches withheld before fitting a position. On the same samples, Doppler shape alone gave a **4.71 km** median forced error on containing offers, compared with **7.95 km** for the offered centres. [Support figure](beacon-transfer-support.png) · [Position charts](charts/README.md) · [Scores](scores.csv)

## Donor graph and observability

The eleven measured captures span eight physical sites. For each target, the predictor excludes all captures from its site. Earlier donors must also end before the first target capture starts. At each other surveyed station we subtract its causal model Doppler at the measured native epochs and learn a wrapped carrier level from alternating six-second blocks. This level combines the transmitter frequency, receiver frequency offset and residual orbit/model error. Its initial tone index can differ by multiples of the **43,945.5 Hz** comb, so both training and held comparisons use that circular period. The subsequent target sees anonymous frequency and time samples, its causal catalogue and one offered square. Donor coordinates and target author IDs are absent from that worker. [Frozen protocol](PROTOCOL.md) · [Source and instrument authority](../../retry-and-transfer/bearing-transfer/SOURCE.md)

The 81 released author-labelled arcs contain **79** satellite IDs. The capture–satellite graph has **nine** components, with 11 capture nodes, 79 satellite nodes, rank 81 and **zero closure cycles**. The labelled carrier quality gate retained **77** edges and the anonymous donor recognition retained **74**, with the same component count and zero cycles in both. All 74 accepted anonymous donor IDs agreed with the authors’ site-assisted assignments. Median held carrier RMS within the donor capture was **111.76 Hz** with labels and **111.73 Hz** without them. That checks the local carrier profile. The graph leaves no repeated cross-capture frequency differences against which to test transport independently of receiver offsets. [Donor fit ledger](donor-ledger.json) · [Graph audit](coverage-and-gauges.json)

| Repeated satellite | Earlier → later site | Separation | Apparent combined raw shift | Shift folded onto the comb |
| --- | --- | ---: | ---: | ---: |
| 56038 | 04 → 07 | 3.384 h | −171,990.29 Hz | +3,791.71 Hz |
| 56925 | 05 → 08 | 3.284 h | +115.53 Hz | +115.53 Hz |

The raw shifts above use the train medians after subtracting causal Doppler at the surveyed donor coordinates. They combine electronics, orbit/model error and transmitter changes. A single shared satellite between two captures fixes their gauge difference if its level is assumed persistent. It leaves no independent constraint to distinguish a transmitter shift from an equal and opposite clock change. The author's injected reference supplies relative SDR-chain phase downstream of the LNB. It establishes no shared absolute RF offset across captures. A repeat of **two** satellites within the same connected donor component would supply the first testable between-beacon level contrast. [Hardware reference and on-air calibration source](https://arxiv.org/html/2604.21147v1#S4.SS2)

## Held target support

Using the target author labels in a post-seal coverage audit, two of eight sites had one strictly earlier prior satellite and six had zero. The all-other-site oracle had four singleton sites and four with zero. Every target's identifiable donor-level rank was **zero** after eliminating one free receiver intercept, even granting all labels and later donor data.

Anonymous target selection recovered NORAD 56038 at site 07 under both the earlier author-ID donor and earlier anonymous donor banks. It selected the same beacon on all three offers. Site 08's shape fit selected NORAD 53417 for the arc whose released ID is 56925. Its training runner-up margin was **19.87 Hz**, below the **75 Hz** identity gate. The later donor oracle also recovered the single genuine overlapping beacon at sites 04 and 05. Neither added a second level to the target fit. [Per-target ceilings and held evidence](coverage-and-gauges.json) · [Prediction receipts](positions.jsonl.gz)

| Site 07 offer | Earlier carried RMS | Free per-arc RMS at the same endpoints | Within-component permutation RMS |
| --- | ---: | ---: | ---: |
| Containing | 156.72 Hz | 156.72 Hz | 156.72 Hz |
| Near missing | 149.99 Hz | 149.99 Hz | 149.99 Hz |
| Far missing | 772.34 Hz | 772.34 Hz | 772.34 Hz |

Across all 30 singleton replay branches, changing or removing the donor level moved held RMS by at most **6.2 × 10⁻¹² Hz**. The one free target intercept absorbs the change. The modestly better held singleton RMS on site 07's near-missing offer is therefore evidence from the local arc shape. The fixed single-RF `c` term is also in the intercept gauge, and all fitted-`c` arms are unavailable. [Matched frequency results](scores.csv)

## Geographic evaluation

| Offer | Doppler forced median | Forced range | Centre median | Held Doppler RMS median |
| --- | ---: | ---: | ---: | ---: |
| Containing | 4.71 km | 2.59–14.17 km | 7.95 km | 138.57 Hz |
| Near missing | 19.74 km | 15.34–23.77 km | 32.22 km | 227.72 Hz |
| Far missing | 50.91 km | 44.00–54.59 km | 62.98 km | 411.45 Hz |

The near-missing offers excluded truth by **14.73–22.39 km** at the closest edge. The far offers excluded it by **43.49–54.48 km**. On all eight sites, held Doppler shape loss favored the containing offer over both matching omissions. Its forced containing estimate was closer than the tile centre at seven sites, while site 08's result missed by **14.17 km** compared with **2.82 km** at that centre. The Doppler arm is a diagnostic and reports no publication. The geographic evidence concerns the local shapes, with no contribution from transported levels.

The earlier grouped clock experiment carried carrier levels between visits at one roof. The Bellaterra common-intercept study stayed at one VHF receiver with cooperative identities. This study holds out all observations from each physical StarLoc site and gives the target no orbit labels. It measures repeated-level observability across sites on one instrument. [Roof carrier transfer](../../coarse-and-navigation/clock-transfer/README.md) · [Bellaterra held receiver clocks](../../latency-and-support/external-position/clock-transfer/README.md)

All 24 target workers completed within 40 s. Median CPU time was **1.26 s**, elapsed time including handoff **2.07 s**, and peak RSS **154.12 MiB**. Four tests cover zero-cycle graph alignment, the singleton gauge and harmonic ambiguity, an identifiable two-level positive control, and full-site chronological exclusion. [Blind prediction seal](prediction-lock.json) · [Score and figure seal](score-lock.json)

## Reproduce

```bash
nice -n 10 taskset -c 18,19 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python -B -m tools.pipeline_eval.qualification.beacon_transfer_trial \
  "$STARLOC_MAT_ROOT"
.venv/bin/python -B -m tools.pipeline_eval.qualification.beacon_transfer_results
.venv/bin/python -B -m tools.pipeline_eval benchmark --study \
  reports/2026_11_19_receiver_screening/original-schedule/beacon-transfer --pack
```
