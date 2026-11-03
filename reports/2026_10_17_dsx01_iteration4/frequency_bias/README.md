# Constant-Hz satellite residual hypothesis

The fixed 1000 Hz Gaussian-width model assigns 462/693 frozen challenge winners,
compared with 422 for matched zero-bias continuation and 96 at the immutable
original fitted-c production endpoint. It reaches the descriptive strong
restoration threshold in eight of 15 windows. This is a full-recording development
fit, not predictive or satellite-identity validation. Configured reference
distances remain poor on S01 and S04 (about 131 and 258 km respectively); frequency
recovery does not establish localization improvement.

Each bank satellite receives one constant absolute-Hz bias, shared across every
receiver, RF, channel and observation. Both predeclared global Gaussian widths,
300 and 1000 Hz, use bounds ±4000 Hz. The bias is an empirical residual hypothesis;
these results cannot identify transmitter oscillator error, TLE error or another
cause. No window-dependent frequency terms, satellite overrides, label locks,
reference-position seeds or new observations enter inference. Existing physical
prediction, frozen band corrections, common/relative timing priors, visibility,
detection q, clutter and winner/classification rules are unchanged.

The quadratic bias prior is included once and regularizes the shared intercept
gauge. Parameter-independent Gaussian normalization constants are omitted to
retain exact scalar objective nesting at bias zero. Consequently total objectives
across the two prior widths are not Bayesian model evidence. Both widths are
reported uniformly, without choosing a width from objective or window coverage.

## Matched full-recording comparison

Every method starts from the same immutable saved iteration2 fitted-c profile
endpoint for its source. For the controlled c=0 arm only vector coordinate 6 is
zeroed and fixed. All other coordinates remain free with the same priors. Bias
coordinates initially equal zero. The zero-bias arm is refit under the same cap.
Search uses two all-training-point signed candidate profiles at 250 Hz spacing
over ±4000 Hz, followed by 50 Hz local refinement. Each changed candidate is then
accepted only on actual full objective descent. Original winner membership,
all 693 observations in all 15 windows, all 20,084 observations and all five bank
candidate sets remain fixed. There are 215 recording-satellite pairs.

| c arm | Method | Full assigned /20,084 | Challenge assigned /693 | Assigned full RMS Hz | Strict endpoints /5 |
|---|---|---:|---:|---:|---:|
| fitted | b0 continuation | 13,784 | 422 | 155.82 | 4 |
| fitted | bias σ300 | 14,143 | 439 | 148.22 | 4 |
| fitted | bias σ1000 | 14,372 | 462 | 147.59 | 5 |
| zero | b0 continuation | 12,180 | 417 | 171.58 | 5 |
| zero | bias σ300 | 12,632 | 422 | 163.96 | 4 |
| zero | bias σ1000 | 12,884 | 470 | 162.05 | 4 |

Assigned RMS uses a changing population. In the fitted-c σ1000 comparison with
matched b0 continuation, the 13,251 retained full-recording points change RMS
152.54→143.32 Hz, with 1,121 new and 533 lost assignments. Within challenge
windows there are 51 new and 11 lost; the retained-point RMS changes
166.83→153.55 Hz. Outside the windows there are 1,070 new and 522 lost. Retained
points can change satellite identity; σ1000 changes 1,202 full-recording identities
relative to b0. Counts alone do not validate those identities.

The immutable original production baseline is a distinct comparison, always
labelled `original_*` in CSVs. Fitted-c σ1000 has 3,929 new and 779 lost full
assignments relative to original, and 376 new and 10 lost challenge assignments.
The 86 retained challenge points change RMS 161.67→149.11 Hz. For each window,
`net_original_missing_restored_pct = 100*(original_new-original_lost)/original_missing`.
The threshold is ≥80% of originally missing points restored on a net basis, not
80% total coverage. σ300 reaches it in seven windows; σ1000 in windows
001/005/007/008/009/010/013/015 (eight). Window003 remains zero. All denominators,
both comparison baselines, and losses are retained in `regions.csv`.

The zero-c arm is matched in observations, bank, calibration, priors and budget,
but its comparison to the immutable original fitted-c endpoint also includes the
effect of forcing c=0. Use the within-arm b0 comparison to isolate added biases.

## Costs, convergence and controls

Thirty primary receipts cover five sources × two c arms × three models. Eight
additional S01/S04 controls use ordinary local continuation within each bias
model from bias zero. All 38 receipts are retained, with zero execution failures.
No best-of-controls endpoint or width is substituted in the primary table.
Profiles do not uniformly beat ordinary continuation: S01 σ300 and S04 zero-c
σ300 have controls with lower same-model objective. The controls are not a global
optimization certificate.

Each inference has a 1,000 actual objective /120 s cap. Recorded total actual
objective calls are 16,078 across all 38 receipts; maximum per receipt is 611.
There are 1,680 cached candidate-profile calls, separately recorded, and zero
extra orbit projections for those profiles. Endpoint replay and reporting are
explicitly outside inference and never select parameters. Four endpoints miss
the strict projected-stationarity threshold 0.001 and are retained as rejected:
S01 fitted b0 (0.003968), S02 fitted σ300 (0.004219), S04 zero-c σ300 (0.001373),
S01 zero-c σ1000 (0.001059). All five fitted-c σ1000 endpoints pass.

## Conditional residual prediction

`conditional.py` and `run_conditional.py` implement a separate bounded diagnostic.
Physical vector, frozen calibration, clock and q are fixed at the same saved
iteration2 fitted-c baseline across both widths; c=0 only zeros its existing c
coordinate. Only new satellite biases learn from a temporal half, then predict
the excluded half in both directions. Held measured CFO never enters profile
selection. This baseline was already conditioned on the full recording, so this
is conditional residual prediction only, not clean cold-pipeline validation,
position prediction or independent identity validation. Positions remain exactly
unchanged. The per-fit cap is 300 cached density objectives /30 s, with profile
calls and one baseline orbit evaluation recorded separately. Results and an
aggregate summary are written separately from the full-data receipts.

All 40 fits completed. Thirty-nine worsen excluded-half likelihood; all training
objectives descend. Both directions pooled count each observation once:

| Fixed baseline c arm | Bias width Hz | Held full assigned before→after /20,084 | Held challenge before→after /693 | Held NLL change |
|---|---:|---:|---:|---:|
| fitted | 300 | 13,784→10,789 | 422→287 | +15,175.05 |
| fitted | 1000 | 13,784→8,307 | 422→262 | +24,388.50 |
| zero | 300 | 10,082→8,380 | 385→311 | +7,353.15 |
| zero | 1000 | 10,082→6,456 | 385→184 | +13,582.27 |

Positive NLL change is worse. The only individual improvement is S03 zero-c
late→early σ300 (−63.26 NLL). The conditional zero-c baseline is the immutable
fitted-c seed with c zeroed and no physical refit, explaining its different
baseline counts from the full-data continuation table. Thirty-five of 40 bias
endpoints pass strict stationarity. The diagnostic used 4,815 cached density
objectives and 3,360 profile calls; maximum actual density calls per fit is 261.
There are 40 training and 40 held baseline orbit evaluations, outside cached
density counts; held evaluations occur only after parameter selection. This
diagnostic provides strong evidence against treating the fitted biases as stable
temporal corrections under this baseline. The in-sample eight-window result
remains descriptive; neither width is promoted.

## Artifacts and validation

`comparison.csv` contains all 38 comparisons; `regions.csv` contains every frozen
region; `summary.json` contains all-five primary aggregates. `timing-pairs.csv`
binds the same 215 original recording-satellite pairs across original, b0, σ300
and σ1000, with common and relative timing kept distinct. The two timing
histograms and two all-15-window coverage plots include the original baseline.
Common timing values appear once per source/method in `comparison.csv`; they
must not be mistaken for independent 215 common timing measurements.

Nine hardware-free synthetic tests pass under the pinned scientific runtime:
exact zero-bias nesting, all physical/timing/clock/q/bias gradients including
the visibility boundary, proper prior/gauge, shared absolute-Hz physics, bounds,
exact cached profile replacement, held-CFO invariance through both fitting
paths, correct signed-bias recovery, and objective budgets. No production code,
sealed earlier artifacts, RF collection or persisted public contract changes.
