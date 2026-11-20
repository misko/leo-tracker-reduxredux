# Sparse original GLRT packets for compact positioning

Negative-lane fill improved geographic error on seven of eight recordings at `c = 0` and six of eight at fitted `c`. It put five and four recordings, respectively, within 10% of original v5 after the same-input retries. Fast four reached four in each arm, and full original compact reached all eight. Both sparse policies worsened DS29-0082, fast four's highest-error recording. [Position summary](summary.csv) · [Protocol](PROTOCOL.md)

## Position errors and returns

The table gives geographic error in kilometres as `c = 0` and fitted `c`. A dagger marks a fit recovered under the longer outer service deadline. [Per-recording endpoints and scores](scores.csv) · [First-attempt endpoints and scores](first-attempt-scores.csv)

| Recording | Fast four | Whole-visit replacement | Negative-lane fill | Full original compact | Original v5 baseline |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0237 | 0.382 / 0.323 | 0.228 / 0.239 | 0.363 / 0.299 | 0.353 / 0.262 | 0.362 / 0.271 |
| DS29-0082 | 2.489 / 2.346 | 3.758 / 3.743 | 3.479 / 3.524 | 0.568 / 0.516 | 0.567 / 0.517 |
| DS26-0036 | 1.003 / 0.935 | 0.832 / 0.801 | 0.935 / 0.859 | 1.260 / 1.196 | 1.278 / 1.208 |
| DS26-0162 | 0.682 / 0.670 | 0.677 / 0.668 | 0.639 / 0.625 † | 0.402 / 0.417 | 0.399 / 0.415 |
| DS26-0168 | 0.805 / 0.796 | 0.843 / 0.844 | 0.769 / 0.858 † | 1.496 / 1.533 † | 1.515 / 1.551 |
| DS29-0491 | 1.501 / 1.443 | 1.477 / 1.445 | 1.456 / 1.406 | 1.764 / 1.778 | 1.767 / 1.780 |
| DS29-0127 | 0.756 / 0.721 | 0.835 / 0.816 | 0.741 / 0.704 | 0.633 / 0.579 | 0.621 / 0.567 |
| DS29-0519 | 0.334 / 0.324 | 0.489 / 0.470 | 0.231 / 0.229 | 0.235 / 0.306 | 0.248 / 0.319 |

Nineteen of 22 new fits returned under the ordinary 210 s service deadline. Fill on DS26-0162 and DS26-0168 and full original compact on DS26-0168 timed out. There were zero other failures or withheld fits. All three retries finished in 119 to 144 s with the same prepared request, native factors, search settings, 512 MiB memory cap, and zero swap. The outer deadline for the retries was 420 s. A separate chart and ledger retain the first-attempt return count and results. [Attempt counts](fit-attempts.csv) · [Ordinary-deadline scores](first-attempt-summary.csv) · [Position charts for both calibration arms](charts)

The ceilings are one-sided. An endpoint qualifies when its error is at most 1.05 or 1.10 times the original v5 baseline error in the same calibration arm. [Thresholds by cohort, arm, and method](summary.csv)

| Policy | First returns, including reused fits | `c = 0` within +5% / +10%, with retries | Fitted `c` within +5% / +10%, with retries |
| --- | ---: | ---: | ---: |
| Fast four | 8 of 8 | 3 / 4 | 4 / 4 |
| Whole-visit replacement | 8 of 8 | 4 / 4 | 4 / 4 |
| Negative-lane fill | 6 of 8 | 5 / 5 | 4 / 4 |
| Full original compact | 7 of 8 | 8 / 8 | 8 / 8 |

At the ordinary deadline, fill reached both ceilings on four of eight at `c = 0` and three of eight at fitted `c`. Among the six hash-sampled recordings, fill with retries reached both ceilings on four of six in each arm. Fast four reached three of six at `c = 0` and four of six at fitted `c`. Fill moved DS29-0519 inside the `c = 0` ceiling. All four methods met both ceilings in both arms on the prior fresh recording, DS29-0491. [First-attempt and final comparisons](first-attempt-summary.csv) · [Held and fresh counts](summary.csv)

The median paired geographic change from fitting `c` was −47 m for fast four, −17 m for replacement, −25 m for fill, and −20 m for the full original compact fit. The median paired RF RMS change across those four methods ranged from −0.034 to +0.004 Hz. The analogous change in the conditional frequency score ranged from +1.13 to +3.09. Each comparison uses the same factors and search settings within its method. [Calibration ablation](calibration.csv)

## Recording selection and matching

DS26-0237 and DS29-0082 are the timing anchors. The remaining six come from ranking the other 20 complete streams by a salted physical-manifest hash, then taking three from each recording series. Available original visits use a separate hash-derived offset per recording and RF center. The membership and schedules were locked before opening scored endpoints or surveyed positions. The eight surveyed positions span less than one metre at the same roof. The results measure sensitivity across recordings and RF conditions from this site. [Membership and schedule seals](membership-lock.json)

The five sampled recordings marked held had already appeared in the reconstructed 20-recording roster. DS29-0491 is marked fresh because it entered the stock roster through the earlier fresh panel. Its fast and original v5 outputs were already available before this replay. Both timing anchors appeared in earlier factor comparisons. [Prior stock roster](../../pilot-influence/one-lane-roster/README.md) · [Prior fresh panel](../../receiver-choice/fresh-panel/README.md) · [Prior anchor support crossing](../../track-recovery/support-cross/README.md)

The original factors in each case come from the full native stream named by that recording's truth-free original positioning request. Both factor parents agree on delivery clocks, UTC anchor, sample counters, excluded raw visits, physical RF, and the ordered antenna metadata. Whole-visit replacement takes both original packets, including negatives. Negative-lane fill keeps a fast positive lane and uses an original packet only where fast is negative and original is positive. Candidate records are copied intact from one measured physical lane. [Packet audit](packet-audit.json) · [Selected-visit lineage](lineage)

The compact position inputs use matching causal TLEs, track configuration, tile, receiver release, and native numerical settings. The run reuses eight sealed fast fits and two sealed full original compact anchor fits after checking the request bindings, native input hashes, and receiver identity. The other 22 fits use pinned cores and a 512 MiB zero-swap cap. Every method shares its factor stream between `c = 0` and fitted `c`. [Execution plan](source-lock.json) · [Terminal prediction seal](prediction-lock.json) · [Four original v5 reference roles](original-v5-references.csv)

## Original detector work

The schedule offers 4,318 of 51,788 valid visits to the original detector. Fill adds 174 passing physical probes and 244 passing candidates across the eight recordings. Replacement adds the same 174 physical probes and drops 335 that passed under fast four. It also changes the candidates in lanes where both detectors pass, for a net loss of 4,996 passing candidates. Fill adds 13 to 32 passing probes per recording. Both recorded RF plans contribute added probes. [Per-recording and physical RF counts](packet-gains-by-rf.csv)

The two full original timing traces charge only detector CPU on valid visits. DS26-0237 uses the prepared original detector and DS29-0082 uses its earlier combined implementation. Summing the measured visits selected by the frozen schedule forecasts the extra worker's detector work. Each trace is a single full recording on the x86 host under a different parallel raw replay. The forecast excludes fast worker cost, decoding, queue delay, contention, and compact positioning. [Per-visit DS26 trace](../../original-support/prepared-waveform/timing.csv) · [Per-visit DS29 trace](../../antenna-confirmation/capture-whole/timing.csv) · [Cost calculations](cost.csv)

| Timing anchor | Scheduled original visits | Measured full original detector CPU | Forecast original detector CPU | Forecast share of one core over capture |
| --- | ---: | ---: | ---: | ---: |
| DS26-0237 | 562 of 6,766 | 2,914.74 s | 240.61 s | 80.2% |
| DS29-0082 | 406 of 4,868 | 3,035.04 s | 250.73 s | 83.6% |

Full original median and P95 detector CPU were 372 and 625 ms per valid visit on DS26-0237 and 600 and 1,197 ms on DS29-0082. Both sparse position policies use the same forecast detector budget. Their compact fit resources, when measured in this run, are in the position scores. [Stage figure](stage.pdf) · [Stage figure data](stage.csv) · [Position scores and resources](scores.csv)

## Reproduce the report

From the repository root, regenerate the tables and both calibration figures from the sealed position results.

```sh
.venv/bin/python -m tools.pipeline_eval.qualification.two_rate_holdout_results
.venv/bin/python -m pytest -q tests/pipeline_eval/test_two_rate_holdout.py tests/pipeline_eval/test_dual_rate.py
```

To rerun the numerical fits, copy the frozen membership, schedules, and protocol into a local scratch report. The original archive paths must resolve in the workspace. The commands below keep the new plan and terminal receipts separate from this report. [Executed source snapshot](executed-lock.json)

```sh
holdout_source=reports/2026_11_19_receiver_screening/receiver-deadline/two-rate-holdout
holdout_scratch=$(mktemp -d /var/tmp/leo-two-rate-reproduce-XXXXXXXX)
cp -a "$holdout_source"/{PROTOCOL.md,membership-lock.json,schedules} "$holdout_scratch/"
.venv/bin/python -m tools.pipeline_eval.qualification.two_rate_holdout_trial stage \
  --report "$holdout_scratch" --work "$holdout_scratch/work"
.venv/bin/python -m tools.pipeline_eval.qualification.two_rate_holdout_trial run \
  --report "$holdout_scratch" --work "$holdout_scratch/work" --batch 0
.venv/bin/python -m tools.pipeline_eval.qualification.two_rate_holdout_trial run \
  --report "$holdout_scratch" --work "$holdout_scratch/work" --batch 1
.venv/bin/python -m tools.pipeline_eval.qualification.two_rate_holdout_retry \
  --report "$holdout_scratch" --work "$holdout_scratch/work"
.venv/bin/python -m tools.pipeline_eval.qualification.two_rate_holdout_results \
  --report "$holdout_scratch"
```
