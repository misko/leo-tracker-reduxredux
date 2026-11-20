# Original detector visits selected by fast-track novelty

Track novelty selected **2,369 original stereo calls** on six held recordings, 6.14% of their 38,599 valid visits. The hash control spent the same counts in the same physical RF and token windows. Novelty gained 105 passing antenna probes and lost 289. Hash gained 127 and lost 158. The net support change was worse for novelty on all six recordings. [RF and call counts](stage.csv) · [Selection and source seal](source-lock.json)

## Position on the held recordings

All 12 fresh compact services returned both calibration arms within the 150-second cap. Novelty lowered the median error compared with hash and full fast. Both selective methods had a larger P95 than full fast and met the same number of paired +10% v5 allowances. Full original met every paired allowance. [Both calibration distributions](charts/index.html) · [Per-arm scores](scores.csv) · [Four original v5 options](v5-references.csv)

| Factors | Median error km, zero / fitted | P95 km, zero / fitted | Within +5% of v5, zero / fitted | Within +10% of v5, zero / fitted |
| --- | ---: | ---: | ---: | ---: |
| Track novelty | 0.470 / 0.510 | 3.079 / 3.122 | 4/6 / 3/6 | 4/6 / 3/6 |
| Matched hash | 0.583 / 0.634 | 3.003 / 3.799 | 4/6 / 3/6 | 4/6 / 3/6 |
| Full fast | 0.653 / 0.804 | 2.253 / 2.089 | 3/6 / 3/6 | 4/6 / 3/6 |
| Full original | 0.648 / 0.610 | 2.798 / 2.805 | 6/6 / 6/6 | 6/6 / 6/6 |

The novelty inputs yielded 11–39 fewer solver observations than hash on every recording. The differences exactly equal the differences in net passing antenna probes. On DS29-0082 both sparse inputs exceeded 3.76 km in both calibration settings. Full fast gave 2.489 and 2.346 km, and full original gave 0.568 and 0.516 km. [Worker observations and tracks](fit-resources.csv) · [Predictions sealed before geographic scoring](prediction-lock.json)

With the same selected observations, causal orbits, region and search budget, fitting `c` changed novelty's median RF RMS from 94.301 to 94.300 Hz. Its median geographic error moved from 0.470 to 0.510 km and the paired +10% count fell from four to three. [Separate RF and geographic summaries](summary.csv)

## Selection and factor assembly

For each antenna and RF, the selector follows up to four recent trajectories in folded CFO and frame phase from complete fast detector output. A token becomes available every 16 valid visits at that RF. It can be spent once when a fast trajectory is novel or interrupted, or on the final visit before the next token. Capture-clock actions close after 300 seconds. Novelty triggered 2,170 calls, and 199 used the token deadline. The matched hash control selects independently among the eligible visits in each spent window.

Development used two previously measured recordings. The 1.0, 1.5 and 2.5 thresholds all had negative signed yield against their matched controls. The least negative threshold, 1.0, was frozen at 0.071 fewer passing probes per original call averaged across the two development recordings. The six holdouts include two timing anchors and four hash-selected inputs. They share one physical roof. No geographic labels entered selection. [Protocol](PROTOCOL.md) · [Frozen development ladder](rule-lock.json)

Both policies substitute the complete original stereo packet at each selected visit. The novelty and hash inputs each changed 4,738 ordered antenna candidate lists. Their native winning candidate records changed on 1,571 and 1,584 probes respectively. The witness files identify each visit, antenna, and before-and-after packet checksum, including passes removed by the substitution. The compact receipt verifies the exact edited packet on each selected antenna. [Per-visit lineage](lineage) · [Independent fit inputs and observation counts](fit-resources.csv)

The earlier current-margin rule responds to a near-gate or competing candidate on one visit. The earlier recording audit spent original calls to decide whether to replace a whole recording. This experiment uses recent fast trajectories and substitutes individual recorded visits while keeping the complete fast acquisition. [Earlier per-visit trigger](../../acquisition-support/selective-capture/PROTOCOL.md) · [Earlier recording audit](../../retry-and-transfer/cascade-audit/README.md)

## Measured and modeled work

The CPU model charges all fast detector calls, including the early visits used to build trajectories. The six held recordings account for 657 measured fast detector CPU seconds. The novelty and hash scenarios add about 1,247 and 1,240 original detector CPU seconds, giving modeled totals of 1,904 and 1,897 seconds. Selected original CPU comes from measured per-visit costs on the two anchors and a projection from the matched series anchor on the remaining four. Computing both archive schedules took 1.05 measured CPU seconds total with already parsed fast factors. Independent compact CPU and wall times have their own table. [Detector and selection work](stage.csv) · [Compact service receipts](fit-resources.csv)

The six independent compact novelty fits used 417 measured CPU seconds in total. The six hash fits used 466 CPU seconds. The novelty scenario's modeled detector CPU is 2.90 times full fast.

A buffered serial model at recorded arrivals uses the measured original wall time for each reserved visit and the matched median fast call delay. By 300 seconds it completed 416/416 novelty visits and 404/416 hash visits on DS26-0237, and 296/297 and 295/297 on DS29-0082. The position replay used all selected archived original packets. These modeled completion counts describe availability under one assumed worker and retained I/Q. [Stage chart](stage.pdf)

## Reproduce the outputs

```sh
study=reports/2026_11_19_receiver_screening/coarse-and-navigation/adaptive-visits
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval.qualification.adaptive_visits_results \
  --work /srv/bulk/leo-dev/adaptive-visits-20261120
MPLBACKEND=Agg .venv/bin/python -m tools.pipeline_eval benchmark --study "$study" \
  --out /var/tmp/adaptive-visits-benchmark
```
