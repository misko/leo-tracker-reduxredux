# Same-receiver rescue with native tone removal

The previous turn was progress: the implemented raw rescue completed its frozen
control experiment and failed on three distinct tone receiver waveforms. This
new candidate addresses that observed failure. It does not change any frozen
experiment, acceptance threshold, primary detector, or reserved dataset.

Implement the narrow scoring port described in
`../native_rescue/NEXT_EXPERIMENT.md`. Fully pack and load one 20 ms receiver
probe, apply exactly the existing native blind nuisance-tone transform, then
invoke its final GLRT at the supplied hypothesis. Do not call the V2/V3 helper
after subtraction: it would overwrite the transformed support with raw IQ.
Use the same scientific flags and FFTW backend; do not requantize the transformed
FP64 buffer. Repeat preparation per call initially; add no prepared-buffer cache.

Use separate explicit ports for the unchanged primary tracked detector and the
new rescue scorer. Preserve the failed rescue's fixed policy: first inactive
receiver in RX0/RX1 order; one Python acquisition on probe zero; at most ten
ordered hypotheses; Python score gate; actual native measurements on probes
zero and two; original acquired and physical CFO supplied to both; per-member
and mutual identity/positivity gates; first accepted pair; no rescue cache
injection. Keep the tone-fit receipt for every attempted native observation,
including rejected points. Complete-call timing includes these calls and all
conversion, selection and controller work; serialize receipts outside timing.

Before saved IQ, qualify the engine on generated arrays and audit data flow,
support, frequency identity, normalization, ABI/error behavior and buffer bounds.
Check raw-engine parity where the nuisance fit is not applied and native-blind
transform/score parity where it is. Distinguish coordinate-normalization
roundoff from algorithm changes; do not promise bitwise equality across
different integer/fractional representations without testing it. Constructed
control files from earlier experiments belong to the frozen evaluation stage,
not unfrozen engine tuning. Unit tests may generate independent deterministic
noise, tone and pilot mixtures.

Freeze implementation, tests, runner, dependencies and membership before any
saved-IQ outcomes. Evaluate the same 42 original controls and 12-parent,
24-execution orientation audit from `native_rescue`. Compare unchanged tracked
native, the frozen failed raw rescue and the new tone-removal rescue on this
stage. Preserve original/derived input provenance and fresh state in the audit.
The raw comparator's known failures are recorded, not a reason to prevent
testing the new variant; all required truth policies must pass for the unchanged
primary and new candidate before opening later stages.

If controls pass, evaluate the existing 26 diagnostic development cases, then
64 chronological recorded visits. Later stages compare the application,
unchanged tracked native, and new rescue. A required constructed truth failure
stops progression. Record physical truth separately from reference agreement;
all recorded additions remain physically unadjudicated. Report receiver and
visit identity retention, 1/3/5% reference-miss bands, additional detections,
routes, actual rescue work, and aggregate CPU plus median/p95/p99/max latency.

One DSP campaign at a time, CPU0, numerical libraries single-threaded. Bounds
are 120 seconds each for controls and diagnostic, 300 seconds for recorded
replay. Loading, source hashing and one-time initialization are excluded from
per-call timing and must be reported as such. Save immutable failed receipts;
no in-place repair or retuning. No validation/holdout IQ generation or opening,
production changes, RF collection, or QNAP writes in this development experiment.

The 10x target remains unproven for a qualified small-loss replacement. Earlier
18–22x rescue estimates were planning models, and raw-rescue control timing
cannot establish application-relative speed. Measure this actual candidate.
