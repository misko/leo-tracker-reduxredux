# Frozen bounded detection experiment

Preparation amendment before any IQ/outcomes: the first metadata freeze exposed
a missing `window_start_counter` adapter field in all eight slots. Preserve that
attempt as `panel_attempt01.json`/`protocol_attempt01.json`; normalize it directly
from the selected public probe's `valid_start_counter` and refreeze the same visits.

Select DS24-0010 and DS24-0011 from the pre-existing 2026-10-24 DS24 analysis inventory, with
CH1/4 controls and CH7/8. For each channel choose the physical visit whose sample
counter is nearest the full processed-scan midpoint; visit breaks ties. Include
both native RX0/1. Selection uses no candidate, detection, GPS, orbit or position
outcome. Missing channel/RX slots remain explicit. Freeze panel and metadata
before reading IQ or generating numerical outcomes.

Read each selected window through the historical public FastSegmentSource and
exhaust its iterator. Verify full paired exported candidate parity against the
unmodified historical runtime, including rank/timing/CFO/scores/gates at existing
replay tolerances. An initial one-window parity timing probe fixes batch feasibility;
it does not change the declared panel/grid. Every process has a 580-second alarm,
one BLAS thread, no RF collection and no raw IQ copies.

Independently synthesize the published analytic eight-tone pilot from its public
state constants: exact symbol boundaries, continuous time per frame, phase per
tone after CP, 750-Hz repetition; do not tile the rounded sampled production
template. Fixed epoch 4321.25 native samples; fixed CFO +213456.75 Hz, flat unit
tone channel, phase 0.37 radians. Inject at mean full-window pilot power / measured
full-window native background complex power = [-24,-18,-12,-6] dB. The same clean
waveform and strength ratios apply to every RX/channel. Baseline is zero injection.
These are pilot-to-recorded-background ratios, not physical antenna-input SNR.
Recorded backgrounds may already contain pilots; unclaimed detections are not
automatically false alarms. Keep float native ADC units for addition (no clipping
or new quantization); production receives complex64 as usual.

Run the complete historical production blind search at every strength on both
receivers. On the identical injected vector, also evaluate public conditioned
GLRT64 at the exactly known fractional timing and CFO, with unchanged >=0.025
margin gate. This is an oracle-anchor diagnostic, not a proposed operational gate.
Blind recovery requires a gate-passing exported candidate within 2 native samples
of injected timing modulo the exact sample_rate/750 frame and <=100 Hz of true
CFO. Record nearest candidate errors even on misses, and all candidate scores.
Anchor support with blind miss isolates acquisition/search loss on this finite
panel; anchor failure is inability of this flat-template scoring lane to separate
the injected signal at that strength/background, not a physical absence claim.

Include independent complex Gaussian background controls on CH1 in each scan
(seed 813260), all four strengths, and wrong-sequence (roll 17) at -6 dB plus
noise-only. Paired controls use independent noise across RX, with the same random
realization held across strengths. Tiny control counts cannot establish a precise
false-alarm rate. Count any gatepass separately from injected-identity recovery.
At high injection a pre-existing signal may be masked or interfere; this is a
superposition experiment. All procedures condition on the existing acquisition and selected
date/windows; no whole-corpus or localization conclusions. No whitening variant.
