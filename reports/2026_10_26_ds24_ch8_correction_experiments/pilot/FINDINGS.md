The fixed panel gives no supported per-tone pilot-response correction and no
supported received-symbol-rate correction. All 16 requested slots completed,
covering 14 physical paired-receiver windows. The read/analysis job took 59.28 s.
Every exported historical candidate for both receivers reproduced within the
established tolerances before the new analysis. There were no physical, primary,
or received-rate failures. No raw IQ copies, collection, admission changes,
observation changes, or position fits were made.

The panel and full authority bindings are in [panel.json](panel.json) and
[raw_metadata.json](raw_metadata.json). Selection used chronological DS24-0010/0011
development scans, CH7 controls and CH8, both receivers: one original passed
winner and one failed window with maximum exported margin in [0.0125,0.025) per
cell, nearest scan midpoint then visit. All slots existed. Original full IDs,
candidate ranks, timing/CFO, exported candidates, source digests, segment/index
references and raw-window digests were frozen before analysis. The 16-row
[table](panel_results.csv) retains every slot and its original rank.

The primary comparison reuses the tested `ChannelPilotWorkspace`. Timing and the
**original finalized fractional tracking CFO** are held exactly fixed; the helper
parameter is named `acquired_cfo`, but the worker passes
`original_candidate['fractional_tracking_cfo_hz']`, not the coarse acquired CFO.
One complex gain per frame is compared with eight independent complex tone gains
per frame, with an independent complex DC in both models. Those are 4 versus 18
real nuisance parameters per frame. Each even-symbol fit predicts odd symbols
and vice versa. The two directions are paired within each frame for a descriptive
2,000-resample frame bootstrap.

In-sample explained fraction increased for all 16 slots, as the more flexible
model permits. Held-symbol SSE improvement ranged from **−0.1626% to +0.00671%**.
Only two estimates were positive, and both intervals included zero. None met
the declared requirement that both flat-versus-tone and wrong-sequence-versus-
exact lower prediction intervals be positive. Median change was −0.0420% for
passed slots and −0.1302% for failed slots. All eight passed slots predicted
better with the exact sequence than the rolled sequence; none of the eight
failed slots had a positive lower interval for that comparison. This does not
authorize admitting the failed slots or equate the response diagnostic with the
public detector margin.

![Fixed-anchor response and known-truth controls](pilot_response.png)

Independent complex tone/frame responses with independent Gaussian noise gave
predictive support in 32/32 known-truth controls; median held-symbol SSE gain was
62.45%. Flat-response-plus-noise, wrong-sequence, and noise-only controls each
gave 0/32 support events. The exact two-sided 95% binomial interval for 0/32 is
**0–10.89%**, and for 32/32 it is 89.11–100%. These are fixed-anchor synthetic
response-event intervals, **not a calibrated pipeline GLRT false-positive rate**.
They establish sensitivity to this tested response mismatch under the declared
synthetic conditions; they do not establish sensitivity to every recording
impairment.

A separate guarded-sample diagnostic reuses `FrameClock`/`WindowClock`, with
eight complex channel gains independently per frame, zero versus one common
received-rate parameter, matched carrier residual bounds ±120 Hz, fixed original
timing and rate bound ±100 ppm. Its no-DC, guarded geometry differs from the
primary comparison; their absolute SSEs are not compared. No recorded slot had
a positive lower held-symbol improvement interval. The largest point improvement
was only +0.00474%; nine slots hit a carrier/rate boundary and six had at least
one nonconverged parity fit. The term is received symbol/tone evolution against
the sample grid, not an identified transmitter-only clock.

The independent analytic control includes scaled symbol boundaries, random
complex tone/frame responses and nonzero independent noise. At injected **37 ppm
and +23.4 Hz residual CFO**, the even/odd estimates were **37.5517/36.6455 ppm** and
**23.3069/23.3774 Hz**, without boundaries. Held-symbol SSE gain was **16.2895%**,
with descriptive interval 12.706–19.543%. Zero-rate, wrong-sequence and noise
controls are also saved in [clock_controls.json](clock_controls.json).

![Separate received-rate diagnostic](received_rate.png)

The sole DS24-0011 RX2 CH7 passed window is explicitly retained: visit 3686,
original rank 0, margin 0.1731144833, probe start 163.2652501 s. Of 846 processed
receiver windows in that cell, one passed, 83 were near-gate failures and three
had no exported candidate. Its verified acquisition was complete, hardware
countered, provider-attested, 200,000 samples at 10 MS/s, with no quality flags.
The retune receipt records the 200,000-sample minimum post-recall guard satisfied.
[The audit](sole_RX2_CH7_audit.json) preserves the entire acquisition receipt,
both receiver candidate sets and nearby same-cell probes. A lone passed window
does not establish a continuous emitter track.

All validation is **within-window prediction conditional on original full-window
acquisition**, which already saw the held symbols. It does not withhold pipeline
GLRT data. Frame-bootstrap intervals are descriptive because dependence is not
calibrated. The small deterministic panel does not establish population coverage,
false-positive rates, absolute CFO truth or localization accuracy. This null
result concerns the tested per-tone response and received-rate terms; **noise
whitening and other RF impairments remain untested**. No correction qualifies for
regional position propagation or a matched-`c` localization comparison here.

Seven component-owned tests and 14 focused existing pilot/clock tests pass.
They check frozen nomination/missing behavior, flat-score parity, equality with
existing held-symbol prediction, independent channel-plus-noise recovery, wrong-
sequence/noise controls, and nonzero-rate recovery. [summary.json](summary.json),
[recorded.json](recorded.json), [controls.json](controls.json), and
[manifest.json](manifest.json) retain full outcomes, parity evidence, uncertainty,
source hashes and artifact hashes. Figures are also available as PDFs.
