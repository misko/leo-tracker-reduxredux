# Positioning from GLRT candidates and causal TLEs

[Every roof modification, both calibration settings](figures/README.md) · [Errors for every recording](per-recording.csv) · [Distributions and coverage](distributions.csv) · [Whole-IQ detector comparison](../2026_11_19_receiver_frontend/README.md)

Each new receiver starts with the candidate peaks measured by the original GLRT, their sample counters and radio frequencies, an acquisition-time UTC bracket and the orbital elements available at that cutoff. It has to establish which satellites, if any, explain those peaks. No v5 tracker output or satellite assignments enter these receivers. The common reader exposes only the measured fields and verifies the detector and orbital files. Location truth is kept in the scorer. [Measurement input port](../../tools/pipeline_eval/qualification/cold_input.py)

Each receiver runs twice on the same inputs. The **global** run searches for the receiver with no site or tile supplied. The **matched-tile** run gets the original 25 km search area that v5 received. Publishing the supplied centre alone puts the estimate approximately 8.19 km from truth on these recordings. The score table tracks that prior alongside v5 and records a method’s best guess even when it withholds. DS26 and DS29 were recorded on the same roof. [Per-recording controls](per-recording.csv)

| From-scratch method | Why the measurements could determine position | Independent check |
|---|---|---|
| Carrier and frame timing pairs | Over two visits, a satellite’s changing range predicts both carrier-frequency change and frame timing drift. Vote for sites that explain both with the same orbit. | Check independent pairs and require the winning location to beat a spatially distinct alternative. [Method, sealed results and decision correction](point-votes/README.md) |
| Frequency tracklets | Three or more nearby peaks supply a frequency slope and curvature. Match these short curves to candidate satellites, then fit position using the independently built assignments. | Check satellite and RF diversity, disagreement between distant sites, and the frequency residual. [Method and results](rate-triplets/README.md) |
| Folded Doppler trajectories | Subtract a hypothetical satellite’s predicted Doppler from the raw frequencies. A real transmitter can leave a nearly constant frequency offset, even across the pilot ambiguity. | Carry each proposed satellite and offset to unused time intervals and test whether supporting peaks persist. [Method and results](folded-doppler/README.md) |

The same observations, orbit candidates and search budgets feed the zero- and fitted-calibration comparisons. Pair differencing cancels a frequency offset that is constant on a fixed RF channel. In the folded trajectory model it is absorbed by the freely fitted offset on that channel. The tracklet worker fits the RF-dependent coefficient explicitly. Frequency agreement and geographic error have separate columns or tables in each report.

At the sealed source revisions, the pair voter uses 327 Python lines, the tracklet solver uses 457 Python lines, and the trajectory accumulator uses 397 Python lines plus a 131-line C scoring kernel. These counts include comments and blank lines in the scientific modules. The shared capture reader, SGP4 library, coordinate transformations, tests and scoring harness are additional dependencies. [Pair voter](../../tools/pipeline_eval/variants/point_votes.py) · [Tracklet solver](../../tools/pipeline_eval/variants/rate_triplets.py) · [Trajectory accumulator](../../tools/pipeline_eval/variants/folded_doppler.py) · [Scoring kernel](../../tools/pipeline_eval/variants/folded_doppler.c)

## Six complete GLRT recordings

| Receiver | Global fixes within 5 km / published / attempts | Global median best-guess error | Global median wall | Given-tile fixes within 5 km / published / attempts | Given-tile median best-guess error | Given-tile median wall |
|---|---:|---:|---:|---:|---:|---:|
| Carrier and frame timing pairs | 0 / 0 / 6 | 10,541 km | 98.11 s | 0 / 0 / 6 | 16.69 km | 14.50 s |
| Frequency tracklets | 0 / 0 / 6 | 11,054 km | 194.06 s | 0 / 0 / 6 | 7.14 km | 13.03 s |
| Folded Doppler trajectories | 0 / 1 / 6 | 11,953 km | 7.68 s | 2 / 3 / 6 | 4.57 km | 2.71 s |
| Full v5 with original detector output | Unmeasured | — | — | 6 / 6 / 6 | 0.832 km | 266.62 s |

These are fitted-calibration results. Best-guess errors include all six recordings, even when the receiver withheld. The only global publication, from the folded-Doppler receiver on DS26-0237, was 8,431 km from truth. Its supplied-tile publications missed by 1.823, 4.025 and 6.378 km. Worker times are x86 measurements beginning after waveform detection. The tracklet sandbox prepared its input packet before its worker timer. The v5 timing control used the same stored original detector outputs. [All recording errors, both calibration arms](per-recording.csv) · [Timed v5 controls](../2026_11_19_receiver_simplification/paired-runtime.csv)

The experiments expose an ambiguity in satellite identification. The pair voter’s mean held-out vote scores reached 0.76–0.84 at its global winners. Its lead over a distant alternative ranged from −0.055 to +0.005. The folded receiver’s erroneous worldwide fix passed four held-out frequency profiles. Many sites and satellite assignments therefore remained compatible with the measured frequencies. [Pair-vote diagnostics](point-votes/scores.json) · [Folded receiver diagnostics](folded-doppler/README.md)

The three receivers also ran on the first declared tile from each original missing-region query for the three DS29 recordings. All nine attempts withheld in both calibration settings. Their forced guesses missed by 33.45–526.00 km. On those same three recordings with the correct tile supplied, eight of nine attempts also withheld. The sole published fix was 6.38 km from truth. These counts put the apparent false-fix improvement in the context of its low coverage. [Correct versus omitted tile chart](wrong-tiles/omitted-tile.png) · [Matched trials and per-case scores](wrong-tiles/README.md)

An independent simulation generated anonymous GLRT peaks at four locations in Europe, Australia, Mexico and southern Africa, plus a control with shuffled measurements. The three frozen receivers completed all 15 global searches. Each withheld on all four planted sites and the shuffle in both calibration arms. The pair voter’s best guess in southern Africa was 2.629 km from the plant, and it withheld on that case as well. These tests used an optimistic shared causal orbit catalogue for signal generation and inference. An earlier fixture counted elapsed time twice for one receiver’s timestamp convention. The corrected panel used a fresh hidden draw, the archived within-visit offset convention, and sealed predictions before scoring. [Independent location chart](scenes/position-errors.png) · [Generator, coordinates, correction and seals](scenes/README.md)

Opening the synthetic truth revealed the failure before the final position fit. The tracklet solver selected six to ten catalogue objects per site and the folded receiver selected four. Neither list contained any of the twelve planted emitters at any site. The fitted tracklet frequency RMS median improved from 4,441 to 4,374 Hz while both calibration arms withheld every positive case. [Satellite-association audit](scenes/physics-audit.json) · [Scored synthetic evidence](scenes/scores.json)

The existing v5 cavity stopping point is still the strongest measured simplification on this roof. It kept v5’s fix count, median, P95 and maximum over the 127 DS26 and eight DS29 recordings in both arms. Twelve DS26 coordinates moved by more than a metre, and one recording’s fitted error rose from 1.218 to 2.370 km. The six paired full numerical replays took a median 135.88 seconds at the cavity and 266.62 seconds through the complete v5 fit. This comparison isolates positioning after the original detector and assumes a supplied tile. [Position chart](figures/fitted_c/v5_core.png) · [Checkpoint and timing evidence](../2026_11_19_receiver_simplification/README.md)

## Changes to the existing v5 solver

Batching the conservative recovery score kept both DS26-0036 positions, both frequency objectives and the number of associated observations. The cumulative peak through that stage fell from 1,356,620 to 981,736 KiB. The full worker’s matched peak fell from 1,472,540 to 1,414,540 KiB, and the measured wall time rose from 157.81 to 166.89 seconds. Causal catalogue propagation remained an expensive later stage. [Batched scoring results](memory/README.md)

Processing the orbital catalogue in batches and retaining the exclusively owned position and velocity arrays reduced both whole-worker time and peak memory. The two complete fits reproduced the stock compact worker’s coordinates, conditional Doppler RMS, frequency objective, observation counts and recovery decisions in both calibration arms. The table shows one paired host replay per recording. Both peaks still exceed the measured 506,568 KiB total RAM of the embedded board. [Catalogue-memory results and numeric checks](catalogue-memory/README.md) · [Receiver-board memory evidence](../2026_11_19_receiver_frontend/embedded/README.md)

| Recording | Stock / revised wall | Stock / revised peak RSS | Peak reduction |
|---|---:|---:|---:|
| DS26-0036 | 155.83 / 133.37 s | 1,420,016 / 1,301,324 KiB | 8.36% |
| DS29-0082 | 118.32 / 96.13 s | 1,298,192 / 1,080,176 KiB | 16.79% |

## Reproduction

The position books are rebuilt from saved per-recording predictions. A live receiver run on the archive host authenticates the native GLRT file and causal TLE catalogue. A tile-assisted run has its own method name and recorded input identity.

```sh
.venv/bin/python -m tools.pipeline_eval figures --out /tmp/receiver-figures
.venv/bin/python -m tools.pipeline_eval run --variant point_votes_global --panel smoke --out /tmp/cold-runs
.venv/bin/python -m tools.pipeline_eval run --variant point_votes_matched_tile --panel smoke --out /tmp/cold-runs
.venv/bin/python -m tools.pipeline_eval.qualification.cold_comparison --report reports/2026_11_19_glrt_cold_start
```
