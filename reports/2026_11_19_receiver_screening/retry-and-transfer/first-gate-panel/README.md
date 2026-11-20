# Stop fractional refinement after one or two original GLRT passes

The original detector reranks the retained coarse basins after fine CFO, conditioned CFO, and exact and control verification. Final rank orders by verification margin, verification score, conditioned score, acquisition score, and deterministic frequency and epoch ties. The tested change leaves that acquisition and the full batch of integer GLRT scores in place. It evaluates fractional refinements in ascending rank and keeps every response reached, including rejected candidates, up through the first or second passing 0.025 gate. A lane with fewer than the required passes exhausts its candidates. The same rule applies independently to a primary or retry attempt. The producer still retries a primary miss only when the other receiver's primary passes. [Protocol](PROTOCOL.md) · [Frozen roster](membership-lock.json) · [Independently bound producer and raw fixture](../first-gate-raw/input-lock.json)

## Archive accounting

The original native inputs cover 908,972 valid stereo visits, 5,217 invalid visits and 583,269 positive receiver lanes on the same surveyed roof. All 135 input hashes match the immutable roster. The policies preserve positivity on every exported lane. The original compact preparer chooses the maximum fractional margin among passes, with rank breaking a tie. A ranked prefix can therefore alter the CFO or margin sent to compact tracking while preserving whether the lane passed. [Assignment and counts by recording](archive-accounting.csv) · [Stage chart](stage.pdf)

| Policy | Changed compact winners / positive lanes | Known completed continuous refinements avoided | Possible fractional-anchor calls avoided | Fraction of original anchor calls |
|---|---:|---:|---:|---:|
| First pass | 114,535 / 583,269 (19.64%) | 2,626,388 | 3,551,723–4,069,977 | 20.26–30.50% |
| Two passes | 10,533 / 583,269 (1.81%) | 1,785,067 | 2,462,567–2,890,415 | 14.05–21.81% |

The capture projection omits incomplete fractional rows. Missing ranks before a later complete rank prove some earlier refinement anchors existed, while ranks after the last export are bounded by the original eight-candidate cap. The 12- and 22-symbol sets in the primary and retry are acquisition configurations. The lower fraction also allows an unobserved, exhausted primary attempt on a visit whose partner passed. The work ranges count candidate anchors. The original 8,291,467 exported complete rows alone provide the separately observed continuous-refinement count. [Bounds and cohort breakdown](archive-summary.csv) · [Accounting seal](accounting-lock.json)

## Independently timed raw windows

The raw qualification and archive panel agreed on every final rank prefix across 16 previously frozen IQ windows on four recordings. Twelve of these visits are on three recordings in the compact position panel. Full, first-pass and two-pass evaluated 312, 186 and 240 fractional anchors, respectively. All three kept the same 39 physical attempts and seven retries. The tested early-stop implementation used singleton batches for fractional grids. Across 80 matched repeats, first-pass saved 10.08 ms of complete detector CPU at the paired median and two-pass saved 4.54 ms. The median paired percentage savings were 2.75% and 1.30%, computed as `100 × (full − early) / full` for each matched repeat. [Independent witness comparison](raw-witness-comparison.csv) · [Actual raw detector timing](../first-gate-raw/summary.json) · [Raw stage chart](../first-gate-raw/stage.pdf)

## Compact positions on six complete recordings

The fitted first-pass and two-pass policies met the original v5 +10% allowance on two and one of six recordings, respectively. The completed full-original compact controls met the allowance on five. Both early-stop policies had larger fitted errors on both timing anchors than the full-original control. The first-pass policy improved on the full-original fitted error on DS26-0239, from 0.548 to 0.345 km. [Position errors](geographic.csv) · [Cohort summary](geographic-summary.csv) · [Fitted chart](charts/fitted_c/modifications.pdf) · [Zero-calibration chart](charts/c0/modifications.pdf)

| Policy | Published of 6, zero / fitted | Within v5 +5%, zero / fitted | Within v5 +10%, zero / fitted | Median km, zero / fitted | P95 km, zero / fitted |
|---|---:|---:|---:|---:|---:|
| First pass | 6 / 6 | 2 / 2 | 3 / 2 | 0.479 / 0.689 | 1.503 / 1.525 |
| Two passes | 5 / 5 | 1 / 1 | 2 / 1 | 0.889 / 0.730 | 0.961 / 1.209 |
| Full original compact | 5 / 5 | 5 / 5 | 5 / 5 | 0.568 / 0.516 | 0.946 / 0.955 |
| Original v5, no repair | 6 / 6 | 6 / 6 | 6 / 6 | 0.697 / 0.565 | 0.983 / 1.047 |

| Recording | First-pass fitted km | Two-pass fitted km | Full-original compact fitted km | v5 no repair fitted km |
|---|---:|---:|---:|---:|
| DS26-0237 | 0.421 | 0.543 | 0.262 | 0.271 |
| DS29-0082 | 0.939 | 1.257 | 0.516 | 0.517 |
| DS26-0239 | 0.345 | 0.730 | 0.548 | 0.613 |
| DS26-0148 | 1.682 | Withheld | 1.057 | 1.049 |
| DS29-0519 | 0.440 | 0.403 | 0.306 | 0.319 |
| DS29-0604 | 1.056 | 1.017 | Timed out | 1.041 |

The two-pass solver withheld DS26-0148 after an unstable gate refit. DS29-0604 retains its reused 210-second full-original timeout. The fixed paired 20 m guard preserved every solver publication decision. Allowance counts include all six scheduled cases and error quantiles use only published positions. The charts and reference table also include selective gap repair, one omitted track and two omitted tracks. [All four v5 options](original-v5-references.csv) · [Publication receipts](publication-and-position-timing.csv) · [Prediction seal](prediction-lock.json)

Fitting `c` changed paired median geographic error by +19.7 m at first-pass, +40.6 m at two-pass and −52.3 m at full original. The respective conditional RF RMS changes were +0.0118, −0.0037 and −0.0221 Hz. The frequency objective changed by +2.955, +4.861 and +1.280. These ablations reuse the same native factors within each policy. Paired geographic effects and independent arm medians describe different quantities. [Calibration effects](calibration.csv) · [RF fit and objective](frequency.csv)

The scoped compact position services took a median of 90.4 s wall and 74.7 s CPU for first-pass and 77.8 s wall and 74.5 s CPU for two-pass. The five measured full-original controls took 88.7 s wall and 81.4 s CPU at the median. These figures include both calibration fits and use the measured position boundary. [Position service measurements](publication-and-position-timing.csv)

## Reproducing the panel

Use a separate local evidence directory with a copy of the protocol and a new work directory. Freeze the six fit cases with the original offered tile, catalogue and causal orbit request. Then run archive accounting and capped position services. Geographic truth enters after the prediction seal.

```bash
.venv/bin/python -m tools.pipeline_eval.qualification.first_gate_panel freeze \
  --report "$panel_report" --work "$panel_work"
.venv/bin/python -m tools.pipeline_eval.qualification.first_gate_panel account --report "$panel_report"
.venv/bin/python -m tools.pipeline_eval.qualification.first_gate_panel fit \
  --report "$panel_report" --work "$panel_work"
.venv/bin/python -m tools.pipeline_eval.qualification.first_gate_panel_results stage --report "$panel_report"
.venv/bin/python -m tools.pipeline_eval.qualification.first_gate_panel_results position --report "$panel_report"
.venv/bin/python -m tools.pipeline_eval.qualification.first_gate_panel_results raw --report "$panel_report"
```
