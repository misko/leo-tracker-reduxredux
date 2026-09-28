# Arithmetic and qualification notes

The candidate keeps six ranking windows, both receivers, one confirmation per
receiver, and the original frame/known-symbol support. No golden fixtures or
production components were changed.

SOL's k-major fold keeps four complex int64 accumulators in NEON registers
across the 15 frames rather than loading/storing them on every frame. Integer
addition remains exact. The scalar tail uses the original validity bounds.

Terra audited every `fold_double` use. Each complex CI16 product or power term
has magnitude at most 2^31. At most 16 terms gives 2^35; the current 20-ms
windows actually fold 15 frames at all four rates. V5 ranking also folds 15.
The helper's ±2^36 precondition therefore holds. GCC arithmetic signed shift
and defined modulo uint16 conversion reconstruct the integer using exact
FP64 components. `test_fold_double.py` checks 250,118 deterministic boundary
and random values and verifies native ARM conversions in disassembly.

The separate, unchanged `ci16_lag.h` comment assumes at most 100,000 samples.
That comment predates the isolated four-rate probe and is stale: a 10-MS/s
20-ms window has 200,000 samples, with a worst-case sum bounded by
200,000 × 2^31 < 2^49 < 2^53. int64 accumulation and FP64 conversion remain
exact. Correct this comment when promoting code; frozen source/binary receipts
are retained unchanged here.

The experimental `fastindex` branch removes per-sample rounding calls where
the existing guards prove nonnegative, bounded indices. Host ASAN tests cover
the corpus. It is not a general hardening of the public GLRT API: the original
near-integer endpoint guard can allow rounding to `count` for tiny negative
offsets. The internal integer lattice uses exact zero. Arbitrary external
near-integer offsets require a separate boundary fix and tests before exposure.

Timing claims must distinguish saved-IQ execution from capture contention.
Concurrent tests process resident historical IQ while live receive-only scan
traffic runs. They do not yet connect new live IQ to GLRT or feed its results
back to the adaptive controller. Moving IRQ work uses the second physical core;
the GLRT remains one thread on CPU0.
