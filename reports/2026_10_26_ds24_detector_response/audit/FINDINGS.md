# Independent audit

All three branches pass their independent preflight and terminal checks.
The auditor performed no detector calls, IQ reads, geometry propagation,
position fits or numerical correction searches.

[The synthetic measurement audit](measurement_terminal.json) checks all 64
receiver slots and the eight fresh paired detector calls. Original IQ hashes,
candidate ranks, acquired CFO, integer/fractional epochs and original gates
are preserved. All 128 target/control spectral cells independently reproduce
their original FFT maxima and refined direct complex-sum scores. Every
frequency and margin numerical guard passes. These checks establish local
cell closure, not a global maximum or calibrated source confidence.

The old control's midpoint-CFO RMS changes from 16.552/16.633 to
2.191/2.350 Hz; fresh signed controls change from 15.314/15.133 to
1.773/1.508 Hz. Zero original GLRT residuals show that the old final values
inherited their acquisition estimates. The continuous extension can resolve
their small frequency offsets without changing aperture or within-symbol
demodulation. The controls share the detector's sampled-template law: this
is a useful measurement-model result, not independent transmitted-waveform
authority, real-noise calibration or localization improvement.

[The accepted-owner audit](influence_terminal.json) verifies the original
Gaussian/VI normal equations, every family and eligible-owner score using
an independently constructed SVD polynomial basis, chronological case choice,
and exact native ownership. There are 54 complete eligible owners in 0010
and 48 in 0011. The four selected owners retain all 159 original points.
Targets are 0010 RX1 CH7 T001/68566 and 0011 RX2 CH4 T000/63936; controls
are 0010 RX2 CH4 T004/59244 and 0011 RX1 CH1 T007/66341.

Susceptibility describes a unit-RMS smooth quadratic perturbation in the
original conditional model, using each arm's original weak axis. It is not
measured bias or achieved movement. Missing baseline physical-mode covariance
remains missing. The oscillating synthetic interpolation error is not that
smooth perturbation, so multiplying its 16.6 Hz RMS by these m/Hz scores
would not predict a position gain.

[The recorded audit](recorded_terminal.json) verifies all eight fixed
native-window requests, exhaustive public-reader integrity bindings,
unchanged historical implementation/environment, and exact candidate parity
on both receivers. All 96 archived complete fractional candidates match
with zero error. The replay returns 128 raw candidates; the other 32 have
no archived complete fractional row and are not claimed to pass parity.
All 16 target/control cells and all eight frequency/margin qualifications
pass; the original requested rank, epoch and gate remain unchanged.

| Case / owner role | First / second quantile correction, Hz |
|---|---:|
| 0010 target | +71.467 / −63.913 |
| 0010 control | +79.036 / −8.635 |
| 0011 target | −4.680 / +20.319 |
| 0011 control | −4.007 / −53.911 |

These are measured numerical changes to the same score, not verified field
error reductions. Large changes also occur in the lower-influence controls.
Two windows cannot establish a complete owner's error shape, uncertainty or
satellite adequacy. Existing noise/admission rules and operational positions
remain unchanged. A complete-owner, fixed-rule measurement comparison with
predictive checks is the next meaningful prerequisite to matched-c position
testing; another unconstrained path or timestamp sweep would not answer it.

[The prior-art review](PRIOR_ART.md) distinguishes this exact scope64
intervention from earlier full-frame continuous CFO/epoch/rate refinement
and effective timestamps. The earlier 322-curve cohort's scatter improvement
did not establish a qualified cohort position gain; that limitation remains
relevant to interpreting the current positive measurement result.

The final binding check caught a coordinator-document addition after the
first two protocols froze. The original plan was restored byte for byte;
the authorized recorded follow-on is preserved in
[a separate scope addendum](../RECORDED_SCOPE.md). The failed check remains
in [its receipt](final_seal_attempt01.json). No scientific source, input,
result, gate or numerical threshold changed, and no science was rerun.
