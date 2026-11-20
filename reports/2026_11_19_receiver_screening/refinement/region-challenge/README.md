# Anonymous native receiver transfer across five new sites

Each independent site supplies one anonymous five-minute native detector packet to all methods. Four offers reuse that packet at exactly +5 km, +1.5 km, −2 km and −25 km from the true location to the nearest tile face. Positive clearance means inside. The shuffled control preserves occupied lane slots and carries no geographic truth. The receiver sees only the offered geometry, opaque identifiers, native observations, track configuration and causal TLE text. [Protocol](PROTOCOL.md) · [Input lock](input-lock.json) · [Source lock](source-lock.json)

The experiment uses native-format simulated GLRT factors. Full observer geometry supplies range timing and Doppler with authentic causal TLE elements and phase perturbations. Receiver-clock drift, RF terms, alias folds, correlated CFO disturbances, epoch jitter, empirical lane residuals and gaps vary across the capture. Detector scores and candidates come from the factor simulator, so the evidence starts after raw IQ detection. The six archived donor receipts calibrate additive error textures. The source lock binds both the donor trace and its audit. The history seal authenticates the earlier TLE collections. The existing receivers consume one admissible catalogue from that history through their ordinary port.

## Location and publication

The smooth-clock receiver published only at Site 1. It rejected both classes of omitted offers across all five sites. Joint-orbit published one wrong fix when the site was just 2 km outside the tile. Fixed training expanded containing-offer coverage to three sites and published three wrong offers, including one 25 km beyond the tile face. All three receivers withheld the shuffled control. [Per-site publication and error plot](boundary-publication.png) · [Sealed scores](scores.json)

| Receiver | +5 km inside | +1.5 km inside | −2 km outside | −25 km outside | Truthless shuffle |
|---|---:|---:|---:|---:|---:|
| Native smooth clock | 1 / 5 | 1 / 5 | 0 / 5 | 0 / 5 | 0 / 1 |
| Native joint orbit | 1 / 5 | 1 / 5 | 1 / 5 | 0 / 5 | 0 / 1 |
| Native fixed training | 3 / 5 | 2 / 5 | 2 / 5 | 1 / 5 | 0 / 1 |
| Prepared smooth clock | 1 / 5 | 1 / 5 | 0 / 5 | 0 / 5 | 0 / 1 |

Entries count published fixes and are identical in each calibration arm. The two containing conditions reuse the same five sites, so their counts do not add independent locations. Across the published ordinary containing fixes, median position errors in km were 2.152 / 2.582 for smooth clock, 1.876 / 1.970 for joint orbit, and 5.424 / 3.845 for fixed training, in zero / fitted order. Only fixed training published at Sites 4 and 5 on ordinary containing offers. Its fitted errors there were 3.845 km and 11.191 km. On the near-edge containing offer, Site 1 returned 1.144 / 0.841 km for smooth clock, 1.499 / 0.256 km for joint orbit, and 1.283 / 0.183 km for fixed training.

| Wrong publication | Site | Zero error (km) | Fitted error (km) |
|---|---:|---:|---:|
| Joint orbit, 2 km outside | 5 | 5.028 | 4.729 |
| Fixed training, 2 km outside | 5 | 3.857 | 3.669 |
| Fixed training, 2 km outside | 4 | 15.554 | 15.915 |
| Fixed training, 25 km outside | 4 | 42.357 | 44.599 |

## Frequency and matched input checks

The smooth clock reduced conditional RF RMS on all 20 positive or omitted offers versus joint orbit in both arms. On the five ordinary containing offers, the median reduction was 51.36 Hz at zero calibration and 48.61 Hz with fitted calibration. That comparison includes numerical fits whose geographic publication was withheld. On the shared published Site 1 ordinary offer, smooth clock lowered fitted RF RMS from 292.63 Hz to 187.46 Hz while the fitted position error increased from 1.970 km to 2.582 km. The smooth receiver withheld 13 physical offers for weak geometry and five for a boundary endpoint. Its lower frequency error did not increase containing-offer coverage on this cohort.

All 63 native attempts finished in 201.2 s across three CPUs, with zero failures or timeouts. Across the three methods, all anonymous observation digests matched per query. Zero and fitted calibration used identical final smooth-clock ownership digests on all 20 physical offers. Native and prepared smooth-clock paths also agreed on all 21 digests, decisions and exact arm endpoints. The prepared pass is a parity check on the same five sites. Its extra work is included in the enclosing smooth worker wall time. The recorded initial native stages have a median wall time of 7.06 s. The five synthetic sites cover catalogue collection ages from 0.4 to 10 h. The authentic histories contained 31–35 causal collections. Per-lane injected empirical CFO had a median RMS of 98 Hz and a maximum of 278 Hz. The shared smooth disturbance had a median lane RMS of 146 Hz. These results describe the frozen scenario construction and five site draws. [Raw predictions](raw-positions.jsonl.gz) · [Sealed labels and nuisance audit](labels.json) · [Prediction lock](prediction-lock.json)

## Reproduce

Use the frozen deployment bundle referenced by `generalization_challenge.py` or restore its byte-identical files from the prior native Graph qualification. `--seed-hex` from `labels.json` reproduces each synthetic capture, perturbation and offered geometry. Use fresh output paths for another run.

```sh
mkdir -p /tmp/native-region-challenge-report
.venv/bin/python -m tools.pipeline_eval.qualification.generalization_challenge \
  --work /tmp/native-region-challenge --report /tmp/native-region-challenge-report \
  --cpus 0 7 17 --budget-s 350
.venv/bin/python -m tools.pipeline_eval.qualification.generalization_challenge \
  --score --work /tmp/native-region-challenge --report /tmp/native-region-challenge-report
.venv/bin/python -m tools.pipeline_eval.qualification.generalization_challenge_figures \
  --report /tmp/native-region-challenge-report
```
