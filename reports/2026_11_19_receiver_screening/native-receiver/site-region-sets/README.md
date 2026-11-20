# Four-region Doppler competition at eight StarLoc sites

Anonymous Doppler shape ranked the containing square first on **24 of 24** physical panels and gave the containing panel lower held loss in every matched omission pair. The leave-one-site-out rule accepted **4 of 24** containing panels and erroneously accepted **1 of 24** omissions. It published **zero field coordinates**. The evidence supports forced region ranking within the tested placement distribution. The publication gates show limited transfer. [Predeclared protocol](PROTOCOL.md) · [Per-panel scores](scores.csv) · [Matched pairs](matched-pairs.csv)

## Measured discrimination and withholding

The eight physical sites are near Champaign–Urbana and use one StarLoc instrument. The first capture at each site supplied four to eleven anonymous arcs and 1,885 total native-second frequency samples. Each recording supplied two near pairs and one far pair. The survey matched the nominal placement in every case. The closest wrong edge lay 6.15 to 27.74 km away on near omissions and 44.62 to 56.35 km away on far omissions. Near panels with a containing square included a rival within 4.96 km of the receiver. [Input digests and placements](blind-plan.json) · [Per-panel distances](scores.csv)

| Four-offer panel | Scheduled | Containing tile ranked first | Correct region accepted | Wrong region accepted | Correct `none` | Wrong `none` | Withheld region |
|---|---:|---:|---:|---:|---:|---:|---:|
| Near, containing | 16 | 16 | 2 | 0 | 0 | 2 | 12 |
| Near, omitted | 16 | 0 | 0 | 1 | 8 | 0 | 7 |
| Far, containing | 8 | 8 | 2 | 0 | 0 | 1 | 5 |
| Far, omitted | 8 | 0 | 0 | 0 | 8 | 0 | 0 |

Every held loss difference in the paired comparison favored the containing layout. The omitted panel's best loss exceeded its counterpart by 0.011 to 0.556 on near pairs, with a median of 0.076. The far median difference was 0.948, spanning 0.412 to 1.516. Absolute best losses overlapped across physical sites. Site 04's wrongly accepted offer cleared its training fold because its omitted-panel loss of 0.0721 was below the other sites' lowest wrong-winner loss of 0.0945. The nearest wrong square missed the receiver by 7.49 km. Site 08's three containing losses of 0.184 to 0.189 exceeded its other-site containing bound of 0.120. The site envelopes have a minimum empirical rank of 1/8 and seven geographic locations per fold. The three pairs at each site share one recording. Envelope calibration runs offline across capture dates. Orbit inputs remain causal to each recording. [Decision figure](region-evidence.png) · [Exact plot data](region-figure-data.csv) · [Calibration folds](folds-and-calibration.json)

| Physical site | Containing loss range | Omitted loss range | Correct region accepts of three | Correct `none` of three |
|---|---:|---:|---:|---:|
| 01 | 0.114–0.120 | 0.136–1.484 | 0 | 2 |
| 02 | 0.0733–0.0735 | 0.116–1.163 | 0 | 2 |
| 03 | 0.0711–0.0722 | 0.338–0.628 | 2 | 3 |
| 04 | 0.0607–0.0611 | 0.0721–1.577 | 2 | 1 |
| 05 | 0.0902–0.0902 | 0.154–0.683 | 0 | 1 |
| 06 | 0.0756–0.0756 | 0.153–1.017 | 0 | 2 |
| 07 | 0.0780–0.0780 | 0.0945–0.490 | 0 | 2 |
| 08 | 0.184–0.189 | 0.221–1.143 | 0 | 3 |

The prior frozen receiver ranked the containing square first on 23 of 24. It accepted one correct region and two wrong regions, and withheld all field points. The geometric medoid forced the correct square on six of 24. Spherical corner-distance sums agreed within 4.8 × 10⁻¹² km, so the medoid's numerical ties use only opaque IDs. Shuffling held frequencies saturated all four tile losses and withheld all 48 field decisions. That sham checks chronological shape dependence. The intact near omissions define geographic ambiguity. [Matched position and score distributions](distributions.json) · [Per-panel scores](scores.csv)

## Position and calibration

The candidate's forced estimates on the containing panels had a median error of **4.39 km**, spanning 2.46 to 14.22 km. The centres of those same 24 winning tiles had a median error of 7.81 km. Held RMS on the containing panels was 138.55 Hz at the median. All five accepted field regions failed the independent arc-group position test. Their split spans were 4.50 to 6.80 km against a 0.75 km threshold. Published field errors are undefined. The region result supplies a 25 km square. [Per-panel estimates and independent geometry](scores.csv)

At the simulated site in Portugal, exact-time SGP4 generation with independent carrier offsets and 5 Hz measurement noise supplied eleven arcs. Envelopes from all eight field sites selected the correct region and published a point **46.7 m** from truth. Independent arc groups and the common fit agreed within the frozen threshold. The same rule rejected the matching omission. The frozen comparator gave a **148 m** fix on the containing panel and accepted the wrong region on the omission, where its position gate withheld. This simulation tests the decision path with a causal catalogue that also generates the signal. It supplies no physical result at a new metro area. [Simulation rows](scores.csv) · [Simulation chart inputs](simulation-queries.json)

Every arc uses one RF of 11.325 GHz. The free wrapped per-arc intercept absorbs the full RF-dependent calibration term. The fitted-`c` arm is unavailable. Changing (c) by 100,000 Hz per GHz and reversing offer order on eight matched panels changed held RMS by at most 3.5 × 10⁻¹² Hz across 32 tiles. The forced coordinates moved by 0 m. [Calibration identifiability and perturbation audit](folds-and-calibration.json)

## Execution cost

All 108 corrected workers completed within their 35 s cap. They include 48 physical panels and two simulated panels for each estimator, plus eight coefficient and tile-order controls. The campaign used two pinned x86 CPUs and took 94.1 s including handoff. No corrected run needed a replay. [Execution attempts](execution-attempts.csv) · [Prediction seal](prediction-lock.json)

| Physical estimator | Elapsed P50 and P95 | CPU P50 and P95 | Peak RSS P50 and maximum |
|---|---:|---:|---:|
| Held Doppler shape | 2.02 and 3.00 s | 1.79 and 2.03 s | 176.94 and 187.30 MiB |
| Frozen regional replay | 1.08 and 1.64 s | 0.94 and 1.47 s | 129.26 and 140.21 MiB |

The candidate evaluated a median 858 positions on each panel including its local verification when reached. The replay uses its original grid and whole-track gate. These host costs start with prepared CFO samples and end at the regional worker result. The receiver's RF time, tracking cost and the target board's performance are outside this timing. [Cost distributions](distributions.json)

## What changed from earlier experiments

| Earlier study | What the new experiment tests |
|---|---|
| [Beacon transfer](../../original-schedule/beacon-transfer/README.md) found a lower held shape loss in the containing tile at eight sites and no identifiable carrier contrast between sites. | Four offered tiles compete in one blind request. Two near pairs and one far pair vary lattice origin, orientation and order. The decision can explicitly answer `none`. |
| [Development-calibrated tile support](../../factors/region-support/development-noise/README.md) tested the interior of one supplied region with compact-v5 noise and orbit priors on two synthetic sites and two prior replays. | The candidate uses released measured tracks at eight physical sites, calibrates thresholds from seven other sites and uses an identical score for every offered square. |
| [Track-time regional null](../../receiver-core/region-null/README.md) tested time alignment and an inside/outside check at two simulated sites and two roof recordings. | The chronology sham shifts held samples at the fixed nominees. Independent omission panels measure geographic specificity among plausible rivals. |
| The frozen blind regional receiver forced the correct offer on all 11 original StarLoc queries with containing tiles and published zero field fixes. | The frozen engine reruns on the same four new offers and the same native-second samples as the candidate, using its original whole-track and changed-time checks. [Matched control scores](scores.csv) |

The public containing-offer centre comes from the sealed release. Both quartets have the same geodesic geometry and share two tiles. The candidate receives the opaque IDs and centre coordinates of a single quartet. Geographic truth enters after the prediction seal. The first placement pilot preserved the authorities but left a deterministic corner-distance cue. That invalidated the pilot's placement test. The new construction uses exactly symmetric spherical squares and inherits the model and thresholds. [Rejected placement pilot](placement-pilot/README.md) · [Blind plan](blind-plan.json) · [Prediction seal](prediction-lock.json)

## Reproduce

`STARLOC_MAT_ROOT` contains the timestamp subdirectories of the staged StarLoc release, each with its original `tracked_tones.mat`. A new field replay also uses the earlier regional experiment's staged public queries, clocks, orbit snapshots and survey-scoring receipt. The blind plan records the file digests. The benchmark command rebuilds the charts directly from this checkout. [StarLoc data provenance and author-supplied track framing](../../retry-and-transfer/bearing-transfer/SOURCE.md) · [Bound field inputs](source-lock.json)

```sh
taskset -c 22,23 env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python -B -m tools.pipeline_eval.qualification.site_region_set_trial \
  "$STARLOC_MAT_ROOT"
MPLBACKEND=Agg .venv/bin/python -B -m tools.pipeline_eval.qualification.site_region_set_results
OPENBLAS_NUM_THREADS=1 .venv/bin/python -B -m pytest -q tests/pipeline_eval/test_site_region_set.py
.venv/bin/python -B -m tools.pipeline_eval benchmark --study \
  reports/2026_11_19_receiver_screening/native-receiver/site-region-sets --pack
```

[Exact sources](source-lock.json) · [Calibration folds](folds-and-calibration.json) · [Paired position distributions](distributions.json) · [Score seal](score-lock.json)
