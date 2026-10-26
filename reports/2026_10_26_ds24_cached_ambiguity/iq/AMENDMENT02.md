# Pre-detector amendment: a declared continuous-time test law

The original construction prerequisite failed before any detector invocation.
At integral epoch, the direct continuous-time generator differs from the
deployed sampled template at 68 of 13,333 samples, all exactly on the 44-sample
symbol boundaries. Off-boundary maximum difference is 1.493e-7. The original
test and measured failure remain unchanged in the archive.

The deployed template obtains its symbol index with floor((n/fs)/4.4e-6);
the synthetic law uses exact 44-sample symbol intervals and chooses the right
side of each boundary. Floating-point arithmetic makes the former select the
previous symbol at some integral boundaries. This is a discretization
difference, not proof of a physical receiver error or authority to change a
golden waveform.

Proceed with the already-declared eight scenarios only as a **pilot-only
synthetic control with a known template mismatch**. Do not claim deployed-
waveform parity, realistic payload/channel closure or empirical field bias.
An independent construction check evaluates all 300 right-boundary samples
directly from the deployed pilot coefficients and their analytic carrier
phases, and checks the right-hand limit. Off-boundary parity still uses the
original 5e-7 tolerance. The original frame-parity test stays failed; it is
not replaced by a looser tolerance.

No detector, IQ or position result existed when this amendment was written.
Scenario parameters, seeds, receiver noise, original detector and selection
policy, all 16 paired-window slots, outputs and 120 s invocation cap remain
as declared in PROTOCOL.md. All conclusions must include the known waveform
discretization limitation. No original IQ replay, source implementation or
scientific fixture is changed.
