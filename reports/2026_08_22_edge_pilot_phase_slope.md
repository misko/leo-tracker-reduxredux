# Edge-pilot phase slope and PNT-like carrier tracking

Date: 2026-08-22

Status: pilot-only phase/Doppler tracker implemented and evaluated; Research-only, not deployed

## Decision

The Qin edge pilots contain usable carrier-frequency information inside each Starlink
frame. The new estimator recovers one frequency slope from all 300 known pilot symbols
and all eight edge subcarriers while treating the phase and channel of every frame as
nuisance parameters. It therefore does **not** require carrier phase to remain continuous
between frames.

Synthetic tests are strong and the first real-dwell result is encouraging: 237 of 240
complete frames preferred the exact Qin sequence over a symbol-rolled control, and the
estimated carrier-frequency rate was within 61.9 Hz/s (0.88%) of the frozen trajectory
model. The estimator did not, however, beat independent GLRT64 CFO against that model on
this interval. It remains a Research observable and is not a Standard replacement or a
trajectory input yet.

The follow-on experiment also tracks a PNT-like state containing carrier phase,
Doppler/CFO, and Doppler/CFO rate. It uses no PNT beacon: every measurement comes from the
same exact Qin edge-pilot wipeoff and rolled-sequence control described below. A dense
pass used all 125 existing timing locks and 1,875 pilot frames. The result is decisive:
under its ordinary unambiguous 2-pi measurement model, phase is coherent locally but not
continuously across the four-second dwell. Only 471 phase updates were accepted, 570
resets were declared, and the longest uninterrupted run of accepted observed frames was
14 frames spanning 22.7 ms. On accepted frequency updates, tracking RMS was 404.5 Hz
versus 398.0 Hz for independent pilot frames and 377.0 Hz for source-window GLRT64. The
tracker is an implemented continuity diagnostic, not a superior Doppler product; the
modulo-pi result below explains one important class of its resets.

The visually smooth 34.73-34.81 s frequency run was also reprocessed as a complete
noncausal batch, including the 11 frame epochs omitted by the retained-lock pass. All 60
frames pass the pilot-quality test and their CFOs fit a smooth curve to 17.8 Hz RMS. The
ordinary phase innovations initially look incompatible at 1.88 rad RMS, but they form two
clear families separated by pi. Doubling phase to remove that binary sign state, fitting
a noncausal cubic, and then resolving the state sequence leaves only 0.151 rad RMS and
0.978 coherent-stack efficiency versus a 0.989 per-frame oracle ceiling. The causal
Kalman filter is therefore rejecting a strong modulo-pi phase observable because its
measurement model assumes one unambiguous 2-pi phase. This is a model failure, not an
absence of coherent signal. An interleaved held-out check confirms it: the even 150 pilot
symbols predict the odd 150 at 0.152 rad RMS and 0.970 stack efficiency; odd predicts even
at 0.164 rad and 0.966; and both halves infer the same 60 binary states up to one global
sign. Out-of-time and out-of-dwell validation is still required before calling this a
navigation-grade carrier lock.

## Introduction

The current receiver obtains coarse and fine carrier frequency from independent GLRT64
acquisitions. That is robust, but it uses only selected acquisition structure and returns
one CFO estimate for a probe. The recently characterized Qin edge pilots provide a second
opportunity: their transmitted complex symbols are known for all 300 OFDM symbols in a
frame, on eight subcarriers at either channel edge. Residual carrier frequency appears as
a common phase ramp across those known symbols.

This work asks whether that ramp can provide a useful frame-rate Doppler observable from
the existing recordings, without assuming the cross-frame phase continuity that the Qin
paper found difficult to model and without changing any persisted analysis contract.

## Problem statement

A direct carrier-phase tracker would normally unwrap phase over time and differentiate it
to estimate Doppler. That is unsafe here. Each frame may start with a different phase, and
each edge subcarrier has its own complex channel response. Connecting those phases can
turn a frame reset, channel change, or receiver discontinuity into a false frequency
excursion.

The desired observable must therefore:

- use the known Qin edge-pilot symbols rather than payload;
- recover frequency from phase evolution **within** one frame;
- tolerate an arbitrary common phase and eight arbitrary complex channel gains per frame;
- provide a matched negative control so structure-free coherence is not mistaken for a
  valid pilot match;
- fail explicitly on short, zero-energy, dropped, or unsupported inputs; and
- remain Research-only until real-corpus accuracy and runtime justify promotion.

Figure 1 shows the distinction. The useful measurement is the slope inside each frame;
the arbitrary phase jump between frames is never joined or unwrapped.

![Frame-local measurement model](figures/2026_08_22_edge_pilot_phase_slope/measurement-model.svg)

*Figure 1. Exact pilot wipeoff exposes a common within-frame phase slope. Separate complex
channel gains absorb subcarrier phase, and every frame is solved independently. The
17-symbol-rolled sequence traverses the same search as a negative control.*

## Approach

For frame \(m\), pilot symbol \(i\), and edge subcarrier \(k\), exact symbol wipeoff gives

\[
z_{m,i,k}=y_{m,i,k}p^*_{i,k}
\approx h_{m,k}\exp\!\left(j2\pi\Delta f_m(t_i-t_\mathrm{ref})\right)+n_{m,i,k}.
\]

Here \(h_{m,k}\) is a separate unknown complex gain for every subcarrier and frame.
Maximizing over those gains leaves the one-dimensional frequency likelihood

\[
\Lambda_m(f)=\sum_k\left|\sum_i z_{m,i,k}
\exp\!\left(-j2\pi f(t_i-t_\mathrm{ref})\right)\right|^2.
\]

The implementation searches \(\Lambda_m\) over a configurable residual-CFO interval
(default \(\pm2\) kHz), refines the maximum with weighted phase regression, and adds that
residual to the acquisition CFO. The same search is repeated after wiping off a
17-symbol-rolled Qin sequence. Exact and control likelihoods are normalized by their
Cauchy ceilings, so their difference is a directly comparable coherence margin.

The result for every complete frame contains:

- residual and absolute CFO;
- an approximate local weighted-fit uncertainty;
- exact coherence, control coherence, and their margin;
- phase residual RMS; and
- a diagnostic phase at the frame reference time.

The diagnostic phase is not an authorization to unwrap between frames. The public result
states `phase_continuity_assumed=False` and the API documentation repeats that constraint.

### PNT-like phase and Doppler state

The tracking extension changes the channel model from an unrelated channel in every
frame to a slowly varying eight-subcarrier channel reference within one locked segment.
Its state is

\[
\mathbf{x}_m=[\theta_m,\dot\theta_m,\ddot\theta_m]^T,
\qquad f_m=\dot\theta_m/(2\pi),
\qquad \dot f_m=\ddot\theta_m/(2\pi).
\]

It propagates the same locally quadratic carrier phase used by Kassas et al. A frame
contributes both its independent phase-slope CFO and a wrapped common-phase measurement
formed by comparing its dechirped eight-subcarrier channel vector with the causal channel
reference. The Kalman innovation wraps only the phase component into `[-pi, pi)`.

An update requires the exact Qin sequence to pass the coherence gates, the channel shape
to remain similar, the frequency innovation to be plausible, and the phase innovation to
remain within 1.2 rad. Two consecutive phase failures declare a reset. A reset starts a
new phase segment while preserving the Doppler and Doppler-rate state. Thus the
implementation tests continuity where supported instead of forcing continuity through a
user, channel, timing, or transmitter phase change.

## Methods

### Implementation boundary

The estimator is implemented in
[`src/leo/analysis/qam/pilot.py`](../src/leo/analysis/qam/pilot.py) as
`analyze_pilot_phase_slope`. It reuses the existing known-pilot demodulator, exports narrow
frozen result dataclasses through `leo.analysis.qam`, and has no storage or service
dependency. No Standard profile, persisted schema, recording, or frozen analysis artifact
was changed.

The PNT-like tracker is implemented in
[`src/leo/analysis/qam/tracking.py`](../src/leo/analysis/qam/tracking.py) as
`analyze_pilot_phase_doppler_tracking`. It consumes the same demodulated Qin pilot cube,
frequency likelihood, exact coherence, and rolled-control coherence as the frame-local
estimator. It does not import, correlate, synthesize, or claim the PNT paper's central
beacon or pseudorange observable.

One complete frame contributes 2,400 known complex observations: 300 pilot symbols times
eight subcarriers. Frames with a positive exact-minus-control margin contribute to the
aggregate median. A dropped all-zero frame has zero margin and is excluded. The maximum
residual-CFO option is rejected if it exceeds the pilot-symbol-rate Nyquist limit.

### Synthetic qualification design

The focused tests in
[`tests/dsp/test_pilot_phase_slope.py`](../tests/dsp/test_pilot_phase_slope.py) exercise:

1. five independently phased frames with arbitrary complex subcarrier channels, additive
   noise, and residual CFO from -875 to +1,190 Hz;
2. raw-IQ demodulation with independent phase on every frame;
3. a capture made from the rolled sequence, which must make the control win;
4. a dropped zero frame, which must not bias the aggregate;
5. short and zero-energy windows; and
6. rejection of a search interval above the symbol-rate Nyquist limit.

The arbitrary-frame-phase cases are the critical scientific test: frequency must remain
correct even though the phases cannot be connected.

The tracking tests in
[`tests/dsp/test_pilot_phase_doppler_tracking.py`](../tests/dsp/test_pilot_phase_doppler_tracking.py)
add continuous quadratic carrier phase, injected Doppler rate, additive noise, a persistent
`pi/2` phase reset, a one-frame dropout, a ten-frame gap, and the rolled-sequence null. The
required behavior is explicit: continuous cases retain one phase segment; the `pi/2` step
starts a new segment without discarding Doppler; one missing frame coasts; a long gap
reacquires; and the rolled sequence cannot initialize the tracker.

### Real-dwell selection and reference

The real-data evaluation used the ordinary read-only recording corpus:

- session `cap-20260821T140820-470384cc9284`;
- `stream-0`, RX0, upper channel edge (`radio_pluto_5d4d`);
- 2.5 MS/s sample rate;
- signal interval 33.7-37.7 s; and
- frozen final trajectory branch prefix `sha256:5852a936` from the Standard analysis root
  ending in `sha256:ccdc4b152617f6e99b23044948cea7be040905cf1e7dd074bb36668b36dc0963`.

Candidate probes came from Standard detections with GLRT64 margin at least 0.05. At each
time, the candidate nearest the frozen trajectory was selected, subject to a maximum
2.5 kHz model difference. Every eighth accepted probe was evaluated, yielding 16 probes
and 240 complete frames across four seconds. This sparse protocol was chosen before
looking at phase-slope performance; it limits repeated adjacent samples while spanning
the observed frequency evolution.

The frozen trajectory is a consistency reference, not carrier-frequency ground truth.
Its residual includes model, calibration, and front-end effects, so all reported errors
must be read as *difference from that frozen model*.

### Paper alignment

Qin et al., *Pilots and Other Predictable Elements of the Starlink Ku-Band Downlink*,
establish the exact edge-pilot structure used here and report that inter-frame carrier
phase discontinuities resist simple modeling. That evidence motivates the frame-local
design and the refusal to unwrap the diagnostic phases.

Kassas et al., *Unveiling Starlink for PNT*, use carrier phase internally in a tracking
state containing phase, frequency, and frequency rate; their final navigation solve uses
Doppler and pseudorange-rate observables. Their central unmodulated pilot tones are not
the Qin edge pilots. The transferable idea is to use coherent phase evolution to sharpen
frequency/frequency-rate estimation, not to equate the two signals or copy a
cross-frame-continuity assumption.

## Results

### Synthetic results

All focused scientific cases passed. With arbitrary frame phase and arbitrary subcarrier
channel, the pure frame-cube kernel recovered every injected CFO to within 2 Hz; its
estimated uncertainty was below 1 Hz, exact-minus-control margin exceeded 0.98, and phase
residual RMS stayed below 0.03 rad. The raw-IQ case recovered four independently phased
frames to within 0.3 Hz. In the rolled-sequence negative control, exact coherence stayed
below 0.01 while control coherence exceeded 0.97. The deliberately dropped frame had zero
margin and did not enter the aggregate.

These are deterministic qualification cases, not estimates of field accuracy. Their role
is to show that the algorithm recovers the intended observable and rejects its named
control under controlled conditions.

### Real 20 ms anchor

The first 20 ms probe at 33.7 s used a coarse CFO of 443,503.891 Hz and contained 15
complete frames. All 15 had positive coherence margin. The margin quantiles were 0.116
(p10), 0.128 (median), and 0.137 (p90). Against the frozen model, the frame estimates had
a median error of -321.5 Hz, MAD 13.5 Hz, and RMS 317.3 Hz. The narrow within-probe MAD
shows stable frame-local estimates, while the common offset warns that the local fit
uncertainty does not cover model/acquisition bias.

DSP execution after IQ had been read took 20.39 ms for the probe, or 1.36 ms per complete
frame on this host.

### Four-second sparse validation

Across 16 probes, 237 of 240 complete frames (98.75%) preferred the exact sequence over
the rolled control. Median coherence margin was 0.152 and median approximate local
uncertainty was 16.2 Hz.

The phase-slope estimates differed from the frozen model by 182.6 Hz median, 273.6 Hz MAD,
and 379.0 Hz RMS. Independent GLRT64 on the same selected probes produced 177.4 Hz median,
159.9 Hz MAD, and 347.1 Hz RMS. The phase refinement relative to GLRT64 had 35.9 Hz median,
64.6 Hz MAD, and 140.3 Hz RMS.

The fitted phase-slope carrier-frequency rate was -6,991.5 Hz/s, versus -7,053.4 Hz/s for
the frozen model: a +61.9 Hz/s difference, or 0.88% of the model magnitude. Figure 2 puts
the central field results and their timing scopes side by side.

![Real-dwell results](figures/2026_08_22_edge_pilot_phase_slope/real-dwell-results.svg)

*Figure 2. The exact pilot wins its control on nearly every frame and the four-second
frequency rate agrees closely with the frozen model. Per-probe scatter is not better than
GLRT64, so the evidence supports continued Research use rather than promotion.*

The quantitative record behind the figure is available as
[`metrics.json`](figures/2026_08_22_edge_pilot_phase_slope/metrics.json).

### Pilot-only phase/Doppler tracking result

The initial sparse evaluation restarted the tracker inside 16 separate 20 ms windows. It
was useful for debugging but could not answer the continuity question. The definitive
dense pass therefore used all 125 existing Qin-pilot timing locks before the reporting
stride, exposing 1,875 actual pilot frames over four seconds. Timing was re-anchored from
those existing locks because a single 750 Hz epoch did not survive the gaps. Carrier
phase, CFO, and CFO rate were carried between locks; no frozen trajectory or PNT beacon
steered the Kalman updates. The pre-existing choice of which candidate locks belonged to
this trajectory was nevertheless conditioned by the frozen-model selection gate described
above; the model is also the comparison reference.

Of the 1,875 frames, 1,777 passed the exact-pilot structure gates. Frequency updates were
accepted on 1,109 frames and phase updates on 471. The tracker declared 570 resets and
formed 571 phase segments. The longest uninterrupted run of accepted observed frames was
14 frames spanning 22.7 ms. The widest segment spanned 65.2 ms but contained only 16
accepted phase updates, and the median segment contained zero accepted updates. Because
the accepted locks do not cover every transmitted frame, the 22.7 ms span includes short
unobserved gaps; it is not proof of continuously observed phase throughout that interval.

| Dense accepted-update comparison against frozen model | Median | MAD | RMS |
|---|---:|---:|---:|
| Independent pilot frame | +340.3 Hz | 151.1 Hz | 398.0 Hz |
| Phase + Doppler tracker | +356.9 Hz | 145.5 Hz | 404.5 Hz |
| Source-window GLRT64 | +288.6 Hz | 192.9 Hz | 377.0 Hz |

This denser and fairer comparison reverses the small improvement seen in the sparse
restarted run: tracking increases CFO RMS by 6.5 Hz relative to the independent pilot
measurement. The Doppler-rate state also remains inaccurate, with 4,897.7 Hz/s RMS error
against the frozen model on accepted frequency updates. Frequent phase discontinuities
do not provide enough continuous phase leverage to stabilize rate.

![Pilot-only phase and Doppler tracking](figures/2026_08_22_edge_pilot_phase_slope/phase-doppler-tracking.png)

*Tracking result figure. The 125 timing-locked windows make the sampled bursts explicit
(A). Phase+Doppler tracking does not beat either frequency baseline (B), the rate state
does not converge to the frozen reference (C), and accepted local phase measurements are
interspersed with 570 explicit resets (D).*

### Why the dense frame times are not uniform

“Dense” here means every one of the 15 frame hypotheses inside every accepted acquisition
window, not every transmitted frame on a continuous four-second lattice. The 1,875 points
therefore arrive as 125 short, acquisition-timed bursts. Within each burst the reference
times follow the expected 750 Hz cadence, but the persisted timing-lock scan did not accept
a window at every possible epoch. The 124 gaps between bursts retain that irregular
selection geometry. This is why the independent-frame points in the tracking plot form
vertical-looking clusters separated by blank intervals instead of being uniformly spread
over capture time.

![Dense-pass sampling geometry](figures/2026_08_22_edge_pilot_phase_slope/dense-sampling-geometry.png)

*Dense sampling geometry. Panel A separates requested frames, accepted frequency updates,
accepted phase updates, and declared resets on the same time axis. Panel B distinguishes
the nominal 1.333 ms within-burst spacing from the larger inter-burst gaps. Panel C shows
how many of the 15 requested frames in each acquisition window supported frequency and
phase updates. Raw IQ exists in the blank intervals, but this analysis did not evaluate a
frame there because no retained timing lock supplied an epoch; the blanks are not evidence
of a quiet or incoherent carrier.*

### What the denser pass says about coherent phase

There is a clear phase observable locally: the accepted phase innovations cluster near
zero, with 0.22 rad median absolute innovation and 0.36 rad RMS. It is not a clear global
phase history. Reset-delimited segments usually contain no accepted phase update, and the
longest consecutive sequence contains 14 evaluated frames over 22.7 ms. The widest
segment lasts 65.2 ms but contains only 16 accepted phase updates. Since evaluated frames
can straddle an inter-window gap, elapsed span is an upper bound on continuously observed
coherence; it must not be read as a claim that every intervening transmitted frame was
tracked.

![Phase-coherence segment detail](figures/2026_08_22_edge_pilot_phase_slope/phase-coherence-detail.png)

*Phase-coherence detail. Panels A and B show the population of all 571 reset-delimited
segments, including the large mass at zero accepted updates. Panels C and D zoom into the
strongest consecutive accepted run: its wrapped innovations remain inside the acceptance
gate, while its CFO estimates still share the several-hundred-hertz offset from the frozen
model. This is short-burst carrier coherence, not yet a seconds-long carrier-phase track.*

### Distribution and apparent cadence of coherent-phase runs

Using the stricter definition of a lock run as consecutive accepted evaluated frames gives
273 observed runs. Of these, 175 (64.1%) are singletons and only 98 contain two or more
frames. There are 272 observed run-start intervals: 191 remain inside continuously
evaluated stretches and 81 cross at least one frame-evaluation gap.

Within the continuously evaluated stretches, 92 of 191 run-start intervals (48.2%) are
two nominal frame periods, or 2.667 ms; another 49 (25.7%) are three frame periods, or
4.000 ms. This is an apparent cadence, but it is not evidence of a physical oscillator or
channel process at 375 Hz or 250 Hz. A run is split by a rejected evaluated frame, all
observations lie on the 750 Hz frame grid, and the tracker explicitly resets after repeated
gate failures or an expired coast. The quantization is therefore expected from the
observation and state-machine definitions. Intervals crossing missing coverage have a
separate, much broader distribution and cannot reveal when the physical phase lock was
actually lost or recovered.

![Observed phase-lock timing distribution](figures/2026_08_22_edge_pilot_phase_slope/phase-lock-timing-distribution.png)

*Observed lock timing and cadence. Panel A places every accepted run in time and exposes
its measured duration and median pilot quality. Panel B shows that single-frame runs
dominate. Panel C shows the frame-grid quantization inside sampled stretches. Panel D
separates those intervals from the 81 intervals censored by missing acquisition coverage.
The present data support an algorithmic/evaluation cadence, not a fixed physical relock
rate.*

The missing information matters. A physical lock-rate claim requires continuously
evaluating every frame over a retained interval, preserving rejected as well as accepted
pilot statistics, and then repeating the analysis with tracker reset/coast thresholds
varied. Without that experiment, physical coherence, acquisition availability, and the
tracker state machine are not identifiable from one another.

### Correcting and controlling for probe quality within a lock run

A common phase rotation does not change the existing single-frame exact-pilot coherence
score, so phase correction cannot improve that metric inside one frame. It can improve
coherent combination across frames. For each of the 98 multi-frame runs, the analysis now
reconstructs the eight-subcarrier channel vector and compares three stacks:

1. no inter-frame phase correction;
2. causal derotation from the carrier state predicted before the current frame update;
3. independent self-alignment from the current frame itself, used only as an optimistic
   ceiling.

The causal correction raises median normalized channel-stack efficiency from 0.444 to
0.861; the self-aligned ceiling is 0.939. Expressed as effective coherent gain relative to
one frame, the medians are -0.15 dB uncorrected, +2.61 dB with the causal tracker, and
+2.81 dB for the self-aligned ceiling. The causal correction improves 86 of the 98
multi-frame runs (87.8%), with a median +2.90 dB improvement over the uncorrected stack.

![Phase-corrected probe quality](figures/2026_08_22_edge_pilot_phase_slope/phase-lock-quality-correction.png)

*Phase correction and probe combination. Panel A controls visually for median exact-pilot
coherence while showing interval duration. Panel B compares uncorrected and causally
phase-corrected stack efficiency. Panel C gives the complete multi-run gain distribution,
and panel D plots the correction gain against interval signal quality. Exact-pilot
coherence has only a weak association with observed run length in this selected sample
(Pearson r = -0.10), so ordinary probe quality does not explain the duration pattern.*

This is useful evidence that the tracked phase can align probes already classified as
locked. It is not an independent SNR or payload-quality validation: the run selection and
channel vectors both use the known Qin pilot, the quality range is truncated by the
selection gates, and 175 singleton runs offer no combining opportunity. A held-out test
should estimate phase from one pilot subset and score a disjoint following subset before
using the gain as a calibrated signal-quality improvement.

### Six zoomed frequency runs with explicit phase status

The full-dwell CFO panel makes the frequency-supported streaks look longer and more
uniform than their phase support. The six zooms below retain the same independent and
tracked CFO residuals but add phase status directly: green rings are accepted phase
updates, red crosses are rejected phase updates, red open circles are resets, green bands
are strict multi-frame phase runs with no missing frame interval, and hatched bands are
raw-IQ intervals that were not evaluated because no retained timing lock supplied frame
epochs.

![Six frequency-run phase zooms](figures/2026_08_22_edge_pilot_phase_slope/frequency-run-phase-zoom-six.png)

*Six representative frequency runs. Run 2 is phase locked across 13 of 14 frames for a
strict 16.0 ms interval. Run 3 and run 5 contain genuine local phase locks but are
fragmented across their complete frequency streaks. Runs 9, 20, and 31 retain smooth CFO
behavior without a sustained strict phase lock. The repeated diagonal CFO geometry is
therefore not sufficient evidence of carrier-phase continuity.*

### Requested zooms and sensitivity to the phase-lock thresholds

The hatched regions in these figures were previously called “unsampled.” That wording was
too strong: the recording contains continuous raw IQ. They are **not evaluated** by this
dense pass because the retained acquisition results did not supply a pilot-frame epoch in
those intervals. No conclusion about phase coherence can be drawn inside a hatched band
without generating and validating additional timing hypotheses.

The causal phase-update decision combines several gates: supported exact-over-control
pilot structure, an accepted frequency innovation, no expired 12 ms phase coast, channel
similarity above threshold, and wrapped phase innovation inside threshold. A reset is
declared after two supported phase failures. The current research defaults are channel
similarity >= 0.65 and absolute phase innovation <= 1.2 rad. These are engineering choices,
not a calibrated physical boundary. The figure therefore reruns the complete causal
tracker with three configurations rather than merely recoloring one result:

| Configuration | Channel similarity | Absolute innovation |
|---|---:|---:|
| Strict | >= 0.80 | <= 0.6 rad |
| Current | >= 0.65 | <= 1.2 rad |
| Lenient | >= 0.50 | <= 2.0 rad |

![Threshold-sensitive phase-lock zooms](figures/2026_08_22_edge_pilot_phase_slope/phase-threshold-zoom-two.png)

*Threshold sensitivity in the requested intervals. In 34.08-34.18 s, the strict tracker
accepts 34/60 evaluated frames and finds at most 6 consecutive frames over 6.7 ms; the
current tracker accepts 45/60 and finds 12 frames over 14.7 ms; the lenient result changes
only to 46/60 and the same 12-frame maximum. This supports genuine local phase-coherent
islands, but the evaluation gaps prevent claiming one continuous 100 ms lock. In
34.73-34.81 s, strict/current/lenient accept 13/15/16 of 49 frames respectively, yet every
configuration has the same maximum of only 2 consecutive frames over 1.3 ms. The absence
of sustained lock there is robust to this threshold range.*

A phase lock in this analysis therefore looks like a sequence of green innovations near
zero, with no intervening rejection, reset, or frame-evaluation gap. The thresholds decide
how much prediction error and channel change are tolerated, while the consecutive-frame
requirement tests continuity. Promotion would require calibrating those tolerances against
held-out phase prediction or independent truth, not treating the current defaults as a
physical constant.

### Offline audit of the apparently smooth 34.73-34.81 s run

The top-left CFO streak is visually persuasive, but it plots **frequency**, not carrier
phase. A small frequency error integrates rapidly: at the 750 Hz frame rate, a 100 Hz
CFO error produces 0.84 rad of phase error by the next frame. Smooth per-frame slopes are
therefore necessary but not sufficient for a cross-frame phase lock.

This interval was rerun without the online constraint. The retained frame starts lie on
one 750 Hz lattice, with at most a one-sample re-anchoring difference between acquisition
windows. That lattice supplies 60 consecutive hypotheses from 34.7300 through 34.8087 s:
49 correspond to retained timing locks and 11 fill the formerly hatched gaps directly
from the continuously recorded IQ. Every one of the 60 frames passes exact-over-control
pilot quality. The median within-frame phase residual is 0.70 rad, the median local CFO
uncertainty is 18.7 Hz, and a robust quadratic CFO curve fits the independent frame
slopes to 17.8 Hz RMS.

The offline phase extraction then removes a separate fractional-delay ramp across the
eight subcarriers in every frame before evaluating the common carrier phase. The fitted
delays follow the expected approximately -1/3, 0, +1/3 sample rounding pattern; after
correction the median channel-vector similarity is 0.990. Thus neither missing IQ,
integer frame timing, nor a changing eight-tone channel explains the rejected phase
updates.

![Offline phase-continuity audit](figures/2026_08_22_edge_pilot_phase_slope/offline-phase-continuity-audit.png)

*The 34.73-34.81 s interval on a complete 750 Hz lattice. Panel A confirms that both the
retained and newly evaluated frames carry the same smooth CFO trend. Panel B shows that
an ordinary 2-pi cubic fit leaves broad residuals while a cubic fit to doubled phase
collapses them near zero. Panel C exposes the two ordinary phase-increment families and
their collapse after resolving the pi state and a common 38.4 Hz correction. Panel D
shows coherent combining: raw, CFO-only, and ordinary cubic correction reach only
0.07-0.11 efficiency; the conservative held-out binary-pi result reaches 0.966 (0.978
when fit and scored on all pilots) against a 0.989 independently aligned per-frame
ceiling.*

The causal result on the 49 previously evaluated epochs was 15 accepted phase updates,
17 resets, and a longest strict run of two frames. The offline results show why relaxing
the Kalman gates did not repair it, and why a different observation model does:

- ordinary adjacent innovations are 1.880 rad RMS, but modulo pi they share a 0.322 rad
  circular center, equivalent to a 38.4 Hz common CFO correction;
- after removing that center and the nearest pi state, adjacent innovation RMS is 0.227
  rad;
- an ordinary noncausal cubic still fails at 1.695 rad RMS and 0.095 stack efficiency,
  and a degree-8 fit improves only to 1.521 rad and 0.249;
- the doubled-phase cubic plus binary-state reconstruction reaches 0.151 rad RMS and
  0.978 efficiency, nearly the 0.989 per-frame nuisance ceiling; and
- the inferred binary state changes 21 times over 59 frame boundaries. It is observable,
  but neither rare nor yet tied to a documented transmitter rule.

The disjoint-symbol validation is equally important. Fitting frequency, smooth doubled
phase, fractional timing, and all binary states from the even pilot symbols predicts the
odd symbols with 0.152 rad RMS and 0.970 stack efficiency. Reversing the halves gives
0.164 rad and 0.966. The independently inferred state sequences agree on every frame up
to the unavoidable single global sign. Only one global carrier-phase offset is fit when
scoring each held-out half; there is no held-out per-frame phase adjustment.

An ordinary integer-cycle Viterbi decoder cannot fix this because adding 2-pi does not
change the wrapped innovation. A **half-cycle** decoder can. The strongest next offline
method is therefore a hybrid factor graph or Viterbi smoother with continuous
phase/frequency/rate states and one discrete {0, pi} state per frame. Phase doubling gives
a robust initialization; the independent within-frame slopes constrain rate; fractional
delay and the eight-tone channel remain nuisance states; and forward/backward smoothing
resolves the binary sequence. This interval strongly supports that method.

The first independence test therefore passes. The remaining scientific test is
out-of-time prediction: freeze the model and binary-state transition law, predict the next
frame, then repeat across receivers, edges, and dwells and check whether the binary state
follows a reproducible signal rule. Until that passes, the result is best described as an
80 ms phase lock **modulo pi**, not an unambiguous 2-pi carrier-phase lock.

### Measured-data figure walkthrough

The aggregate comparison above hides the signal-processing geometry. Figures 3-7 return
to the measured RX0 IQ and then move progressively through raw spectrum, frame-local
phase, window alignment, and residual/control diagnostics. Five PNGs use the preregistered
16-window sparse selection; the seven dense tracking PNGs use all 125 pre-stride timing
locks, and the additional offline PNG uses the complete inferred lattice in the requested
34.73-34.81 s interval.

![Raw measured IQ context](figures/2026_08_22_edge_pilot_phase_slope/raw-iq-context.png)

*Figure 3. Raw RX0 IQ over the complete 2.5 MHz capture band (top) and a zoom around the
tracked carrier (bottom). The ordinary FFT view has no clean narrow carrier ridge; the
trajectory and estimator marks are overlays. This is why exact known-symbol correlation,
rather than visual peak following, is needed to recover the pilot phase observable.*

The white triangles mark the 16 windows selected only after the persisted GLRT64 margin
and frozen-model gates were applied. The phase-slope result does not create or move those
windows. In the zoom, the GLRT64 and phase aggregates sit close to the same declining
trajectory even though the raw spectral texture alone does not isolate it.

![Anchor phase evolution](figures/2026_08_22_edge_pilot_phase_slope/anchor-phase-evolution.png)

*Figure 4. The 15 frames in the 33.700 s anchor window. The top panel shows independent
wrapped diagnostic phases and intentionally draws no line between them. The lower panels
show measured exact-wiped pilot phase from four frames and each frame's independent
frequency-slope fit.*

The lower observations are circular phase values lifted onto the branch nearest their own
frame-local fit. This is a display operation inside one frame, not an unwrap between
frames. It avoids rendering a low-weight symbol near the +/-pi boundary as a false 2-pi
jump. The dense central clouds follow their fitted slopes; scattered points farther away
are retained rather than hidden. The displayed phase-residual RMS is 0.65-0.75 rad for
these four examples.

![One phase fit per selected window](figures/2026_08_22_edge_pilot_phase_slope/window-phase-gallery.png)

*Figure 5. One control-supported representative frame from every selected 20 ms window.
Blue points are measured circular pilot phase after exact wipeoff and per-frame channel
combining; amber lines are independent fits. Titles report the residual correction to
GLRT64, exact-minus-control margin, and circular phase-residual RMS.*

The gallery is deliberately exhaustive over the 16 selected windows rather than a set of
best-looking examples. Residual corrections change sign and magnitude as expected for a
local refinement. Every representative frame has a positive control margin, while the
phase scatter makes clear why the local curvature uncertainty must not be interpreted as
calibrated end-to-end frequency error.

![Window-by-window CFO alignment](figures/2026_08_22_edge_pilot_phase_slope/window-alignment.png)

*Figure 6. Absolute CFO, aggregate residual, and the complete 15-frame distribution for
each window. The boxes expose windows whose individual frame estimates are tight as well
as windows with broad or asymmetric residuals; amber points are medians of only the
frames supported by the exact-over-control test.*

The top panel makes the useful result visible: all 240 frame-local estimates follow the
same four-second carrier trend. The lower panels also preserve the negative result. Phase
refinement sometimes moves GLRT64 toward the frozen model and sometimes away from it, so
there is no uniform accuracy improvement on this dwell.

![Residual and control diagnostics](figures/2026_08_22_edge_pilot_phase_slope/residual-diagnostics.png)

*Figure 7. Window-error ECDFs, phase-versus-GLRT residual changes, exact/control
coherence, and all 72,000 circular symbol residuals (240 frames times 300 symbols). Thin
horizontal lines in the heatmap separate the 16 windows.*

The ECDF restates the field-accuracy decision without reducing it to one number: GLRT64
has the narrower residual distribution on this interval. The exact/control panel shows
why the phase observable is nevertheless credible: 237 frames form a high-exact,
near-zero-control column, while the three unsupported frames lie near the origin rather
than masquerading as strong control detections. The residual heatmap shows structured
frame-to-frame quality variation but no cross-frame phase connection is used.

The per-window/per-frame values and SHA-256 digest of every PNG are retained in
[`detailed-results.json`](figures/2026_08_22_edge_pilot_phase_slope/detailed-results.json).

## Interpretation

Three conclusions are supported.

First, phase helps because frequency is the slope of phase. Three hundred known symbols
provide many coherent time samples inside a frame, so the estimator uses far more than a
single phase value. It does not obtain Doppler by comparing absolute phase between frames.

Second, the Qin correspondence is explicit: the received symbols are wiped with the exact
known Qin sequence, and that result is required to beat an identically processed rolled
sequence. The satellite/trajectory correspondence is a separate downstream association
problem. In this experiment it came from the pre-existing frozen Standard trajectory,
not from carrier phase alone and not from Doppler rate alone.

Third, the result is promising but not yet superior. Rate agreement and control
separation show real signal content; the larger MAD and RMS than GLRT64 show that this
implementation is not ready to replace independent CFO acquisition. A useful next role
may be as additional likelihood evidence or a locally smoothed frequency-rate observable,
provided that evaluation remains frame-local and uses held-out tracks.

Fourth, phase can be tracked in short coherent segments, but the real dwell does not
support a single carrier-phase history. The dense pass accepted 471 phase updates but
required 570 resets; no uninterrupted run of accepted observed frames exceeded 22.7 ms.
The current result is a useful discontinuity measurement, not Doppler improvement or a
validated carrier-phase navigation observable.

## Runtime and operational consequence

The 1.36 ms/frame number measures the estimator after IQ read. The 16.77 ms/frame number
from the sparse run includes independent verified corpus reads and must not be interpreted
as DSP cost. The 20.39 ms anchor-probe total is close to its 20 ms observation span, so the
Python implementation is approximately real-time on one core but has insufficient
production headroom once scheduling, acquisition, storage, and other analysis are added.

The dense locked-frame tracker processed 1,875 requested frames in 1.437 s after IQ read,
or 0.766 ms per requested frame on this host. This is an offline batch measurement; it
does not include acquisition, timing-lock generation, verified storage read, or service
scheduling.

Promotion would require batching or a native kernel, then a benchmark in the intended
pipeline. The current Research API adds no service or recording overhead unless called.

## Limitations

- The real-data sample is one receiver path and four seconds of one dwell.
- The frozen trajectory is a reference, not RF truth; field error cannot be calibrated
  from this comparison alone.
- The reported ~16 Hz uncertainty is local weighted phase-fit curvature. It excludes
  acquisition bias, trajectory error, oscillator drift, calibration error, and model
  mismatch, and is not a calibrated one-sigma field uncertainty.
- Positive exact-minus-control margin is evidence for the named pilot structure, not an
  independently calibrated detection probability.
- Phase at the reference time is diagnostic only. This work neither proves nor assumes
  global cross-frame phase continuity; the tracker tests it locally and labels resets.
- The dense tracking evaluation carries carrier state across all 125 existing pilot
  locks, but timing is re-anchored at each lock. It does not yet estimate the PNT paper's
  code/frame phase and rate as additional Kalman states.
- The complete-lattice offline audit covers one requested 80 ms interval. It establishes
  a strong modulo-pi phase trajectory there, but does not identify whether the binary
  state is set by transmitter framing, precoding, an unmodeled deterministic signal law,
  or propagation. Its held-out validation is interleaved within the same frames and
  capture; it is not an out-of-time or independent-dwell test.
- The default residual search is limited to +/-2 kHz and depends on a sufficiently close
  acquisition CFO.
- No live RF, hardware capture, Standard artifact, or persisted public contract was
  changed by this work.

## Testing and qualification

After rebasing onto `origin/main` at `20a1130`, the focused DSP and analysis plan passed:

```text
98 passed, 2 deselected in 2.72s
```

Command:

```bash
.venv/bin/python -m pytest -q tests/dsp -m 'not real_corpus' \
  tests/analysis/test_pilot_trajectory_bank.py \
  tests/analysis/test_standard_performance_equivalence.py \
  tests/analysis/test_compare_edge_pilot_methods_tool.py
```

The phase/Doppler extension and complete DSP package then passed its focused plan:

```text
44 passed, 2 deselected in 1.28s
```

Command:

```bash
uv run pytest -q tests/dsp -m 'not real_corpus' \
  tests/analysis/test_edge_pilot_phase_slope_report_tool.py
```

The full ordinary plan also passed:

```text
1423 passed, 162 deselected, 1 warning in 91.59s
```

Command:

```bash
.venv/bin/python -m pytest -q -m 'not real_corpus and not postgres'
```

Mypy for the QAM package, Ruff, formatting, and the diff check passed. Two protected
`real_corpus` tests could not start because user `mouse9911` does not have the `leo` group
permission required for `/srv/bulk/leo/test-corpus`; this is an access-controlled test
skip condition, not a scientific test failure. The separate ordinary recording corpus
used for the read-only dwell evaluation was accessible.

The retained measured-data figure tool has focused tests for the selection order and the
frame-local circular-phase display, phase-run splitting, and reset-segment grouping. The
three focused estimator/report modules passed after regenerating the dense and offline
figures. The report-tool tests include a complete-lattice synthetic continuous-carrier
case with injected binary pi states, wrapped batch fitting, interleaved held-out
prediction, phase doubling, and fractional-timing factorization:

```text
22 passed in 0.99s
```

Run them with:

```bash
.venv/bin/python -m pytest -q \
  tests/analysis/test_edge_pilot_phase_slope_report_tool.py \
  tests/dsp/test_pilot_phase_slope.py \
  tests/dsp/test_pilot_phase_doppler_tracking.py
```

## Reproducibility and next gates

The original frame-local estimator implementation commit is
`fe22a71e873d3d40d76eaeb50e93db2a6feda604`. The dense PNT-like tracking extension,
synthetic fixtures, selection protocol, input identity, frozen reference identity,
measured aggregates, and timing scopes are recorded in this worktree and must be committed
together. The original real-dwell selection was run interactively. It is now retained as
[`tools/report_edge_pilot_phase_slope_figures.py`](../tools/report_edge_pilot_phase_slope_figures.py),
which repeats selection from the frozen products before opening IQ, performs one bounded
digest-verified read, reruns all 240 frame estimates plus the phase/Doppler tracker, and
emits the detailed JSON and thirteen PNGs:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python tools/report_edge_pilot_phase_slope_figures.py
```

Before any Standard or trajectory use:

1. run held-out multi-dwell, multi-radio evaluation with predeclared gates;
2. separate acquisition/model bias from frame-local estimator variance;
3. add and qualify explicit frame/code timing and timing-rate states instead of depending
   on acquisition re-anchors;
4. calibrate the coherence margin and uncertainty against nulls and independent truth;
5. batch or move the likelihood kernel native and remeasure end-to-end latency; and
6. require an explicit scientific review before changing any persisted contract.

## Sub-second raw-lattice follow-up

The subsequent complete-lattice and multi-dwell analysis is reported in
[`2026_08_22_subsecond_pilot_structure.md`](2026_08_22_subsecond_pilot_structure.md).
It recovers the 11 previously unevaluated raw frames in 34.73–34.81 s, resolves the
binary-pi phase ambiguity, audits all 34 contiguous frequency-update runs, and shows that
a 10 ms offline local-linear CFO model reaches 16.48 Hz interleaved held-out RMS. It also
documents the negative result: full phase qualification does not generalize to every
independent dwell, so phase remains a segmented Research observable.
