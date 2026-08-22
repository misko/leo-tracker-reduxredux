# Frame-local edge-pilot phase-slope Doppler

Date: 2026-08-22

Status: research estimator implemented and qualified on an isolated branch; not deployed

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

## Methods

### Implementation boundary

The estimator is implemented in
[`src/leo/analysis/qam/pilot.py`](../src/leo/analysis/qam/pilot.py) as
`analyze_pilot_phase_slope`. It reuses the existing known-pilot demodulator, exports narrow
frozen result dataclasses through `leo.analysis.qam`, and has no storage or service
dependency. No Standard profile, persisted schema, recording, or frozen analysis artifact
was changed.

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

### Measured-data figure walkthrough

The aggregate comparison above hides the signal-processing geometry. Figures 3-7 return
to the measured RX0 IQ and then move progressively through raw spectrum, frame-local
phase, window alignment, and residual/control diagnostics. All five PNGs are generated
from the same preregistered 16-window selection used for the reported statistics.

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

## Runtime and operational consequence

The 1.36 ms/frame number measures the estimator after IQ read. The 16.77 ms/frame number
from the sparse run includes independent verified corpus reads and must not be interpreted
as DSP cost. The 20.39 ms anchor-probe total is close to its 20 ms observation span, so the
Python implementation is approximately real-time on one core but has insufficient
production headroom once scheduling, acquisition, storage, and other analysis are added.

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
  cross-frame phase continuity.
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

The full ordinary plan also passed:

```text
1414 passed, 162 deselected, 1 warning in 99.65s
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
frame-local circular-phase display. Run together with the estimator tests:

```bash
.venv/bin/python -m pytest -q \
  tests/analysis/test_edge_pilot_phase_slope_report_tool.py \
  tests/dsp/test_pilot_phase_slope.py
```

## Reproducibility and next gates

The implementation commit is `fe22a71e873d3d40d76eaeb50e93db2a6feda604`. The code,
synthetic fixtures, selection protocol, input identity, frozen reference identity,
measured aggregates, and timing scopes are recorded above. The original real-dwell
selection was run interactively. It is now retained as
[`tools/report_edge_pilot_phase_slope_figures.py`](../tools/report_edge_pilot_phase_slope_figures.py),
which repeats selection from the frozen products before opening IQ, performs one bounded
digest-verified read, reruns all 240 frame estimates, and emits the detailed JSON and five
PNGs:

```bash
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  .venv/bin/python tools/report_edge_pilot_phase_slope_figures.py
```

Before any Standard or trajectory use:

1. run held-out multi-dwell, multi-radio evaluation with predeclared gates;
2. separate acquisition/model bias from frame-local estimator variance;
3. test whether robust temporal fitting improves rate without silently connecting phase;
4. calibrate the coherence margin and uncertainty against nulls and independent truth;
5. batch or move the likelihood kernel native and remeasure end-to-end latency; and
6. require an explicit scientific review before changing any persisted contract.
