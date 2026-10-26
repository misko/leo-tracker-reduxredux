# Independent audit

The complete measurement intervention and all eight matched nonlinear solves
pass the independent artifact audit. Four original-data controls reproduce
their saved endpoints and full objectives exactly. The refined DS24-0010 pair
passes the predeclared research checks. DS24-0011 fails paired accepted-ID
retention: its c=0 endpoint loses 57 postfit-only IDs, despite passing retained
residual, phase and precision gates. Fixed likelihood IDs remain exact in both
scans. The operational reference remains unchanged throughout.

The separately authorized frozen-endpoint readback reproduces the original
extension decisions. Both c=0 losses occur only at the original residual-slope
limit of 3: the 21-point 57955 owner changes from 2.999997410 to 3.007648003,
and the 36-point 56094 owner from 2.906246753 to 3.056059076. All other predicates
for those original hypotheses pass. This explains the discrete coverage loss;
it neither proves a physical identity failure nor validates changing the gate.
The original 57-ID preservation failure remains in force.

| Scan | Arm | Original error (km) | Refined error (km) | Raw gain (m) | Paired research qualification |
|---|---|---:|---:|---:|---|
| DS24-0010 | c=0 | 1.241915 | 1.107702 | 134.214 | Pass |
| DS24-0010 | fitted c | 1.246474 | 1.107491 | 138.983 | Pass |
| DS24-0011 | c=0 | 1.727734 | 1.634419 | 93.315 | Fail |
| DS24-0011 | fitted c | 1.567031 | 1.476448 | 90.583 | Fail |

These are two previously exposed development scans with four RF-selected
owners. The same correction vector enters both c arms; there is no independent
sample-rate, identity, geometry or generalization comparison here. Geographic
values were read only after the RF audit and root's separate release. The
independent distance readback uses Cartesian unit vectors rather than the
evaluator's haversine expression.

## Measurement and inference controls

All 159 native IDs are unique and complete: 38/37 points in the DS24-0010
target/control and 64/20 in DS24-0011. Eight exact prior results were reused;
151 new paired detector calls consumed 337.479 cumulative worker-seconds,
including preparation, below the frozen 480-second cap. Exact historical
parity covers 1,849 archived complete fractional candidate rows and 9,245
floating fields, all with zero error. The detector returned 2,544 raw candidate
records; unarchived records are outside that parity claim.

The numerical frequency and margin checks pass for every selected point.
An independent direct complex sum reproduces all 318 saved target/control
score cells within 9e-15. These checks establish local numerical consistency,
not true recorded CFO or globally identified peaks. Candidate, rank, integer
and fractional epoch, window midpoint, within-symbol demodulation and admission
decisions remain fixed. Native new-minus-old CFO is added once to every graph
occurrence and native observation view, preserving integer alias offsets.

The position audit verifies the full curved plus predictive objective, all
five original phase-refresh rounds, zero initialization, unchanged likelihood
membership and recomputed current-value gates. DS24-0010 retains 2,571 curved
and 615 predictive IDs per arm; DS24-0011 retains 2,241 curved IDs with no
predictive factor. All eight endpoints complete in 42.872 cumulative worker-
seconds, including preparation, below the frozen 600-second cap. There are no
retries, dropped points, alternate starts or failed numerical refinements.

## Interpretation

The scalar estimator is established prior work. The August 23 report already
implemented continuous GLRT64 exact/control refinement and separate longer-
pilot prediction. The previous review missed this close precedent; the
[attribution correction](PRIOR_ART_CORRECTION.md) identifies immutable sources.
The new evidence is complete-owner DS24 transfer under exact historical parity
and actual matched nonlinear position propagation.

All four raw geographic contrasts improve, while three of four descriptive
quadratic CFO residual RMSs worsen. That is a concrete demonstration that a
fixed polynomial scatter metric does not rank localization quality. It does
not establish that refinement is generally more physically accurate or that
all remaining measurement error is finite-bin bias. The localization objective
also compares different observed vectors, so its before/after difference is
not a model Bayes factor.

The optional [saved-response readback](../response/FINDINGS.md) uses the actual
signed native corrections with the old Gaussian/VI response matrix, without a
second RF scaling. Independent SVD projection verifies its quadratic/remainder
decomposition and vector additivity. Its approximately 134 m prediction is
close to the 140–142 m DS24-0010 endpoint movement, but it predicts only
22–24 m against 102–105 m in DS24-0011. Thus neither smooth-bias susceptibility
nor this frozen local calculation replaces a full nuisance-refitted solve.
The discrepancy does not isolate a unique physical cause.

The full solves also refit nuisance precisions: all four selected owners'
conditional RMSs increase, while the DS24-0010 RX2 CH4 control precision falls
to about 0.594 of its original value and the DS24-0011 RX2 CH4 target falls to
about 0.164. Thus the position change combines measurement and weighting
effects. A later crossed original/refined-observation and original-frozen/
refitted-precision comparison could isolate that mechanism. This is a proposal,
not an outcome of the present matched comparison. Target and control owners
were changed together within each scan, so the nonlinear result does not
attribute a gain to any single owner.

The most useful next scientific test is a frozen later block with complete
owner coverage, unchanged original acceptance and matched c arms. Keep failures
and operational fallback in its denominator. Do not use the present geographic
gains to select owners, relax the 57-ID retention failure, or promote an ALGO.
Further same-case smoothness metrics and additional demonstrations that a
continuous maximum raises its own score have limited discriminating value.

## Receipts and limits

- Measurement [preflight](measurement_preflight.json) and [terminal](measurement_terminal.json).
- Position [preflight](position_preflight.json) and [terminal](position_terminal.json).
- Released [geographic readback](geographic_readback.json).
- Posthoc [local-response readback](response_readback.json).
- Frozen-endpoint [postfit-gate readback](postfit_readback.json).
- Audit [source](check.py) and [scientific interpretation](INTERPRETATION.md).

The audit makes no new IQ, detector, geometry or optimizer calls. One initial
audit assertion incorrectly compared a window's start to its documented midpoint;
the [failed attempt](measurement_terminal_attempt01.json) is preserved with a
conservative 25-second charge. The repaired check includes half the 20 ms
window, matching every original counter/time join. No scientific file or
threshold changed. Total numerical audit time remains below 120 seconds.
