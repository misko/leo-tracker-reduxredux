# Original GLRT on one physical RF center

This panel routes both antennas at one fixed physical RF center to the original capture GLRT. At every other center it uses the fast four-region detector. The archived factor replay preserves complete stereo visits from one branch at a time, including negative results. It retains all eight recordings from the earlier two-rate panel and adds DS26-0197 and DS29-0604 by a manifest-only draw. All ten recordings came from the same surveyed roof. The retrospective count-matched control distributes the same number of original visits across centers using the final per-RF visit counts. [Protocol](PROTOCOL.md) · [Enrollment](membership-lock.json) · [Schedules](schedules/)

## Position and publication

Whole-RF routing published nine of ten positions in each calibration arm. With fitted `c`, it passed the original v5 +10% allowance on four of ten recordings, compared with four for count-matched, five for full fast and eight for full original compact. At fitted `c`, whole-RF gave smaller errors than fast in four of nine paired positions and smaller errors than count-matched in three of nine. The median paired changes were +5 m versus fast and +69 m versus count-matched. The lower whole-RF P95 versus count-matched reflects the large DS29-0082 improvement. [Per-recording errors](geographic.csv) · [Summary by cohort](geographic-summary.csv) · [Fitted chart](charts/fitted_c/modifications.pdf) · [Zero-`c` chart](charts/c0/modifications.pdf)

| Policy | Published of 10, zero / fitted | At most v5 +5%, zero / fitted | At most v5 +10%, zero / fitted | Median km, zero / fitted | P95 km, zero / fitted |
|---|---:|---:|---:|---:|---:|
| Whole RF | 9 / 9 | 3 / 4 | 4 / 4 | 0.791 / 0.865 | 1.812 / 1.794 |
| Count-matched across RFs | 9 / 9 | 5 / 4 | 5 / 4 | 0.717 / 0.771 | 2.853 / 2.928 |
| Full fast four | 10 / 10 | 4 / 5 | 5 / 5 | 0.774 / 0.765 | 2.045 / 1.939 |
| Full original compact | 8 / 8 | 8 / 8 | 8 / 8 | 0.541 / 0.547 | 1.588 / 1.574 |
| Original v5, no repair | 10 / 10 | 10 / 10 | 10 / 10 | 0.594 / 0.628 | 1.654 / 1.677 |

The 5% and 10% counts use all ten recordings and the no-repair v5 baseline. Medians and P95 use published errors. The other three v5 options are included in the position charts and reference table. [All four v5 options](original-v5-references.csv)

| Recording | Whole RF fitted km | Count-matched fitted km | Full fast fitted km | Full original fitted km | v5 no repair fitted km |
|---|---:|---:|---:|---:|---:|
| DS26-0237, timing anchor | 0.315 | 0.315 | 0.323 | 0.262 | 0.271 |
| DS29-0082, timing anchor | 2.036 | 4.031 | 2.346 | 0.516 | 0.517 |
| DS26-0197, prospective | 0.998 | 0.891 | 0.992 | 0.677 | 0.689 |
| DS29-0604, prospective | 0.865 | 0.771 | 0.734 | Timed out | 1.041 |

Both routed fits withheld DS26-0168 with an unstable gate refit. The full-original first attempt there and the new DS29-0604 full-original run timed out at 210 seconds. The separately archived 420-second DS26-0168 full-original retry returned a fitted error of 1.533 km. Applying the fixed 20 m paired tile-face guard left the publication counts as recorded by the solver. [Publication and position timing](publication-and-position-timing.csv) · [Archived retry](archived-retries-geography.csv) · [Prediction seal](prediction-lock.json)

## Calibration and compact timing

Across the nine paired whole-RF fixes, fitted `c` changed the median paired position error by −32.8 m, conditional RF RMS by +0.014 Hz and the frequency objective by +3.108. DS26-0197 deteriorated from 0.791 to 0.998 km in the same ablation. The calibration table gives separately paired changes in geography, RF RMS and the frequency objective for each policy. [Paired calibration](calibration.csv) · [RF and frequency metrics](frequency.csv)

Whole-RF compact services took 96.8 s median wall and 80.2 s median CPU, including native preparation and both calibration arms. The count-matched services took 118.6 s wall and 82.7 s CPU. The whole-RF timing anchors took 105.3 s wall and 83.3 s CPU on DS26-0237, and 47.2 s wall and 37.7 s CPU on DS29-0082. The archived fast controls supply matched endpoints and solver stage values. The scoped position service measurements are available for the new routed jobs and eight original controls. [Measured position service scopes](publication-and-position-timing.csv)

## Detector support

The four factor policies each cover 65,305 valid stereo visits and preserve 2,410 hardware-invalid visits. Whole-RF routing sends 8,352 valid visits, or 12.79%, to the original detector. It gains 354 positive antenna probes and loses 636 versus the full fast detector. The count-matched control gains 361 and loses 624. A positive antenna probe has at least one candidate passing the recorded fractional margin gate. Compact association uses the complete routed candidate records. [Stage figure](stage.pdf) · [Per-RF counts](packet-counts-by-rf.csv) · [Pair lineage](lineage/)

| Timing anchor | Original RF (GHz) | Original visits / valid | Whole-RF original CPU (s) | Count-matched CPU (s) | One-twelfth CPU (s) |
|---|---:|---:|---:|---:|---:|
| DS26-0237 | 12.2096875 | 846 / 6,766 | 356.7 | 364.5 | 240.6 |
| DS29-0082 | 12.6903125 | 739 / 4,868 | 427.1 | 463.4 | 250.7 |

The CPU comparison sums exact selected visits from the standalone original-detector traces. That work is equivalent to 1.19 and 1.42 original-detector cores over the two 300-second recordings. The faster lane-selector trace on DS26-0237 yields 303.5 seconds for whole-RF, 309.8 for count-matched, and 204.5 for one-twelfth. These sums cover the original branch only. Position times are measured in separate fitting services. [Original-detector CPU](detector-cost.csv) · [Faster selector sensitivity](detector-cost-selector-sensitivity.csv)

## Reproducing the factor replay

Stage into a separate evidence directory containing a copy of the protocol and use a new local work directory. The runner checks the prior recording and fit seals and the installed solver release. It launches one no-swap, 512 MiB position worker on each of cores 16–19 with 210 seconds per new fit. The two raw sources and every staged request retain their immutable original capture, catalogue, tile and causal history bindings. Once the position ledger is sealed, score against the independent survey and original v5 options.

```bash
.venv/bin/python -m tools.pipeline_eval.qualification.rf_lane_panel stage \
  --report "$panel_report" --work "$panel_work"
.venv/bin/python -m tools.pipeline_eval.qualification.rf_lane_panel run \
  --report "$panel_report" --work "$panel_work"
.venv/bin/python -m tools.pipeline_eval.qualification.rf_lane_panel_results --report "$panel_report"
```
