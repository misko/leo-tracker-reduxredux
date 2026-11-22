# Cold Gaussian family profile with ALGO08v3 fallback

The prototype invoked the full ALGO08v3 fallback on both saved recordings. The roof proposal took **0.302 CPU seconds** and missed the reference by **4.182 km** in both calibration arms. Its independent family estimates disagreed by more than 4 km. The southern packet reached fallback after **0.053 CPU seconds** because its confident associations supplied too little support. Both fallbacks reproduced their archived ALGO08v3 positions, frequency RMS and owner digests. [Roof receipt](measurements/family-profile-roof.json) · [Southern receipt](measurements/family-profile-south.json)

The research solver uses the prepared native detector tracks, original curvature gate, offered region and supplied causal orbit bank. At the region center it samples up to nine observations per curved track and ranks the full screened catalogue by a bounded orbital phase tangent and a track intercept. It fixes one satellite and integer alias for each nominated track. The fitted stage uses every observation on those tracks. It checks a 5 × 5 grid spanning the square and performs five bounded refinements of each grid minimum. Every calculation starts from the causal nominal phase. [Prototype](../../../tools/pipeline_eval/variants/algo08_family_profile.py)

At each location the fit eliminates each zero-mean 1,000 Hz Gaussian track intercept analytically and profiles a single Gaussian phase per satellite plus shared receiver terms. The original constant radio noise estimate fixes the data scale. Identity ridge precision applies to prior-scaled columns. The paired arms use the same rows, aliases, candidate set, priors and search budget. Fitted `c` adds one RF-dependent receiver column. Partitioning satellites by alternating support rank lets two disjoint family groups estimate the position independently. The score is the profiled data quadratic plus the Gaussian penalties. [Component tests](../../../tests/pipeline_eval/test_algo08_family_profile.py)

The predeclared fallback covers less than 80% of curved points with a decisive nominal association, fewer than six distinct satellites, invalid geometry, split estimates over 2 km apart, endpoints within 1 km of an offer edge, a coarse-grid score gap below nine outside a quarter-width radius, or any fitted phase beyond 15 s. Nomination calls a nine-point score gap decisive. The threshold values are development rules. Both arms must pass. A failure invokes the complete frozen solver on the same already prepared inputs. The shadow path has a position and residual RMS only. A release would need to build its publication packet, figures and comparable observation evidence. [Trial runner](family_profile_trial.py)

The RF-dependent column is constant inside each track. Freely fitted track intercepts could absorb it exactly. Here their finite Gaussian prior carries the between-track information about the RF coefficient. A lower penalized quadratic in the fitted arm can therefore reflect the intercept prior and provides no independent geographic validation.

## Saved comparisons

Both runs used one numerical thread with an exclusive Gauss lock, CPU 2, `nice -n15` and `ionice -c2 -n7`. The measured boundary starts at saved detections and ends after the fallback's position grid. It includes the stock preparation shared by the two routes. The inferred stock time removes the measured proposal CPU from that same run. The clock covers a single comparison per recording. [Runner](family_profile_trial.py)

| Saved input | Decisive / total curved points | Nominated satellites | Proposal CPU (s) | Total solver CPU / elapsed (s) | Inferred stock solver CPU (s) |
|---|---:|---:|---:|---:|---:|
| DS30-0374 roof | 645 / 2,918 | 11 | 0.302 | 21.579 / 23.844 | 21.277 |
| Southern near-edge simulation | 171 / 266 | 5 | 0.053 | 4.530 / 4.585 | 4.477 |

The roof profile evaluated 117 unique positions. Both arms chose the interior point 9.375 km east and 6.641 km south of the offer center. Its coarse-grid score gap exceeded 92 in both arms. Independent family estimates were 4.284 km apart at `c = 0` and 4.106 km apart with fitted `c`, exceeding the 2 km threshold. The RF fit and geographic scores use separate measurements. RMS uses each method's own nominated or recovered support. [Roof location reference](../location-audit/README.md)

| Roof calibration | Proposal quadratic | Proposal / ALGO08v3 RMS (Hz) | Proposal / ALGO08v3 horizontal error (km) |
|---|---:|---:|---:|
| `c = 0` | 641.603 | 104.977 / 101.536 | 4.182 / 1.855 |
| Fitted `c` | 641.398 | 104.975 / 101.520 | 4.182 / 1.935 |

The southern offer contains the simulated reference by 100 m. Its five nominated families trigger fallback before the grid. The frozen zero and fitted arms returned errors of 0.817 and 1.101 km, with RMS 6.502 and 6.392 Hz. This input exercises the low-support fallback. It leaves the proposed geographic edge check untested. [Southern audit and reference](measurements/exact-curved-lookahead-south-audit.json)

The hypothesis gained no solver time on these inputs. On DS30-0374, omitting the entire solver in the published stage clocks would still leave 58.92 of 84.85 seconds in acquisition and publication, a **1.44×** raw-to-publication ceiling for solver changes alone. Across the first 52 successful fixes that ceiling is **1.43×**. [ALGO08v3 stage clocks](../v3/single-core-target.md)

Five component tests checked the profiled track covariance, nested calibration arms, separate family-grid minima, and the fallback gates. Two release checks passed. This comparison used saved detector packets and no raw I/Q replay.

## Reproduction

The runner verifies the labelled v3 specification, all freeze pins, the assigned archive and offer, the saved detector bytes and the original terminal document. Position references remain in postfit scoring only. Give each invocation fresh output. The study uses the original saved DS30-0374 and public southern containing detections. [Physical baseline](exact-curved-physical-triage.md) · [Southern baseline](exact-curved-public-sites.md)

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
bench=/tmp/leo-algo08v2-2x-bench
frozen="$bench/integration-exact-curved-lookahead"
export OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 OMP_NUM_THREADS=1
export PYTHONPATH="$frozen:$release/src:$release"
flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 80 \
  "$release/venv/bin/python" -BPs \
  reports/ALGO08/single-core-2x/family_profile_trial.py \
  "$pair" "$frozen" "$saved_detector" "$saved_terminal" "$new_receipt"
```
