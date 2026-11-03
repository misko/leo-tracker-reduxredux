# Sequence-assisted frequency prototype

Frozen before the first run. This is a bounded raw-IQ replay, not a position
fit, new collection, or absolute Doppler/timing validation.

Inputs: cached S02 (DS7, 5 MS/s), S13 (DS8, 10 MS/s), and DS9-middle
(10 MS/s), both RXs, first twelve complete frames each. These previously
examined excerpts are convenience samples, not a representative blind corpus.
Verify each original excerpt digest. Reuse only the numerical FFT demodulator,
published pilot/template references and carrier indexing; do not reuse corrected
soft symbols or fitted per-frame trends. Cached acquisition epoch/CFO initialize
the replay, so this remains acquisition-assisted.

Symbols 22–121 initialize residual frequency from pilots. Symbols 142–181
select one of the frozen 60 generated states using non-pilot correlations.
Symbols 182–221 fit each estimator; 222–301 evaluate without refitting.
Every arm has the same fitting times. Each carrier has one static complex gain.
Fit residual frequency and differential phase timing drift (ppm) jointly;
absolute timing is unidentifiable with these free channel phases and is not claimed.
The ppm term describes a frequency-dependent phase drift, not calibrated oscillator truth.

Arms: pilot-only; pilots plus predicted sequence; pilots plus state k+1 control.
All arms predict the same held pilots and tail samples. For pilot-only, extra
carrier gains are estimated on the fitting samples with frequency/drift frozen.
State-selection coherence and initialization-pilot coherence above 0.5 define
a training-only qualified subset. Preserve all rows and report subset coverage.
No results-based changes to these thresholds, split, or membership.

Synthetic tests check signed frequency/clock recovery, gain nuisance terms,
wrong-sequence rejection, and held-sample isolation. An injected frequency and
clock ramp on each real symbol matrix checks equivariance, not absolute accuracy
or RF intercarrier interference. Report paired held normalized squared errors,
frequency changes, boundary solutions and results per dataset/RX.
No geography evaluation unless this first assay justifies it.
