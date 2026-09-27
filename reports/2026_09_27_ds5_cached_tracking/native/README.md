# Known-state native GLRT research port

This bounded port measures one selected 20 ms CI16 interval at timing and CFO
predicted by a causal channel tracker. The fast point runs one existing final
exact/rolled-control GLRT. It performs no blind timing acquisition, whole-dwell
ranking, tone fitting, or energy-based acquisition-support selection.

`NativeKnownState.measure(iq, epoch_samples, cfo_hz)` returns the scored
fractional timing, fresh CFO innovation, tracking CFO, exact/control/margin,
support-frame count, trust/reacquisition status, and conversion/kernel/total
CPU and wall timing. Timing semantics are `predicted_verified`: the fast call
scores caller timing but does not pretend to fit it. Passing
`recover_timing=True` evaluates a local +/-1 sample bracket and a parabolic
fit; an edge maximum requests blind reacquisition.

The research shared object includes the hash-pinned deployment `presence.c` in
the wrapper translation unit so CI16 is converted once before the unchanged
static final GLRT kernel is called. It uses the newer decision-band scientific
flags. This implementation coupling is confined to the research artifact and
is not a production/runtime dependency.

`known_state_v2.py` adds direct support for a natural `raw[:, rx, :]` dual-RX
view and converts only samples used by the GLRT. Its `frame_limit=16` result is
bit-identical to V1. Limits 4 and 2 are separate partial-aperture research
statistics labelled `partial_N_frame_final_glrt_unqualified`; they must be
qualified independently and must not be substituted for the full score.

`known_state_v3.py` adds an optional expected physical CFO while preserving the
acquisition CFO as the scoring center. The raw GLRT residual stays visible, but
reacquisition uses measured-minus-expected physical CFO. This handles a valid
physical CFO outside the scoring center's +/-400 kHz range when the residual is
within the GLRT's representable support. V1 and V2 remain frozen for comparison.

`blind_strided_v4.py` removes the server harness's full 120 ms receiver pack on
blind fallback. Rank reads the natural receiver stride and only selected 20 ms
confirmation windows are packed inside native code. The safe ARM stride path
is scalar pending a raw-base-plus-receiver-lane ABI and ARM-specific timing.

`blind_aligned_v5.py` supplies that safer ABI: a C-contiguous dual-RX base plus
an explicit receiver lane. Its Cortex-A9 cross-build contains the intended NEON
interleaved loads and widened int64 accumulation. This is disassembly evidence
only; the prototype has not been executed or timed on ARM hardware.
