# DS7 wave 2: executed comparisons

This continuation uses SOL for numerical/model work and Terra for cached-input preparation. It retains all wave-1 records and failed attempts. Scores below are distances from the **unsurveyed operator reference**, at one exposed repeated site. Overlapping prefixes are not independent trials; these results cannot establish a population ranking or operational sub-kilometre accuracy.

## Recording-budget comparison

| Method | First 1 | First 2 | First 4 | First 8 |
|---|---:|---:|---:|---:|
| Joint frozen Doppler model | 4,004.26 m | 3,638.94 m | 2,771.03 m | 2,541.48 m |
| Equal mean of independent fits | 4,004.26 m | 2,923.44 m | 1,258.09 m | 1,930.07 m |
| Inverse training-RMS-squared mean | 4,004.26 m | 3,748.47 m | 2,206.03 m | 2,152.44 m |
| Mean of lowest-RMS 75% | 4,004.26 m | 2,923.44 m | 1,830.89 m | 2,532.71 m |

All completed entries converge/interior or aggregate qualified upstream fits. The one-recording control entries are the algebraic identity of the single estimate; separate one-member aggregation runs were unnecessary. Every control uses the same independent estimates. RMS is a frozen training-only, conditional MAP-residual statistic, not a geographic-confidence estimate. At two members, retaining `ceil(0.75*n)` retains both, so the 75% and equal controls coincide by definition.

Equal averaging is closest to the reference at both four and eight recordings. Its error increases from four to eight; more data does not monotonically improve this control. No entry reaches 1 km, and this one group does not justify selecting a production model. First-four evidence: [joint](coordinator/prefix4-score-v1/scores.json), [equal](coordinator/controls-equal-first4-score-v1/scores.json), [inverse RMS](coordinator/controls-inverse_rms2-first4-score-v1/scores.json), [lowest RMS 75%](coordinator/controls-lowest_rms75-first4-score-v1/scores.json). First-eight evidence: [joint](coordinator/first8-score-v1/scores.json), [equal](coordinator/controls-equal-first8-score-v1/scores.json), [inverse RMS](coordinator/controls-inverse_rms2-first8-score-v1/scores.json), [lowest RMS 75%](coordinator/controls-lowest_rms75-first8-score-v1/scores.json).

All eight independent fits converge with interior solutions, yet none is below 1 km: errors in chronological order are 4,004.26, 2,205.18, 2,886.62, 2,407.33, 4,065.12, 2,859.12, 2,316.45 and 11,769.67 m. Their median is 2,872.87 m. The final capture is a substantial error despite numerical convergence. These are eight recordings from one site, not eight independent sites. Sources: [singles 1–2](coordinator/prefix2-regression-v1-score/scores.json), [3–4](coordinator/singles-003-004-v1-score/scores.json), [5–8](coordinator/first8-score-v1/scores.json). The early prefix2 regression inadvertently selected all 122 plan units; only two singles and that prefix had available inputs. Its unavailable rows remain in the sealed receipt and are not counted as 122 scientific fits.

An additional predeclared **historical-style initialization** control uses independent-fit timing offsets, starting once at the spherical mean of the eight single estimates and once at the donor-center position. Historical DS6 used independent timing offsets and a zero-position start; the spherical-mean start is a declared addition, not an exact historical reproduction. Both starts converge and the selected solution is interior. Its reference distance is 2,541.47 m, only about 1.4 cm different from the default group8 result. Objective, banks, bounds and per-start optimizer remain fixed; this uses two starts versus the baseline's three, so it is not a matched-total-call benchmark. Initialization does not explain this group's kilometre-scale gap. [Sealed control score](coordinator/historical-init-score-v1/scores.json).

## Search and source-null comparisons

On `single-001`, the local three-start control and all nine predeclared geographic starts converge to essentially the same interior optimum. The wider search used 125 objective evaluations against the same 180-evaluation allowance as the local control, and completed in approximately 39 seconds. This addresses the earlier timeout. It supports agreement across these starts within the frozen region and finite candidate bank; it does not prove global search or catalogue completeness.

The exploratory fixed-1% constant-frequency null mixture also converges to essentially the same estimate. Mean null responsibility is about 1.08e-11. This particular constant-frequency alternative does not explain away the observed track dynamics. It is not a complete interference model or independent satellite-identification evidence.

Scored distances are 4,004.26 m for local, multibasin and null-mixture fits (differences below two millimetres). [Local score](coordinator/local-score-v1/scores.json), [multibasin score](coordinator/multibasin-score-v1/scores.json), [null score](coordinator/null-score-v1/scores.json), [pre-fit null specification](null-spec.md).

## Other directions

| Proposed direction | Completed coverage | Still outstanding |
|---|---|---|
| Corrected joint model and aggregation | First 1/2/4/8 panel, eight singles, three aggregation controls | Remaining ten groups and full88 |
| Orbit inputs | Wave-1 matched causal freshness smoke | Archived alternative products and group comparisons |
| Receiver-clock states | Conditional real-data derivative/rank screen | Independent constraints, nonlinear fitting and location evaluation |
| Orbit-error hierarchy | Wave-1 support/admission review | Defensible identities/priors and actual hierarchy fits |
| Association/search | Nine-start single-recording search, fixed constant-null mixture and deterministic replays | Broader banks, aliases, wrong-association controls and group evaluation |
| Pilot/CFO extraction | Ordinary/robust/differential waveform panel with held and scrambled controls | Broader support, calibrated false-support checks and downstream location ablation |

- Receiver drift now passes a **local conditional sensitivity** screen with real frozen derivatives: rank 61/61, scaled condition about 55.35, projected receiver-column norms about 0.594 and 0.941. Independent calibration and full mixture/nonlinear tests remain unmet, so no clock-position fit is admitted. [Clock report](clock/REPORT.md).
- CFO extraction now has an eligible same-lane held waveform comparison and deterministic scrambled-pilot control. Ordinary/robust profiles produce real coherence of 0.151/0.151 on RX0 and 0.104/0.105 on RX1, versus roughly 0.006–0.007 scrambled; this is one held window per receiver. Differential phase is rejected for boundary hits on 4/14 and 8/14 frames. A cross-channel visit remains explicitly inapplicable. Earlier method-label and lane interpretations are superseded with original receipts retained. Cumulative existing-IQ use is 163.2 MB and 27.22 analyzer seconds; no RF was collected. These diagnostics do not establish frequency accuracy, calibrated false support, or positioning improvement. [Authoritative CFO receipt](cfo/FINAL-CFO-RECEIPT.md).
- Wave-1 orbit-freshness and hierarchy results remain unchanged. This wave does not acquire missing historical ephemerides or manufacture calibration/identity priors.

## Numerical and transport work

The fast profiler batches candidate fixed-point iterations without changing the scalar root solves or scientific model. Three real prefix2 objective/gradient probes match exactly; objective calls improve 2.53–3.69x. End-to-end prefix2 improves from 56.97 to 32.98 seconds while reproducing the old prediction exactly. Prefix4 completes in 84.93 seconds and group8 in 170.30 seconds under the predeclared wave-2 300-second allowance. [Solver report](solver/README.md).

The first prefix4 attempt failed closed at a loader check. The third capture contains one seven-training/zero-held track; the unchanged exporter correctly excludes it under its pre-existing eligibility rule. The repaired fast loader requires exactly all eligible tracks and reports exclusions, while rejecting omitted eligible or duplicate tracks. The original failure and source snapshot remain preserved. Neither the bank nor the scientific selection rule changed.

The fifth bank reached its initial 150-second preparation cap. The timeout remains recorded. A new bounded preparation lease was declared using measured workloads; its retry succeeded in 111.71 seconds. This is a resource-policy continuation, not score-directed model tuning. [Initial input receipt](inputs/preparation-provenance.json), [continuation lease](preparation-continuation.json).

The first 1/2/4/8 panel, all eight independent fits, and the additional historical-style initialization control are complete. Remaining groups/full88 are not launched automatically, and this report is not a claim that all proposed model families have been evaluated. Terra's [final artifact audit](review/FINAL-ADDENDUM.md) verifies the frozen membership and exact independent-estimate provenance used by the controls.

## Priorities after this tranche

1. Compare the frozen joint model and equal averaging on the remaining chronological groups, with the same membership, failure accounting and explicit bounded leases. Retain the two RMS controls to test whether their current disadvantage repeats. This is evaluation on an already exposed site, not untouched confirmation.
2. Expand pilot/CFO diagnostics to additional eligible windows and rates only under a new bounded specification; admit a downstream positioning ablation only after acquisition, lane and boundary checks pass. The current tiny pilot result is promising prerequisite evidence, not a replacement observation product.
3. Complete independent receiver-clock constraints and nonlinear identifiability checks before fitting extra clock states. Keep orbit-error hierarchy gated on identity support and independently defensible priors; time-causal alternative orbit products remain limited by archived availability.
4. Broader candidate-bank, alias and wrong-association controls remain necessary. The nine-start and constant-null results address narrow search questions only; neither warrants priority over the observed systematic positioning gap.

## Verification and reproducibility

The complete DS7 component suite passes (69 tests), and Ruff passes for all DS7 tools and tests. Dataset metadata verification retains the original 88-recording manifest digest. All 159 wave-1 report files and 31 bound source/config/test files remain unchanged. Wave-2 closeout binds report files, run/score seals and current source hashes; original failed attempts and superseded CFO interpretations are retained.

After the historical-style run, source-binding validation was hardened to reject a different or reordered recording group. The coordinator independently checked that all eight actually executed initialization sources were in the correct order and bound by their source seals. The executed adapter is retained in `solver/frozen-source/`; its original v1 arm remains intact, and the hardened arm is v2. This interface repair does not imply a new scientific run.
