# What a scope64 frequency repair would and would not change

This source review precedes the new numerical outcomes. It inspects the frozen
deployed source at `/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src`.
The original implementation identity is
`sha256:124afbbc81870a4079b272bd828d4a99f716e54624a073d9cb13acc2a1b7fe16`.
No deployed source is edited.

`scanner/fast_scan_analysis.py::production_glrt` calls the dwell detector with
eight retained acquisition candidates, a fractional margin threshold of 0.025,
and 20 ms physical windows. `scanner/fast_scan_detector.py::_evaluate_probe`
calls `acquire_symbolwise`, then integer and fractional scope64 scoring at each
retained acquired CFO. Candidate selection is a separate operation from CFO
refinement and should remain fixed in the primary comparison.

The configured acquisition defaults include a 500 Hz fine grid followed by
quadratic interpolation and a 100 Hz conditioned grid around that interpolation.
`analysis/starlink/acquisition.py::acquire_symbolwise` returns that acquired
CFO. Its native helper accelerates coarse anchor evaluation; a different native
detector implementation must not silently replace this public path.

`analysis/starlink/fast_scan_scores.py` forms per-frame, per-symbol correlations.
Its GLRT accumulates squared coherent magnitude across frames, using symbols
2 through 65 and a 512-bin residual-frequency grid. The nominal spacing is
1/(512 * 4.4 microseconds), or approximately 443.892 Hz. The returned tracking
CFO is acquired CFO plus the selected grid residual. This is not simple
quantization of the final CFO because the acquired component is interpolated.
It can nevertheless preserve acquisition interpolation errors when the selected
residual bin is zero. Attribution from the saved single-source outputs must
establish whether this is what actually happens in that control.

A continuous local maximum of the **same fixed-candidate correlation score**
would isolate residual-frequency discretization from changing pilot aperture,
epoch, source count or graph ownership. Let z[f,s] denote the already computed
complex symbol correlations for frame f and symbol s. The relevant numerator
is sum_f |sum_s z[f,s] exp(-i 2 pi delta_f t[f,s])|^2; its normalization must
match the deployed coherent ceiling. The sampled version must reproduce the
actual FFT score before a continuous comparison is interpreted. Include actual
symbol support and timing conventions, rather than inventing uniformly spaced
raw samples. Independent control-template normalization and maxima retain their
original role.

This score's continuous extension is still the detector's measurement model.
It is not automatically a fully re-demodulated likelihood at the changed CFO,
an independent physical waveform model, or a calibrated source-presence test.
Changing within-symbol demodulation or fractional epoch as well would define a
different test and must be reported separately. An improvement on an inverse
template toy does not by itself justify new satellite admissions or geographic
claims.

Earlier `tools/probe_ds23_raw_pilot_refinement.py` already performed continuous
fixed-epoch and joint CFO/epoch/rate fitting, odd/even-frame comparisons, template
debias and effective-time calculations using the broader pilot workspace. The
new opportunity is therefore a deliberately narrow exact-scope64 comparison,
not generic continuous CFO estimation. The independent prior-art review records
the older experiments and their absence of qualified cohort position gain.

For field replay, preserve the original physical window, sample counters,
receiver/channel/RF, original fractional candidate and native observation ID.
Use the public `ShortWindowReader` and exhaust its bounded iterator so complete
containing-chunk verification executes. Use `VerifiedFastWindow` and the original
persisted fast policy to reproduce acquisition before attributing its stages.
No raw path may be constructed from convention when the contract supplies it.
The earlier DS24-0011 first-window replay demonstrates this authority pattern;
it does not establish parity for the newly selected field windows in advance.
