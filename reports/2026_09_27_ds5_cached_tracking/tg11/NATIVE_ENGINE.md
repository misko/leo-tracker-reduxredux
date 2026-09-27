# TG11-v1 native observation engine

This research port implements the measurement boundary from
`application_coarse_alternatives/TRACK_GUIDED_DESIGN.md`. It does not own cache
state or detector decisions.

`NativeTG11.screen(raw, receiver=...)` accepts one complete C-contiguous
`int16[N,2,2]` 120 ms recording. It evaluates eleven chronological 20 ms probes
at 10 ms spacing exactly once, using the frozen decision-band rank implementation.
The selected hybrid projection is chosen from the contrast across all eleven
probes. A `ScreenWindow.projected_epoch_sample` is local to that 20 ms probe;
`probe_start_sample + projected_epoch_sample` is dwell-relative.

`blind(raw, receiver=..., screen=...)` requires the existing screen object for
the same raw allocation and receiver. It performs no rank work. It runs the
unchanged unseeded FP32-FFTW confirmation on all eleven probes and returns both
native candidates from every probe. `guided(...)` performs one full-aperture V3
known-state score at caller-supplied local timing and scoring CFO. Its optional
`expected_physical_cfo_hz` must be supplied by the causal decision layer when
physical and scoring CFO differ.

Observations expose local and dwell-relative epochs, acquired/scoring CFO,
physical tracking CFO, exact/control/margin, fractional completion, actual frame
support and fitted-versus-predicted semantics. The pre-outcome support rule is
`valid_bounds && support_frames >= 2`, matching the frozen research protocol.
A full 20 ms aperture commonly contains 14 or 15 usable 750 Hz frames; sixteen
is a computation cap rather than a validity requirement. Fractional completion
is a separate field and decision condition.

The build is isolated here and hash-pins the deployment native sources, frozen
research V3/V4 sources, profile flags, FFTW backend source and linked library.
No production source is modified. Workspaces are non-reentrant. Input loading,
causal routing and complete-call timing belong to the parent TG11 harness.

Component tests cover both rates and receivers for screen coordinates and
determinism, both candidates against the direct FP32 native confirmation,
14/15-frame support, dual-CFO guided equality to V3, zero input, screen reuse,
caller immutability and build receipt integrity.
