# Long-arc frame-vector phase transport

The 78-visit replay stores a complex eight-tone vector at each frame reference.
For a guarded IQ slice whose physical origin is `o`, raw IQ contains carrier
phase at `o + n`.  The split estimator removes the acquisition NCO at local
sample `n` and restores it at the local reference sample.  Its saved vector
therefore already includes the physical `o` phase.  A consumer must not rotate
it by `frame_start_sample` or `valid_start_counter` again.

For the current integer-grid extraction, the physical vector reference counter
relative to the session's first sample is

```
s_i = valid_start_counter - source_first_counter + reference_sample_i
t_i = s_i / sample_rate_hz
```

`fractional_epoch_offset_samples` was not passed to the split estimator.  It
must consequently not be silently added to a saved vector's timestamp.  A
future fractional-interpolating extractor would instead evaluate at
`s_i + fractional_epoch_offset_samples`.  Within one dwell that offset is
constant, so it cancels from the present adjacent-pair interval; at 15 MS/s
the selected pair interval is exactly 20,000 samples, or 1/750 s.

For same-dwell vectors `c_i` and `c_j`, a static tone response cancels in
`vdot(c_i, c_j)`.  Qin pilots have a pi-radian carrier equivalence, so the
valid increment is

```
d_ij = 0.5 * angle(vdot(c_i, c_j)**2)                 # modulo pi
q_ij = 2*pi * integral[t_i, t_j](f_native(u) du)     # modulo pi
r_ij = wrap_pi(d_ij - q_ij)
```

The candidate trajectory must be at native source RF.  A prediction expressed
in the manifest's 11.2 GHz CFO convention is divided by
`historical_rf_normalization_scale` before the phase integral.  A per-visit
circular increment intercept removes unknown carrier offset and phase.  It
must be fit from the six even calibration pairs only.  A candidate-common
receiver frequency-rate grid may be selected across the 42 outer-train visits;
the chosen candidate/grid then scores the 36 odd held visits.  The matching
zero-curvature model must retain the same per-visit intercept freedom.

This is conditional evidence: a receiver LO curvature that is allowed to vary
freely by dwell can absorb the satellite-rate signal.  It does not establish
cross-visit phase continuity, identity, or position.

The reproducible [phase-advance comparison](2026_09_23_longarc_phase.md)
uses all 78 visits and retains this conditioning explicitly. Its selected
candidate has held phase RMS 0.2612 rad versus 0.2621 rad for the constant-rate
control. Wrong-time geometry performs slightly better. The present extraction
therefore does not demonstrate an incremental association constraint.

`tools/research/longarc_phase_transport.py` implements the coordinate and
modulo-pi operations.  Its synthetic test creates the same carrier at two
different physical slice origins while passing dwell-local frame coordinates;
the recovered increment matches the physical time advance, and a transport by
the carrier trajectory makes the vectors stationary.  This confirms that an
extra frame-start rotation would double-count the capture origin.
