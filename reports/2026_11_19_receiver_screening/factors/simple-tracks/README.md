# Sparse native GLRT tracks with the same joint position fitter

The sparse front end reduced median track-stage CPU from **2.12 s to 0.45 s** and full receiver CPU from **4.05 s to 2.56 s**. Across eight recordings it retained 90.4% of the accepted GLRT peaks and published six fixes per calibration arm. Graph retained 87.5% and published five. The sparse builder did not preserve Graph’s position accuracy. On the five primary recordings it increased upper-tail error in both calibration arms, even though both builders published the same four recordings.

## Measured changes

Both workers start from complete authenticated archived GLRT factors, the capture’s track configuration, an eligible causal TLE catalogue, and the same supplied 25 km tile. Both read and hash the same bytes, keep the same accepted peak per probe, and call the same frozen joint solver, with both `c=0` and fitted `c`. Graph’s primary anonymous-track digests, publication decisions and full position arms matched the earlier archived native-joint run exactly. Candidate track digests differed from Graph on every unmodified recording. [Prediction and source seals](prediction-lock.json)

The sparse front end packs disjoint paths using a second-order dynamic program over at most 48 predecessors per point. The archived slope and gap bounds admit at most one alias lift per edge. Velocity continuity informs path scores. A polynomial residual gate grows each path using available original peaks, with an explicit 600 Hz/s² curvature bound on fitted support. At a crossing, the owner must fit the sample at least one noise standard deviation better than a competing curve. The algorithm provides the original CFO samples with only integer alias lifts, preserving their times and frequencies for the downstream fit. It removes Graph’s blocked residual diagnostics, repeated conditional polynomial tests and structured joins.

| Median on eight roof recordings unless stated | Sparse tracks | Graph control |
| --- | ---: | ---: |
| GLRT read and peak-selection CPU | 0.128 s | 0.130 s |
| Tracks CPU / wall | 0.451 / 0.499 s | 2.124 / 2.469 s |
| Joint backend CPU | 1.696 s | 1.478 s |
| Full receiver CPU / wall | 2.563 / 3.010 s | 4.048 / 5.128 s |
| Max resident / virtual memory | 146.0 / 381.1 MiB | 150.2 / 385.7 MiB |
| Imported first-party files / physical lines | 16 / 3,179 | 19 / 3,941 |
| Accepted GLRT peaks retained | 28,164 / 31,139 | 27,257 / 31,139 |
| Total tracks / curved tracks | 867 / 471 | 960 / 522 |

One Graph worker took 23.82 s elapsed and 2.76 s process CPU on the shared host. Use CPU times to compare computations. The sandbox enforced a 512 MiB virtual address-space ceiling and measured resident memory via `VmHWM`. First-party source totals include the measured worker and common joint fitter. Python and installed numerical libraries contribute to resident memory. The replay starts at archived GLRT factors on x86-64. Its measurements cover neither IQ detection nor a phone or embedded board. [Deployment source list](deployment.json)

## Position and frequency

| Cohort and receiver | Fixes per arm | `c=0` median / P95 (km) | Fitted `c` median / P95 (km) |
| --- | ---: | ---: | ---: |
| Primary sparse | 4/5 | 1.815 / 3.099 | 1.198 / 3.182 |
| Primary Graph | 4/5 | 1.692 / 1.887 | 1.323 / 1.641 |
| Primary original v5 baseline | 5/5 | 0.567 / 2.070 | 0.689 / 2.153 |
| Confirmation sparse | 2/3 | 2.053 / 2.659 | 2.418 / 3.271 |
| Confirmation Graph | 1/3 | 1.922 / 1.922 | 2.047 / 2.047 |
| Confirmation original v5 baseline | 3/3 | 1.229 / 2.623 | 1.239 / 2.374 |

The standard charts and score table include all four original v5 choices. All four published on every roof attempt. A published sparse result was within 5% and 10% of original no-repair v5 on 2/8 roof attempts in each arm. The preregistered relative Graph error threshold was exceeded by three of four common primary fixes at `c=0` and two of four with fitted `c`.

For DS29-0082, the sparse stage kept 1,530 points to Graph’s 1,526, and the fit assigned 1,465 points to 33 orbits versus 1,480 to 34. Its held score improved at `c=0` from 0.346 to 0.382, but the pooled shift increased from 1.17 km to 2.80 km and position errors increased from 1.550/1.643 km to 3.275/3.504 km. On independent DS26-0092, the shift fell from 4.38 to 3.51 km and crossed the shared geometry threshold. Sparse published at 2.726/3.366 km. Graph withheld despite smaller forced errors of 1.786/2.367 km. More retained samples and higher held compatibility can coexist with weaker geographic accuracy.

Fitted `c` reduced sparse conditional RMS on all eight roof attempts, including the forced fits. Primary median RMS dropped from 172.9 Hz to 137.9 Hz. Geographic error improved on two of four primary publications and increased on two. DS29-0082 gained 41.2 Hz in RMS alongside a 0.229 km increase in location error. The original v5 controls are archived position references. The scientific candidate/control comparison uses the same joint backend. [Case-level coverage, geometry and errors](scores.csv)

Both workers withheld in the wrong frozen `r0` tile and on the deterministic within-lane shuffle. Wrong-tile forced errors were 23.131/23.235 km for sparse and 23.314/23.377 km for Graph. Both produced zero tracks on the shuffled data. [Transfer query bindings](transfer-queries.json)

## Reproduction

Run on Linux with the frozen native data, the repository environment and Bubblewrap. The command rebuilds both deployed source closures from the pinned inventory. Pick two locally available CPUs.

```bash
scratch=$(mktemp -d /tmp/simple-tracks.XXXXXX)
env OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  .venv/bin/python -B -m tools.pipeline_eval.qualification.simple_tracks_eval \
  --cpu 6 23 --work "$scratch/work" --out "$scratch/evidence"
.venv/bin/python -B -m tools.pipeline_eval figures --panel screening \
  --evidence "$scratch/evidence" --out "$scratch/charts"
.venv/bin/python -B -m tools.pipeline_eval.qualification.gallery_check \
  "$scratch/charts" --expected-charts 3
```

[Protocol](PROTOCOL.md) · [Sparse predictions](sparse-positions.jsonl.gz) · [Matched Graph](graph-positions.jsonl.gz) · [Summary distributions](summary.json) · [Charts](figures.json)
