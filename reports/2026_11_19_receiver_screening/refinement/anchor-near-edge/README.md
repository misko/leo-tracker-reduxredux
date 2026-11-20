# Blind near-edge qualification of the native anchor receiver

The frozen anchor receiver published three positions on twenty offers that omitted the site. The same three cases published in both calibration arms. Each false fix was more than 7.4 km from the reference. The other independent near-edge results and all forty raw outcomes are retained. [Prediction seal](prediction-lock.json) · [Scores](scores.json) · [Standard chart](figures.json)

| Offer | Published / attempts, each arm | Median published error, zero / fitted (km) | Worst published error, zero / fitted (km) |
|---|---:|---:|---:|
| Original tile | 7 / 10 | 3.035 / 2.326 | 5.288 / 5.368 |
| Site near inside edge | 4 / 10 | 2.607 / 2.181 | 5.792 / 5.218 |
| Site near outside edge | 1 / 10 | 7.446 / 7.401 | 7.446 / 7.401 |
| Site 6 km outside | 2 / 10 | 11.889 / 11.891 | 13.686 / 13.594 |

DS26-0048 published with the site 1.289 km and 6 km outside the offer. DS29-0316 published with the site 6 km outside. All forty queries produced forced estimates and completed the same capped streaming Graph plus anchor path used in the full-panel replay. The near-edge controls use separately generated offers and retain the same causal native archives and physical installations across conditions. [Full panel](../anchor-full/README.md) · [Per-case predictions](positions.jsonl.gz)

The independent evaluator's original-tile labels have no requested edge margin. The post-seal scorer groups those by condition and retains their null margin. The inference-source hash and scorer-source hash are recorded separately. The estimator, prediction bytes and calibration arms remained frozen. Site labels were opened only after all forty anchor predictions were sealed. [Source lock](source-lock.json) · [Figure seal](figure-lock.json)
