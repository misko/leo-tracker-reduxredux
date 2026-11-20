# Joint orbital phase for anonymous Doppler tracks

Joint assignment published nine fixes within 5 km on ten measured recordings in each calibration arm. Exact orbit fit and lean robust EM each published seven. The additional fixes came from one timing recording and one disjoint confirmation recording. Every method withheld the measured wrong tile and the measured shuffle. On the two independently drawn simulated sites, each method published the same one correct tile and withheld both omitted tiles and the shuffle. [Predictions and ownership seal](prediction-lock.json) · [Per-arm scores](scores.json)

The joint receiver tests whether independent track fragments can share one orbital phase error. It preserves the original candidate shortlist, receiver and RF nuisance terms, exact range-rate refinement and publication limits. Both final calibration arms use the same pooled assignments.

An earlier trace from the six timing recordings motivated this change. Of 125 capture-specific satellite IDs with at least four same-owner samples on some track, 96 appeared on multiple receiver/channel lanes. Seventy pairs of arcs on the same receiver and channel overlapped in time while carrying different IDs. These counts use agreement between the earlier lean and authenticated v5 assignments. They show where shared-orbit evidence is available and why multiple simultaneous assignments are needed. [Earlier ownership audit](../../../2026_11_19_receiver_convergence/track-fit/README.md)

## Assignment and measurement

At each bounded site and radio state, each shortlisted arc contributes three sufficient statistics to its candidate orbit's whitened least-squares cost. A single bounded phase and Gaussian prior represent that orbit across assigned arcs. The receiver tests isolated label changes and a fixed budget of two-arc moves for disjoint time intervals or different receiver/RF combinations, then finishes with a one-arc pass. A fixed-cost outlier option remains available on every arc. The original measurement model and loss scale determine that cost.

The archive test evaluates six earlier timing cases, four disjoint selected recordings from the same physical installation, one frozen wrong tile and one within-track shuffle. The geographic test uses two new simulated locations with previously measured Doppler residual and support patterns. It uses anonymous prepared GLRT CFO tracks plus a causal catalogue. Those two positions are synthetic and provide a separate check on the mechanics outside the archive geography. The simulation has no v5 comparison. [Frozen protocol](PROTOCOL.md)

## Geographic results

Each result pair gives zero and fitted calibration, respectively. The accuracy columns use only published fixes. All 51 workers completed within 60 s and both arms were scored on each query.

| Correct tiles | Receiver | Within 5 km / attempts, zero · fitted | Published median, zero / fitted (km) | Published max, zero / fitted (km) |
|---|---|---:|---:|---:|
| Timing archive | Joint orbits | 6/6 · 6/6 | 1.407 / 1.150 | 3.387 / 3.392 |
| Timing archive | Exact orbit fit | 5/6 · 5/6 | 1.667 / 1.427 | 3.779 / 3.457 |
| Timing archive | Lean robust EM | 5/6 · 5/6 | 1.832 / 2.136 | 4.479 / 4.158 |
| Disjoint archive | Joint orbits | 3/4 · 3/4 | 2.775 / 3.266 | 3.545 / 3.283 |
| Disjoint archive | Exact orbit fit | 2/4 · 2/4 | 1.929 / 1.703 | 3.484 / 3.201 |
| Disjoint archive | Lean robust EM | 2/4 · 2/4 | 0.938 / 1.075 | 1.353 / 1.563 |
| Fresh simulated | Joint orbits | 1/2 · 1/2 | 1.916 / 1.754 | 1.916 / 1.754 |
| Fresh simulated | Exact orbit fit | 1/2 · 1/2 | 1.916 / 1.754 | 1.916 / 1.754 |
| Fresh simulated | Lean robust EM | 1/2 · 1/2 | 2.076 / 1.934 | 2.076 / 1.934 |

Taking joint minus exact on the five common timing fixes gives median error changes of −0.062 and −0.065 km. On the two common disjoint fixes, the medians were +0.047 and +0.151 km. The additional joint fixes were DS29-0247 at 1.258 and 0.960 km and DS26-0259 at 2.775 and 3.283 km. The latter case accepted zero two-arc moves. Its gain therefore cannot be assigned to the pair moves alone. [Per-query positions and outcomes](scores.json)

Each receiver withheld the one measured omitted tile, the one measured shuffle, both synthetic omitted tiles and the synthetic shuffle in both arms. For the measured omission, joint's forced error was 23.314 and 23.377 km. Its two synthetic omitted forced errors ranged from 21.544 to 28.784 km. On the second correct synthetic tile, joint withheld for weak held-track support despite forced errors of 1.661 and 1.450 km. [Controls and diagnostic positions](predictions.jsonl.gz)

## Independent association audit

The prior v5 request and execution certificate were authenticated after inference and owner traces were sealed. Agreement uses the authenticated v5 owner on a uniquely matched `(receiver, channel, time, folded CFO)` observation as an independently computed comparison label. Physical transmitter identity remains unknown. The audit includes inferred owners in diagnostic fits.

| Measured cohort | Receiver | Used points | Unique v5 matches | Agreements | Coverage outside unique v5 matches |
|---|---|---:|---:|---:|---:|
| Timing archive | Joint orbits | 19,501 | 15,812 | 15,413 | 3,689 |
| Timing archive | Exact orbit fit and lean robust EM, each | 19,017 | 15,529 | 15,134 | 3,488 |
| Disjoint archive | Joint orbits | 15,851 | 12,827 | 12,665 | 3,024 |
| Disjoint archive | Exact orbit fit and lean robust EM, each | 10,917 | 8,968 | 8,817 | 1,949 |

On the 15,529 timing observations shared by every method, joint matched 15,130 v5 owners and each control matched 15,134. On 8,791 shared disjoint observations, joint matched 8,696 and each control matched 8,640. The coverage and common-observation comparisons distinguish additional usable associations from changes in identity agreement. [Method-specific ownership](ownership.json) · [Common-observation audit](common-ownership.json) · [Sealed owner traces](owner-traces.jsonl.gz)

## RF fit and resource cost

Fit RMS uses each method's selected observations, including forced fits. Held loss uses the shared synchronized chronological block split and the same normalized Doppler prediction metric. For the two controls, fitted-calibration held loss comes from a separate diagnostic refit on training associations, leaving the original publication decisions unchanged. Median inference CPU uses the ten measured correct-tile attempts.

| Measured cohort | Receiver | Conditional fit RMS, zero / fitted (Hz) | Held normalized mean loss, zero / fitted |
|---|---|---:|---:|
| Timing archive | Joint orbits | 176.53 / 135.55 | 15.57 / 15.69 |
| Timing archive | Exact orbit fit | 203.10 / 174.33 | 18.95 / 22.24 |
| Timing archive | Lean robust EM | 197.23 / 179.63 | 18.95 / 22.24 |
| Disjoint archive | Joint orbits | 212.48 / 179.79 | 5.15 / 4.88 |
| Disjoint archive | Exact orbit fit | 262.49 / 233.82 | 18.93 / 15.54 |
| Disjoint archive | Lean robust EM | 263.26 / 235.19 | 18.93 / 15.54 |

Median inference CPU was 2.53 s for joint, 2.19 s for exact orbit fit and 2.03 s for lean. Peak measured RSS was about 153 MiB for all three. The timing starts at prepared tracks and ends at the serialized decision's numerical portion. The worker also collects independent diagnostics after that section. Joint improved off-fit held loss on the disjoint recordings, while fitted calibration increased its median published position error on those three fixes. [Frequency and position summary](scores.json) · [Worker records](predictions.jsonl.gz)

## Reproduce

Use a new local scratch folder and the original archived inputs.

```bash
export OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1
scratch="$(mktemp -d)"
taskset -c 21 .venv/bin/python -m tools.pipeline_eval.qualification.joint_orbits_trial prepare \
  "$scratch/panel" --cache "$scratch/cache"
taskset -c 21 .venv/bin/python -m tools.pipeline_eval.qualification.joint_orbits_trial predict \
  "$scratch/panel"
taskset -c 21 .venv/bin/python -m tools.pipeline_eval.qualification.joint_orbits_trial score \
  "$scratch/panel" --out "$scratch/report"
.venv/bin/python -m tools.pipeline_eval.qualification.joint_orbits_figures "$scratch/report"
```

The replay used one pinned CPU and one numerical thread. The source lock precedes the new seed draw, input lock and prediction lock. [Source lock](source-lock.json) · [Seed](seed.hex) · [Input lock](input-lock.json) · [Prediction lock](prediction-lock.json)

The standard screening renderer reads four cohort descriptors. [Timing archive](timing/figures.json) · [Disjoint archive](confirmation/figures.json) · [Measured controls](archive-controls/figures.json) · [Fresh simulation](synthetic/figures.json)
