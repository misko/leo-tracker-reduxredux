# Wide receiver on 12 whole-IQ roof recordings

The stock wide detector and compact phase-release solver returned both calibration arms on **12/12 recordings using the fixed study precedence** and **11/12 at the earliest eligible launch**. Median fixed-primary error was **0.774 km at `c = 0`** and **0.781 km with fitted `c`**. Both arms were within 10% of their original no-repair v5 errors on **5/12** recordings. The roster extends the distribution from one roof across separate recordings and sessions. [Zero-calibration charts](charts/c0/modifications.pdf) · [Fitted-calibration charts](charts/fitted_c/modifications.pdf) · [Full score summary](summary.json)

## Roster and attempt coverage

The roster was locked from sealed study identities before this analysis opened predictions, measurements or geographic references. The primary precedence gave eight cases to full-stride, two held cases to exact-wide-iq and the remaining two to scout-full. The six cases added to the earlier comparison include the two exact-wide held cases, the two manifest-selected full-stride additions and two cases unique to scout-full among primary sources. Those groups reflect study membership. Capture dates overlap. [Protocol](PROTOCOL.md) · [Recording and study lock](roster-lock.json) · [Prediction and evidence lock](prediction-lock.json)

| Stock source | Number of services | Full recorded IQ verified | Both positions published | Deadline |
| --- | ---: | ---: | ---: | ---: |
| Full-stride control | 8 | 8 | 8 | 360 s |
| Exact-wide-iq control | 2 | 2 | 2 | 450 s |
| Scout-full control | 8 | 8 | 7 | 360 s |
| Fresh-waveform | 2 | 2 | 2 | 360 s |
| Deadline-repeat control | 2 | 2 | 2 | 360 s |
| Radius-full control | 2 | 2 | 2 | 360 s |
| Whole-winner stock | 3 | 2 | 2 | 286 s |
| **All attempts** | **27** | **26** | **25** | |

The first eligible DS29-0082 launch timed out at 360.08 s after 334.05 s of raw processing. The fixed full-stride primary for this recording finished and had the same native archive digest. A separate whole-winner stock launch for DS29-0082 exited after 2.36 s because the detector path was inaccessible to the service before either lane decoded. The ledger retains this setup failure, the timeout and all successful repeats with their measured deadlines, unit and build identities. Across repeated successes, both complete calibration-arm payloads agree exactly within each recording. [Attempt evidence](attempts.json) · [Repeat sensitivity ledger](sensitivity.csv) · [Original timeout](../../acquisition-support/scout-full/README.md) · [Whole-winner launch incident](../../receiver-core/whole-winner/initial-launch.json)

The stock detector used the full ±800 kHz range, 21 coarse bins and four proposed starts. Each service offered the same original 25 km tile and retained the recording’s acquisition clock, invalid-visit exclusions, input receiver order, causal catalogue and request. Install locations differed across some studies. The compact scientific source, native libraries and compiler inputs remained byte-identical. Original v5 curves use their archived capture-era observations. Portable archives and the sealed execution receipt identify replay-native inputs. The exact-wide and whole-winner factor checks additionally rehashed the original files in host scratch during this audit. [Original-grid control](../../receiver-core/full-stride/README.md) · [Held exact-wide study](../exact-wide-iq/README.md) · [Source hashes and archive locations](attempts.json)

## Position error and calibration

Each cell lists `c = 0` / fitted `c`. The 5% and 10% counts compare independently with the matching arm of original no-repair v5, using every attempted recording as the denominator. Medians and P95 use published positions. For the two-recording groups P95 interpolates between two observed errors. [Per-arm errors and all four original v5 options](scores.csv) · [Grouped results](summary.json)

| Group and selection | Both-arm coverage | Within 5% | Within 10% | Median error, km | P95 error, km |
| --- | ---: | ---: | ---: | ---: | ---: |
| All, fixed primary | 12/12 | 4 / 5 | 5 / 5 | 0.774 / 0.781 | 1.849 / 1.791 |
| All, earliest eligible | 11/12 | 4 / 5 | 5 / 5 | 0.756 / 0.755 | 1.323 / 1.328 |
| Legacy six, fixed primary | 6/6 | 3 / 3 | 4 / 3 | 1.162 / 1.127 | 2.198 / 2.094 |
| Legacy six, earliest eligible | 5/6 | 3 / 3 | 4 / 3 | 1.003 / 0.935 | 1.325 / 1.334 |
| Added six, either selection | 6/6 | 1 / 2 | 1 / 2 | 0.606 / 0.695 | 0.804 / 0.843 |
| Exact-wide held pair, primary | 2/2 | 0 / 0 | 0 / 0 | 0.675 / 0.721 | 0.806 / 0.857 |
| Full-stride held pair, primary | 2/2 | 0 / 1 | 0 / 1 | 0.508 / 0.497 | 0.665 / 0.653 |
| Scout-only pair, primary | 2/2 | 1 / 1 | 1 / 1 | 0.614 / 0.738 | 0.741 / 0.754 |
| DS26, fixed primary | 6/6 | 2 / 2 | 3 / 2 | 0.751 / 0.814 | 1.241 / 1.223 |
| DS29, fixed primary | 6/6 | 2 / 3 | 2 / 3 | 0.774 / 0.763 | 2.198 / 2.094 |

The original no-repair v5 median was 0.607/0.623 km, with P95 at 2.263/2.334 km. The missing DS29-0082 first position lowers observed coverage and removes the largest-error primary result from the earliest eligible error distribution. The added six have lower absolute errors than the legacy six, while only one zero-calibration and two fitted-calibration results meet the relative thresholds. [Per-recording chart data, zero calibration](charts/c0/modifications.csv) · [Per-recording chart data, fitted calibration](charts/fitted_c/modifications.csv)

Across the 12 primary pairs, fitted minus zero calibration changed geographic error by a median **−0.006 km**, conditional RF RMS by **+0.034 Hz** and conditional frequency objective by **−0.982**. The corresponding changes across the 11 paired first launches were −0.002 km, +0.049 Hz and −1.485. For the legacy and added primary groups the median conditional RMS change was −0.008 Hz and +0.062 Hz, respectively, and geographic error changed by −0.030 km and +0.015 km. These RF metrics describe the estimator’s own observations. The position score uses the surveyed roof position. [Paired distributions](summary.json) · [Conditional and historical RF columns](scores.csv)

## Measured time

Pipeline wall runs from the worker entry mark to its completed position result. Raw and position measurements come from their own worker marks. CPU counts cgroup usage over the pipeline. Manager wall is available separately for 10 primary completions. Deadline checks apply to the entire transient service. The detector column counts whole dual-receiver calls with measured wall time at or below the 20 ms input window. [Per-attempt measurement](attempts.json) · [Timing distributions](summary.json)

| Primary group | Pipeline wall median / P95, s | CPU median / P95, s | Raw / position wall medians, s | Detector calls ≤20 ms |
| --- | ---: | ---: | ---: | ---: |
| All 12 | 191.40 / 237.87 | 209.36 / 296.06 | 110.05 / 70.32 | 36,002 / 78,770 |
| Legacy six | 166.45 / 206.42 | 199.60 / 297.35 | 103.76 / 62.19 | 18,766 / 38,641 |
| Added six | 201.14 / 255.95 | 250.74 / 293.37 | 112.36 / 93.48 | 17,236 / 40,129 |
| Exact-wide held pair | 210.27 / 210.70 | 292.13 / 293.42 | 115.82 / 93.48 | 891 / 13,514 |

The median age of the causal catalogue at recording cutoff was 1.10 hours for the legacy six and 0.63 hours for the added six, with observed ranges of 0.31–1.83 and 0.02–0.98 hours. Recording conditions, selected catalogue, host scheduling and service deadline differ across these retrospective groups. The measurements describe this roster under those conditions. The 20 ms counts show wall deadline misses in both groups. [Recording timestamps and catalogue identities](attempts.json)

Re-score the sealed attempts and render both calibration plates from the repository root.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.wide_roster_results score
.venv/bin/python -c 'from tools.pipeline_eval.qualification import screening_figures as f, wide_roster as t; f.generate(t.REPORT/"charts", evidence=t.REPORT)'
```
