# Complete DS26-0162 replay with a nested 12-anchor primary

The nested detector completed all **6,772 visits** on the first attempt and preserved physical support and clocks. Its changed candidate stream increased geographic error by **203 m at `c = 0` and 220 m with fitted `c`** against the independently fitted original archive. The eight-worker replay took **456.04 seconds**. Every valid visit exceeded the 20 ms detector wall budget. [Raw audit](audit.json) · [Comparison](comparison.json)

DS26-0162 is the signed upper-edge, dual-antenna recording. The source binding preserves its original 25 km offer and 48 causal TLE snapshots. The earlier capture archive supplies an independent compact position control. The prospective frame contained 6,772 visits, including 6,713 valid visits and 59 exclusions. [Prospective binding](binding-lock.json) · [Protocol](PROTOCOL.md)

## Selected measurement

The nested detector uses 12 entries from the original 22-anchor retry schedule for each initial antenna evaluation. When exactly one initial lane passes the fractional gate, the other runs the 10 remaining anchors and combines their folded sums with its cached 12-anchor partial. Both paths use the released 512-point bank geometry, the row-wise selector, the previously qualified batched fine FFT and the same physical refiners. The distinct 256-point overlap-save study passed its held comparison separately. [Selected source lock](source-lock.json) · [Nested held study](../nested-anchors/README.md) · [FFT-length study](../fft-length/README.md)

The launch check used one original exclusion, successful old peer rescues in both physical directions, two failed peer controls and three sequence-hash visits. The installed and incumbent paths reproduced the archived factors. The add-ten and recomputed-22 nested paths agreed on all eight checks in complete public responses, projected factors and acquisition attempts. Both old peer rescue targets still matched at their held visits. This evidence qualifies sharing for the new anchor set on the tested inputs. Changing the 12 primary anchors changes the detector's measurements. [Launch receipt](receipts/smoke.json)

In the separate held study, four genuine DS26-0162 retry visits averaged 471.8 ms of detector CPU when recomputing all 22 anchors and 417.0 ms with sharing. The full replay supplies absolute resource measurements for the selected nested detector. The signed original factors supply the scientific control for the new primary. [Held interleaved timings](../nested-anchors/times.csv)

## Full waveform measurements

The replay authenticated all 106 chunks and retained all 13,426 physical probes, including complete timestamps and the 59 original exclusions. It took 1,305 logical nested retries with 469 gate-positive rescues. The earlier directly identified original schedule took 1,319 retries with 530 rescues. The new worker traces recorded 1,313 add-ten grids, with eight visits repeating that grid through the conditioned-CFO guard. All 120,312 batched fine-CFO calls used the batched path. [Full audit](audit.json) · [Fine timing](fine.csv) · [Earlier original retry census](../../retry-and-transfer/retry-policy-holdout/README.md)

| Published measurements across the recording | Signed original | Fresh nested |
|---|---:|---:|
| Complete candidates | 63,534 | 63,290 |
| Empty physical probes | 28 | 37 |
| Gate-passing candidates | 17,608 | 16,666 |
| Physical probes with a gate pass | 5,517 | 5,412 |

One-to-one matching within two cyclic samples and 1 kHz after wrapping CFO found **14,263** paired gate winners. There were 3,345 old-only and 2,403 new-only gated candidates at that tolerance. Of the original positive probes, 222 became negative. Of the original negative probes, 117 became positive. Another 97 probes passed in both streams and had no candidate match within the stated tolerance. These comparisons measure the detector output changes on the same saved signal. [Per-receiver science counts](comparison.json) · [Fresh factors](native.json.gz)

## Position and RF calibration

Independent compact services fit the fresh nested and archived original factors using the signed causal catalogue and original 25 km offer. Each service kept the two calibration arms matched on observations, candidates, priors and search budget. The nested stream supplied 5,412 observations and 165 tracks to the compact fit. The archive supplied 5,517 observations and 172 tracks. Predictions were sealed before scoring against the held survey. [Prediction lock](prediction-lock.json) · [Geographic scores](scores.csv) · [Original v5 roles](v5-roles.csv) · [Chart, c = 0](charts/c0/modifications.pdf) · [Chart, fitted c](charts/fitted_c/modifications.pdf)

| Position input | Error at `c = 0` (km) | Error with fitted `c` (km) | Conditional RF RMS, zero / fitted (Hz) |
|---|---:|---:|---:|
| Fresh nested replay | 0.60429 | 0.63640 | 50.8700 / 50.8793 |
| Archived original factors, independent compact fit | 0.40152 | 0.41672 | 47.4672 / 47.4601 |
| Earlier complete fast four-region replay | 0.68248 | 0.67001 | 57.5950 / 57.5959 |
| Earlier complete fast five-region replay | 0.66663 | 0.64980 | 60.1322 / 60.1307 |
| Original v5 no-repair | 0.39875 | 0.41503 | 108.2760 / 77.7621 |
| Original v5 selective gap | 0.39875 | 0.41503 | 108.2760 / 77.7621 |
| Original v5 omitted-track-one | 0.40328 | 0.42059 | 108.2011 / 77.7767 |
| Original v5 omitted tracks | 0.40328 | 0.42059 | 108.2011 / 77.7767 |

Fitted `c` increased the nested geographic error by 32.11 m. Within that same factor stream, conditional RF RMS increased by 0.0093 Hz and the frequency score changed from 37,262.786 to 37,249.750. The original archive's geographic error increased by 15.20 m with fitted `c`. Its conditional RMS fell by 0.0071 Hz and its frequency score changed from 37,386.160 to 37,369.648.

## Host timing

The eight raw workers occupied CPUs 2, 3 and 6–11, each capped at 512 MiB charged memory with zero swap. They authenticated 8.236 GB of compressed data and 10.835 GB of decoded IQ. The resident detector used 2,771.77 CPU seconds. The workers used 2,797.25 cgroup CPU seconds between bound starts and terminal snapshots. Peak worker RSS was 217.48 MiB and the highest charged memory peak was 512 MiB. Retained two-lane folded state peaked at 4,586,552 bytes. [Worker receipts](receipts/) · [Detector timing and per-RF ordinals](timing.csv) · [Timing figure](timing.pdf)

| Valid-visit detector clock | P50 (ms) | P95 (ms) | P99 (ms) | Maximum (ms) | At or under 20 ms |
|---|---:|---:|---:|---:|---:|
| Resident CPU | 365.33 | 784.50 | 894.96 | 1,285.01 | 0 / 6,713 |
| Resident wall | 410.05 | 872.18 | 1,998.79 | 14,903.39 | 0 / 6,713 |

Maximum detector CPU occurred at visit 1,634, RF channel 3 ordinal 204. Maximum wall time occurred at visit 1,669, channel 6 ordinal 208. The attested historical fast four- and five-region detectors completed 5,782 and zero calls within 20 ms, on the same 6,713 valid visits. Their earlier compact position stages took 99.94 and 128.81 wall seconds, respectively. [Ordinal tails](comparison.json) · [Earlier complete fast resources](../../latency-and-support/complete-timing/resources.csv)

| Independent compact fit, both calibration arms | Wall (s) | Cgroup CPU (s) | Charged peak (MiB) | Swap |
|---|---:|---:|---:|---:|
| Fresh nested factors, CPU 2 | 71.07 | 70.23 | 377.39 | 0 |
| Archived original factors, CPU 3 | 80.70 | 80.04 | 373.71 | 0 |

Raw launch through fresh coordinates took **531.93 seconds**. The archived-factor fit returned coordinates 541.54 seconds after that same launch. [Fresh fit receipt](receipts/actual/terminal.json) · [Archive fit receipt](receipts/archive/terminal.json)

## Reproduce

Use an unpublished evidence checkout to create a new prospective plan and selection. To repeat the published selection, copy its source lock into a new local work directory. Keep the original releases and sealed inputs at the paths named there. Each worker reads the original saved IQ directly.

For replay or fresh score assembly after shared accounting code changes, restore the two as-run capture modules into a clean checkout using the destinations and SHA-256 digests in the snapshot manifest. The generic figures renderer reads the sealed predictions and timings directly. [As-run source snapshot manifest](source-snapshot.json)

```bash
work=/var/tmp/leo-coarse-waveform-repeat
report=reports/2026_11_19_receiver_screening/coarse-and-navigation/coarse-waveform
mkdir "$work"
cp "$report/source-lock.json" "$work/source-lock.json"
.venv/bin/python -m tools.pipeline_eval.qualification.coarse_waveform preflight "$work"
.venv/bin/python -m tools.pipeline_eval.qualification.coarse_waveform run "$work"
.venv/bin/python -m tools.pipeline_eval.qualification.coarse_waveform_results position --work "$work"
.venv/bin/python -m tools.pipeline_eval.qualification.coarse_waveform_results publish --work "$work"
```
