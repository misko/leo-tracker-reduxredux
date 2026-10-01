# Full-scan ARM coarse-cutoff removal

The full saved 300-second DS9 scan completed on physical PLUTO+ 192.168.1.15.
Removing the preliminary coarse-score cutoff preserves every original passing
candidate and adds 6,463 passing candidate entries. The unchanged rolling-backfill
tracker improves strict reviewed server-segment agreement from **47/62 to
50/62**, gaining seven references but losing four. It produces substantially
more hypotheses, and detector latency exceeds the 120 ms dwell interval more
often. This is a useful recall experiment, not an unqualified replacement for
the previous pipeline.

## Recovery with the same tracker

| Reference-duration bucket | Original coarse cutoff | Cutoff disabled |
|---|---:|---:|
| Short, <15 s | 3/9 | 7/9 |
| Medium, 15–30 s | 21/25 | 19/25 |
| Long, >=30 s | 23/28 | 24/28 |
| Total | 47/62 (75.8%) | 50/62 (80.6%) |

Gained: #2, #5, #7, #34, #54, #61, #62. Lost: #9, #19, #33, #37.
Matching criteria and the sole approved ref #10 exception are unchanged.
The original full-scan server detector and its 63 reference tracklets remain
the frozen oracle; 62 are eligible after that exception. Both one-to-one and
any-complete-output counts are 50 in this experiment.

All five previously missing long references now have >=80% matching source
coverage in one output. Three still fail the independent >=80% source-purity
criterion because their outputs include many detections not assigned to those
reference segments:

| Reference | Original matching sources | Cutoff-disabled matching sources | New source purity | Strict match |
|---|---:|---:|---:|---|
| #2 | 67/84 | 79/84 (94.0%) | 96.3% | Pass |
| #30 | 28/40 | 36/40 (90.0%) | 59.0% | Fail purity |
| #8 | 5/42 | 36/42 (85.7%) | 64.3% | Fail purity |
| #34 | 32/45 | 45/45 (100%) | 90.0% | Pass |
| #47 | 0/24 | 20/24 (83.3%) | 54.1% | Fail purity |

The extra points in #8, #30, and #47 are geometrically close to their server
curves: median / p95 circular CFO residuals to interpolated reference points
are **87 / 296 Hz**, **41 / 248 Hz**, and **42 / 354 Hz**, respectively.
This supports inspecting them as possible additional useful detections; it
does not prove identity or justify changing the scoring threshold. The report
keeps the strict failures visible.

## Regressions and extra hypotheses

| Previously matched reference | Before | After | What changed |
|---|---|---|---|
| #9 | 39/39 sources, 95.1% purity | 14/39, 100% purity | Coverage loss |
| #19 | 21/23, 87.5% purity | 22/23, 61.1% purity | More matching points, but source-purity failure |
| #33 | 27/30, 90.0% purity | 0/30 | No matching points in emitted hypotheses |
| #37 | 70/71, 98.6% purity | 0/71 | No matching points in emitted hypotheses |

All original passing detector candidates remain present, so #9/#33/#37 are
downstream tracking losses under the expanded input. The fixed active-hypothesis
bank and association/pruning behavior are plausible mechanisms; this experiment
does not separately isolate them. #19's additional in-span points have median
48 Hz and p95 230 Hz residual to the interpolated reference curve, so its
scoring regression is different from those coverage losses.

| Output diagnostic | Original | Cutoff disabled |
|---|---:|---:|
| Emitted track hypotheses | 327 | 542 |
| Hypotheses with zero source/CFO matches to any reference track | 43 | 139 |
| Of those, duration >=30 s | 6 | 26 |
| Hypotheses with <50% of points matching any reference track | 52 | 202 |
| Local next-point prediction residual p95 | 459 Hz | 572 Hz |

These are overlapping hypotheses, not distinct satellites or proven false
tracks. Reference support uses all frozen reference tracklets, including #10
for this diagnostic only. Geometric predictability is also not identity truth.

## Detector output and noise-related evidence

| Candidate entries across all 4,430 receiver windows | Original | Cutoff disabled |
|---|---:|---:|
| Evaluated by final GLRT | 9,977 | 35,440 |
| Passed final GLRT margin >=0.025 | 9,728 | 16,191 |
| Rejected by final GLRT | 249 | 19,249 |
| Passing with same-source server CFO agreement | 9,390 | 12,950 |
| Passing without same-source server CFO agreement | 338 | 3,241 |

The final gate removes much of the additional background, but unmatched passing
entries increase materially. Agreement means the same visit/RX/probe and
circular CFO difference normalized to 11.2 GHz <=2.5 kHz. This diagnostic is
not one-to-one, has no epoch gate, and includes duplicate candidate hypotheses.
The 3,241 unmatched entries cannot be equated to 3,241 false detections.
No noise-only ground-truth false-positive rate was measured.

## Physical ARM timing

| Metric | Original | Cutoff disabled |
|---|---:|---:|
| Mean detector time / dual-RX dwell | 56.94 ms | 103.47 ms |
| Median detector time / dwell | 54.69 ms | 102.86 ms |
| p95 detector time / dwell | 87.17 ms | 121.83 ms |
| Maximum detector time / dwell | 144.84 ms | 165.27 ms |
| Detector calls >=120 ms | 3/2,215 | 142/2,215 (6.41%) |
| Sum of detector-call wall times | 126.12 s | 229.19 s |
| Tracking from saved GLRT, median | 2.556 s | 4.569 s |
| Tracker whole-process median, including parsing/output | 3.625 s | 6.249 s |

Cutoff-disabled tracking repeats are 4.57451, 4.56882, and 4.56557 s. All
three physical outputs are byte-identical to host. Maximum observed tracker
RSS is 17,684 KiB. Original timing is the frozen prior physical run on the same
device; the new full detector timing is one fresh pass with all calls included.
p95 uses nearest rank.

New detector plus tracking compute totals about **233.76 s for 299.86 s of
capture**, excluding acquisition, staging, transport, and other pipeline
components. Average capacity is encouraging, but p95 and 142 dwell overruns
mean a per-dwell 120 ms deadline is not satisfied. Buffered continuous capture
and full-system contention have not been qualified. Saved-IQ replay including
transfer and verification took 1,362.7 s; that is not detector runtime.

## Validation and scope

- All 2,215 original raw-IQ hashes and event identities match the original
  full-scan inputs. First 20 ms/RX of each original 120 ms dual-RX dwell,
  2.5 MS/s, unchanged templates and final margin threshold.
- Frozen cutoff-disabled binary reused from the preceding diagnostic; no
  parameter tuning during this run. No new RF or firmware changes.
- Projection code checked against all 9,728 original observations: source
  groups, timestamps, lanes, CFOs, and scores agree exactly.
- Every original passing candidate, including multiplicity and every candidate
  field, is preserved in the new output.
- All 85 dwells from the previous ablation reproduce every non-timing receiver
  result field exactly in this full replay.
- Identical tracker binaries/defaults on both inputs; three host repetitions
  deterministic and three physical ARM outputs byte-identical to host.
- Original reference fixtures, thresholds, and accepted reports are unchanged.
  Source-purity limitations are reported rather than waived.

The next targeted work is to prevent the #9/#33/#37 tracking coverage losses
under the expanded candidate set, inspect the coherent extra-point cases, and
then qualify an affordable detector rejection policy or buffering strategy.
This run does not justify silently deploying the ungated configuration.

## Evidence and plots

- [Full-scan CFO comparison](full-scan-cfo.png), [PDF](full-scan-cfo.pdf)
- [Five long tracks before/after](five-long-tracks.png), [PDF](five-long-tracks.pdf)
- [Summary](analysis/summary.json), [full evaluation](analysis/evaluation.json)
- [Changed-reference audit](analysis/change-audit.json)
- [Physical tracking receipt](tracking-device/receipt.json)
- [Physical detector completion](arm/completion.json)
- [Projection validation](projection-validation.json), [protocol](protocol.md)

`run_arm.py`, `analyze.py`, `run_tracking.py`, `plot_results.py`, and
`audit_changes.py` reproduce the saved-data workflow. The analysis/projection
uses the scientific Python environment with
`PYTHONPATH=/var/tmp/leo-arm-realtime-publication/src`. Replay reads the saved
IQ store read-only. `MANIFEST.sha256` binds final artifacts and input dependency
hashes are recorded in `dependencies.json`.
