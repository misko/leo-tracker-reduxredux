# Radio .20: saved-IQ repetition and acquisition coverage

Offline analysis finds intermittent stronger proposals in the saved 60-MS/s
CH3 capture that its six live scans missed. It does not establish a missed
valid acquisition. Recent 30-MS/s visits have much weaker frame-period
repetition, close to the saved control. No new RF was collected, and no
runtime gate or firmware changed.

Follow-up through the actual C worker now rejects all ten strongest
time-separated missed proposals: **0 of 80 past measurements accepted**.
Independent refinement/moment review passes. Thus wider scan coverage alone
does not produce a valid handoff from these tested proposals.

## Spectral and repetition comparison

All inputs are the exported 2.5-MS/s complex IQ, independently hash-checked
against the capture receipts or frozen replay input. The analysis uses
4,096-sample Hann-windowed spectra (610.3515625-Hz bins), averaged in
131,072-sample blocks. Each incomplete final analysis block is explicitly
excluded. Parseval energy checks pass; a generated tone has unit normalized
lag correlation and zero input gives zero.

The repetition statistic is squared normalized complex correlation at a
10,000-sample lag: 4 ms, or three nominal 750-Hz frames. Nearby 9,000- and
11,000-sample lags provide descriptive comparisons. It is not a calibrated
detector, false-alarm test or RF identity measurement.

| Saved input | Median 4-ms lag power | Ratio to mean of nearby-lag medians |
| --- | ---: | ---: |
| 30-MS/s CH1–CH4 visits | 0.0000072–0.0000079 | 1.16–1.22 |
| 60-MS/s CH3 visit | 0.0000550 | 8.77 |
| 60-MS/s CH4 visit | 0.0000092 | 1.42 |
| Saved positive replay input | 0.0001491 | 18.95 |
| Saved control replay input | 0.0000082 | 1.90 |

The normalized spectral shapes are broadly similar; spectral flatness ranges
from 0.792 to 0.819. These are different recordings, not a controlled 30-versus-
60-MS/s experiment. The result cannot attribute the difference to sample rate,
antenna pointing, LNB power or a particular transmitter. The control is a
development input, not independently established ground-truth noise.

The [spectral/repetition figure](figures/2026_09_13_radio20_saved_iq_coverage/saved-visit-spectra-v2.svg)
and [numeric results](figures/2026_09_13_radio20_saved_iq_coverage/saved-visit-spectra-v2.json)
retain the per-input quantities and excluded tails.

## Replaying acquisition windows

The unchanged C coarse scanner was compiled for host replay. Its eight
proposals were ranked with the same full-pilot FFT power calculation, using
an independent NumPy FFT. All 18 original windows across the three replayed
physical visits reproduce their complete integer grids exactly and reproduce
their retained ranking scores within numerical tolerance.

| Input | Replayed windows | Maximum full-pilot rank power |
| --- | ---: | ---: |
| 60-MS/s CH3, six original live windows | 6 | 0.00389 |
| 60-MS/s CH3, spaced coverage plus originals | 54 | 0.02590 |
| 60-MS/s CH3, consecutive 14,000-sample windows plus originals | 1,803 | 0.03987 |
| 30-MS/s CH3, spaced coverage plus originals | 54 | 0.00550 |
| 30-MS/s CH4, spaced coverage plus originals | 54 | 0.00518 |
| Saved positive, spaced windows | 48 | 0.08503 |
| Saved control, spaced windows | 48 | 0.00475 |

The denser 60-MS/s replay takes 44.1 seconds on the host, including its two
controls. Its strongest proposal is at capture offset 6.4344 seconds, in a
window the live scanner did not examine. Stronger proposals also occur in
other seconds; this is not solely an event after the live worker finished.
Consecutive input windows do not enumerate every possible full-pilot start:
the unchanged scanner still selects only eight coarse proposals per window.

Rank power alone does not prove the repeated-pilot support, fresh handoff or
native feedback required for tracking. The replay therefore qualifies no new
acquisition. It shows that sparse scan timing can hide stronger proposals and
motivates evaluating temporal coverage and proposal selection on this retained
capture before changing the ARM scan policy. It supplies no justification for
lowering native or startup acceptance gates. The newer 30-MS/s CH3/CH4 windows
remain much closer to the control even with wider temporal coverage.

The [spaced replay](figures/2026_09_13_radio20_saved_iq_coverage/saved-visit-coverage-v1.json)
and [dense replay](figures/2026_09_13_radio20_saved_iq_coverage/saved-visit-dense-coverage-v1.json)
include all window offsets, scores, source/input/reference hashes and runtime.
Analysis sources accompany them. The physical state remains the
[last verified 30-MS/s CH4-upper visit](2026_09_13_radio20_clean_loss_visits.md),
TX disabled, serial `1040005e0b100007100010000bf33a5d4d`. Sustained tracking and
physical clean-loss continuation remain unfinished.

## Do the stronger missed proposals support acquisition?

The follow-up selects the ten highest-ranked proposals separated by at least
500,000 samples (200 ms), each with enough retained data for a 447,851-sample
replay. Each exact source cut is hash-checked. The unchanged C coarse scanner,
full-pilot ranking, resolver, startup carrier prediction and catch-up worker
run against that cut. The replay reproduces the previously computed ranking
scores, then evaluates the actual repeated-pilot acceptance conditions.

| Replay group | Accepted past measurements | Maximum past coherence | C worker outcome |
| --- | ---: | ---: | --- |
| Ten strongest spaced 60-MS/s CH3 proposals | 0 / 80 | 0.0403930 | Insufficient supported history in every case |
| Saved positive input | 15 / 15 | 0.0872203 | Ready proposal with 15 supported observations |
| Saved control input | 0 / 8 | 0.0048718 | Insufficient supported history |

All 80 candidate measurements fail the existing 0.05 coherence requirement:
57 fail coherence alone and 23 additionally fail local correction bounds.
Independent NumPy resolver and dense-fit calculations verify 204 timing/CFO
hypotheses and 103 moment/fit records across the twelve cases. The reviewer
checks exact original-IQ cuts, moment words, coherence, CFO, rejection bits
and causal startup forecasts; six deliberate coherence/CFO mutations are
rejected.

Receiver time is a frozen retained snapshot. The positive's ready proposal
therefore demonstrates the offline software path, not a fresh ARM handoff or
physical native tracking. The source window is deliberately rebased to zero
for replay, with its original file offset retained separately. No RF or native
measurement is submitted.

This narrows the next step: improving proposal coverage remains useful, but
these tested missed proposals also lack per-pilot support under the current
policy. They cannot qualify clean-loss continuation or sustained tracking.
Any proposed integration across multiple pilots would need separate evidence
for its acceptance rule and resulting timing/carrier accuracy; this replay
does not authorize weakening the existing gates.

The [C replay result](figures/2026_09_13_radio20_saved_iq_coverage/missed-candidates/result.json),
[independent review](figures/2026_09_13_radio20_saved_iq_coverage/missed-candidates/independent-review.json)
and twelve retained worker journals are accompanied by the benchmark, runner
and review source. Original IQ cuts remain in the local evidence directory.

## Can sparse pilots support coherent integration?

Two offline diagnostics fit the first four retained pilot measurements and
predict the next four without fitting to their phase or frequency. These are
frames 0, 9, 18, 27, 36, 45, 54 and 63: measurements are approximately 12 ms
apart, spanning 84 ms, rather than adjacent 1.333-ms frames. All IQ is the
existing 2.5-MS/s coarse stream; no new RF is collected.

The first model removes the resolver CFO, fits a linear residual phase to the
training pilots and extrapolates it. The second fits a linear CFO drift from
the first four independently checked C estimates, integrates that predicted
frequency across the IQ samples, then fits the remaining training phase.
The second model uses estimates even when the C worker rejects them; this is
an exploratory diagnostic, not an authorized feedback or acceptance path.

| Saved input | Constant-CFO phase RMS / gain | Drift-model phase RMS / gain |
| --- | ---: | ---: |
| Strongest missed proposal | 2.076 rad / 0.063 | 1.374 rad / 1.146 |
| Positive | 2.299 rad / 1.236 | 1.553 rad / 1.978 |
| Control | 2.073 rad / 0.456 | 1.870 rad / 0.731 |

Phase RMS is the circular prediction error on the four held-out measurements.
Gain is `abs(sum(corrected amplitudes))**2 / sum(abs(amplitudes)**2)`, with a
maximum of four. Gain alone can hide a common phase prediction error and is
not a calibrated detection statistic. These twelve selected cuts do not
establish a false-alarm distribution or general sensitivity improvement.

The positive's first four local CFO estimates decline from 471,921 to 471,780
Hz; their fitted drift is about -3,824 Hz/s. The drift model improves its phase
prediction, but its held-out error remains substantial. Consequently neither
model establishes reliable phase prediction even for the saved positive.
This result cannot rule out coherent integration: sparse phase sampling has
frequency ambiguity in approximately 83.33-Hz increments, the linear drift
forecast can be inaccurate, and fractional reference timing and inter-frame
phase behavior still need examination. No specific cause is established here.

Before changing the tracker, the next bounded offline experiment should
inspect adjacent pilots on the positive and control, retaining exact timing
and reference-phase conventions. Any combined-pilot detector would then need
held-out timing/CFO checks and false-alarm calibration that includes its search
and selection process. Existing acquisition and native gates remain unchanged;
sustained FPGA tracking is still unqualified.

The [constant-CFO result](figures/2026_09_13_radio20_saved_iq_coverage/pilot-phase/heldout-pilot-phase-v1.json)
and [drift result](figures/2026_09_13_radio20_saved_iq_coverage/pilot-phase/heldout-pilot-drift-v1.json)
retain all complex correlations, per-pilot powers, source coordinates, phase
errors and provenance hashes. Both diagnostic sources accompany the results.
The first checks ideal phase prediction and cancellation; the second checks
an ideal chirp at the actual 12-ms cadence and verifies that changing held-out
CFO values cannot change the trained frequency model. These synthetic checks
do not constitute an independent numerical review of the physical phase model.

## Adjacent pilots expose a timing-model limitation

A follow-up examines frames 0 through 63 in three existing 2.5-MS/s input
cuts. The first 32 frames train a linear carrier model and residual phase;
the next 32 are held out. The initial timing schedule uses the resolved first
start, the C scheduler's Q16 period and quarter-sample rounding. Per-pilot
frequency searches cover resolver CFO ±1,000 Hz on a 5-Hz grid. These searched
peak powers are diagnostic statistics, not the C worker's acceptance results.

The fixed timing schedule gives median searched power 0.02764 on the positive,
versus 0.03719 on the strongest weak candidate and 0.00076 on the control.
That unexpected positive result motivates a separate ±2-sample timing search,
in quarter-sample steps, for each pilot.

| Input | Median power after local timing search | Timing-search boundary hits / 64 | Held-out power using training-only timing/carrier forecasts |
| --- | ---: | ---: | ---: |
| Strongest missed proposal | 0.03737 | 0 | 0.03586 |
| Positive | 0.07743 | 4 | 0.03459 |
| Control | 0.00148 | 10 | 0.00020 |

The local timing search is fitted separately on every frame and therefore is
an in-sample diagnostic, including on the held-out half. Its results on that
half never train the forecast: only the first 32 local positions and CFO
estimates fit the timing and carrier models used for the final column.
The rise in the positive's local power shows that fixed timing alignment
explains much of its apparent correlation loss. Unweighted forecasts still
perform poorly, with several training measurements weak or at the timing
search boundary. This experiment does not establish the cause of those weak
frames, nor prove that a robust fit will fix them.

Held-out phase RMS with the timing/carrier forecast remains 1.280 radians for
the weak proposal, 1.784 for the positive and 1.944 for the control. Coherent
gain is respectively 5.479, 0.074 and 5.439 out of a maximum of 32. A gain
number alone clearly supplies no defensible acquisition rule here.

The next implementation question is how actual C timing/CFO validity checks
behave at adjacent cadence, and whether excluding invalid measurements gives
a useful causal forecast. Coherent integration remains an unqualified research
option. No gate, ARM runtime or FPGA image changes in this experiment, and no
RF collection occurs. The previous 30/60-MS/s scan/revisit verification stands;
sustained native tracking remains incomplete.

The [fixed-timing result](figures/2026_09_13_radio20_saved_iq_coverage/pilot-phase/adjacent-pilot-phase-v1.json)
and [localization/forecast result](figures/2026_09_13_radio20_saved_iq_coverage/pilot-phase/adjacent-pilot-timing-v1.json)
include source hashes, all selected jobs, frequencies, powers and complex
correlations, with their diagnostic sources alongside. Six synthetic checks
cover chirp fitting, exclusion of held-out CFO, phase prediction, scheduler
examples and a known frequency peak. An additional
[18 direct-DFT spot checks](figures/2026_09_13_radio20_saved_iq_coverage/pilot-phase/adjacent-pilot-timing-spot-checks-v1.json)
reproduce selected local peak powers across all three inputs. These checks do
not independently validate the entire search, the physical model or a
false-alarm rate.
