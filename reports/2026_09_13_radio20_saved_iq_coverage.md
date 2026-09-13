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

## Existing C gates recover a useful adjacent-pilot forecast

The next replay runs the unchanged C 2.5-MS/s IQ moment collector and tracking
solver on the previous diagnostic's 64 localized pilots per input. All
integer moment words, dense-fit timing/CFO corrections, coherence and rejection
bits are checked against the independent NumPy calculations. The existing
0.05 coherence threshold and local correction bounds remain unchanged.

Only measurements accepted by C in frames 0–31 train a linear timing and
carrier forecast. That forecast is frozen before frames 32–63, which receive
new C measurements at the predicted quarter-sample positions and CFOs.
Held-out localization results do not enter the forecast, and held-out
measurements do not feed back into it.

| Input | Accepted localized measurements | Accepted training measurements | Accepted forecast measurements |
| --- | ---: | ---: | ---: |
| Strongest missed proposal | 0 / 64 | 0 / 32 | No forecast authorized by this diagnostic |
| Positive | 53 / 64 | 26 / 32 | 27 / 32 |
| Control | 0 / 64 | 0 / 32 | No forecast authorized by this diagnostic |

The positive timing fit advances by 0.01782 coarse samples per frame relative
to the nominal frame period, about 5.35 ppm. Its fitted CFO changes by
-4.865 Hz per frame, about -3,649 Hz/s. The five rejected held-out measurements
are frames 35, 41, 47, 53 and 59: each fails both coherence and local bounds.
Their periodic spacing is an observation, not an established explanation of
the transmitted waveform or RF path.

This is materially better than the preceding unweighted fit of every local
estimate. It provides a reason to pursue validity-filtered adjacent-pilot
startup before introducing coherent integration or weakening gates. It does
not yet establish an acquisition algorithm: training positions/CFOs came from
a relatively broad diagnostic search, the forecast is a Python fit rather
than the production C trend controller, and neither ARM runtime cost nor a
fresh native handoff has been measured for this path. The next implementation
step is to exercise the production trend/catch-up path with these accepted
adjacent observations and measure its bounded ARM cost.

The [C validity result](figures/2026_09_13_radio20_saved_iq_coverage/pilot-phase/adjacent-c-validity-v1.json)
retains all 224 independently checked moment/fit records and provenance.
Its [replay source](figures/2026_09_13_radio20_saved_iq_coverage/pilot-phase/check_adjacent_c_validity.py)
builds the unchanged collector and solver into a host library. No RF,
firmware, acceptance gate or production runtime changes occur. Sustained
30/60-MS/s native tracking remains unqualified.

## Production C feedback sustains the saved positive replay

The production C trend predictor and scheduler now replace the diagnostic
Python fit. Training still comes from the preceding offline localized
measurements: all first-32 outcomes, including rejections, enter the C history
port, which retains 26 accepted positive observations. There is no change to
production source or acceptance gates.

Both frozen history and causal feedback accept 27/32 measurements in frames
32–63. Extending the test uses the exact original positive input, SHA-256
`af991e03e69271c253d2fe6b5aeff110c9da5d5bd6ddda8c6850584f9e97b1c4`,
with enough retained IQ to test through frame 1799.

| C predictor mode | Measured frames | Accepted measurements | Outcome |
| --- | --- | ---: | --- |
| Frozen first-32 history | 32–63 | 27 / 32 | Refuses frame 64 because history is stale |
| Feedback after each measurement | 32–1799 | 1,367 / 1,768 | Still supported at frame 1799 |
| Weak candidate or control, either mode | None | 0 | Refuses initial forecast with no supported training history |

The feedback run covers 2.357 seconds of frame intervals. Its longest sequence
of rejected measurements is four frames; the final measurement passes with
coherence 0.07728. Each prediction precedes its IQ measurement, and rejected
estimates enter the existing history API with their rejection bits intact.
They do not become supported observations. The frozen-history result also
shows that a predictor cannot continue indefinitely on its training data.

All 1,800 measured records in the extended comparison have exact C integer
moments and dense-fit corrections/coherence/rejection checked independently.
C job quantization matches the rational scheduler oracle, and batch prediction
leaves its input history unchanged. This is coarse 2.5-MS/s saved-IQ feedback,
not native 30/60-MS/s FPGA feedback, receiver-paced catch-up or a live handoff.
The diagnostic training search remains outside the production acquisition
path. ARM execution cost and source-time freshness still require measurement.

The [short C trend replay](figures/2026_09_13_radio20_saved_iq_coverage/pilot-phase/adjacent-c-trend-v1.json)
and [extended replay](figures/2026_09_13_radio20_saved_iq_coverage/pilot-phase/adjacent-c-trend-long-v1.json)
retain every measured job, moment word, fit and terminal refusal, with their
sources alongside. This establishes a useful production-C feedback baseline
for a bounded ARM replay; it does not yet complete the FPGA tracking goal.
No RF is collected or firmware changed.

## Actual ARM replay rules out every-frame software measurements

A bounded saved-IQ replay ran on radio `192.168.1.20`, serial
`1040005e0b100007100010000bf33a5d4d`, with the resident 60-MS/s image.
The operator acquired both radio leases, attested identity and TX-safe idle
state, verified staged input/binary hashes, ran the alarm-bounded executable
and removed its temporary files. Before/after identity, boot, image hashes,
buffer state and TX-safe state match. No RX buffer or native job is opened.

The executable uses the unchanged C collector, solver, trend and scheduler,
with the same 32 diagnostic training records and original positive IQ.
All 1,768 ARM scheduled jobs, rejection decisions and fitted values match the
independently checked host replay within the review's numerical tolerances.
Both platforms accept 1,367 measurements.

| Compute metric | Host | Radio ARM |
| --- | ---: | ---: |
| Total for 1,768 measurements | 0.386 s | 3.723 s |
| Mean per measurement | 0.218 ms | 2.106 ms |
| 99th percentile | 0.274 ms | 2.239 ms |
| Maximum | 0.440 ms | 2.442 ms |
| Measurements exceeding the 1.333-ms frame period | 0 | 1,768 |

Timing includes prediction, IQ moment calculation, solve and history update.
It excludes input loading, output serialization and live capture/DMA costs.
ARM computation alone consumes 1.579 times the represented source duration.
This is an unpaced compute benchmark, not a receiver-freshness qualification.

Therefore the current software collector cannot sustain measurements on every
750-Hz frame on this ARM in the tested build. The result changes the next
experiment: test less frequent ARM observations for maintained support and
headroom, while preserving the FPGA path for native per-frame measurements.
Neither a two-frame cadence nor any broader system throughput is qualified by
the table alone. Startup localization cost also remains outside this benchmark.

The [ARM operator receipt](figures/2026_09_13_radio20_saved_iq_coverage/pilot-phase/arm-bench/operator.json),
[host/ARM comparison](figures/2026_09_13_radio20_saved_iq_coverage/pilot-phase/arm-bench/review.json),
both measurement journals, benchmark, operator, reviewer, training records and
build hashes accompany this report. ARM binary SHA-256 is
`991750d4a82262694bcdfa085a4a71fcfee1aef954495a15a6cb028b3f85ae4f`.
No RF or firmware changes occurred; sustained native tracking remains unfinished.
