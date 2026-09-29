# First/last-window interpolation experiment

Goal: replace nine of eleven full window acquisitions per receiver with
endpoint-informed local GLRT evaluations, without changing the standard
analysis pipeline's individual-positive-hit denominator.

Use saved 120 ms dual-RX dwells only, all 22 receiver-windows accounted for.
Run actual full timing/frequency discovery with the frozen boundary-fallback
method on window 0 and window 10 for each receiver. No baseline coordinates
or baseline scores may seed the implementation. Baseline is evaluation only.
This requires the complete dwell and is not causal with respect to its middle
windows; there is no dependence on any later dwell.

Associate endpoint candidates one-to-one using an 8-sample circular timing
gate with the physical rate/750 frame period and an 8 kHz tracking-CFO gate.
Use all endpoint candidate entries, including weak/negative entries that may
become positive later. Preserve candidate multiplicity. Interpolate tracking
CFO and unwrapped timing phase; translate phase into each window's coordinate
system. Recompute current-IQ GLRT for each predicted timing +/-1 integer
sample, retaining the best result per seed. Do not interpolate GLRT scores.
Clamp the initial GLRT acquired-CFO input to its supported +/-400 kHz range
while retaining the unclamped tracking prediction in metadata. The GLRT's
residual estimate then determines the final tracking CFO; do not discard an
otherwise valid endpoint track just because its residual put it outside the
acquisition-input range.

Fixed modes, selected before reading the experiment results:

- `pairs-only`: matched endpoint hypotheses only.
- `union`: also propagate each unmatched endpoint hypothesis with constant
  frequency and phase (no unsupported drift estimate), up to 16 hypotheses.
- `union-fallback`: the union mode, followed by full blind search in a middle
  receiver-window if the local evaluations produce no positive candidate.
  Charge every failed local attempt as well as fallback CPU and kernel calls.

The first cohort is the existing metadata-selected DS7 32-dwell panel covering
all four rates and both edges (704 windows, 843 standard positive entries).
That is development evidence, not all DS7. Expand a promising mode onto the
existing 704-dwell cohort. Time a bounded physical-ARM subset using saved IQ
resident in RAM. No radio collection or concurrent capture in this iteration.

Primary metrics: standard positive entries recovered one-to-one within the
same receiver/window and within 2 samples and 8 kHz; unmatched positives;
positive windows; original windows executed; all GLRT kernel attempts; full
search counts; ARM CPU per complete dwell. Do not substitute endpoint
association, frequency coverage or confirmation counts for recovered hits.
Report the 2.5 MS/s subset separately and include cold endpoint searches in
every dwell's CPU total. The full-search reference for quality is always the
standard pipeline, even though endpoints use its qualified fast approximation.
