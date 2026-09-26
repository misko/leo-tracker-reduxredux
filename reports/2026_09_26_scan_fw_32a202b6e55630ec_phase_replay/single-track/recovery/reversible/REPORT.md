# Reversible phase replay

This prototype retains every phase correction as a complex unit phasor. The
reported residual is therefore only a convenient processing coordinate; the
declared input coordinate is recovered by multiplying the retained phasors
back in. A synthetic regression confirms that a known geometric phase survives
derotation and exact reconstruction, while residual-only output loses the
removed phase.

`cached_corrected_phase_deg` is the actual Qin per-tone product after the
sample-level differential-CFO correction used to build the frozen cache.
`declared_uncorrected_gauge_phase_deg` adds that correction back at the frame
reference. It is **not** the raw uncorrected broadband average: time-varying
derotation and averaging do not commute. The roughly 682 kHz correction is a
declared processing branch, not an independently established hardware
calibration and not a geometric-phase estimate.

The tracker is the bounded causal previous-increment baseline. It uses only two
preceding frames in the same contiguous dwell segment. Its correction is stored
in `tracker_removed_cycles`; unsupported segment starts remain blank. No cycle
count is inferred across a dwell gap.

`cached_within_dwell_change_deg_processing_gauge` gives the within-segment
change after the declared GLRT correction. It is not geometric merely because
the physical hardware is stable: the correction itself might have removed
geometric frequency. Interpreting this column as geometric requires independent
proof that the removed correction contains only instrument phase and that the
remaining instrumental and non-geometric propagation terms are constant.
Neither condition is established by these five dwells. The declared input gauge
can be reconstructed modulo 2π, but the sparse frame phases cannot establish
the intervening cycle count of the large frequency correction.

Run `run.py` to regenerate `summary.json`, `reversible-phase.csv`, and
`reversible-phase.png`. Numerical results in `summary.json` are generated from
the frozen cache rather than copied into this report.

On the frozen five-dwell cache, 435 of 445 frames have the two prior frames
required by the causal replay. The other ten are the first two frames in each
dwell. Complex reconstruction agrees with the declared input gauge to a maximum
absolute error of `2.29e-16`. Keeping the residual alone changes the declared
input phase by `104.34 degrees RMS` (wrapped), demonstrating why the correction
record is necessary; it is not a recovery-quality score.
