# Exact integer energy and NEON widening feasibility

Both candidates preserve the prepared raw complex128 samples, normalized FP32
samples, and FP64 prefix sums bit for bit, but are rejected for ARM runtime.
This is an input-preparation microbenchmark, not full GLRT dwell timing.

| Rate | Scalar control ms | Integer-energy ms | Separate NEON control ms | NEON widening ms |
|---|---:|---:|---:|---:|
| 2.5 MS/s | 60.994 | 62.425 | 60.497 | 98.278 |
| 5 MS/s | 121.589 | 124.541 | 120.854 | 196.083 |
| 7.5 MS/s | 182.848 | 187.568 | 182.050 | 293.624 |
| 10 MS/s | 242.854 | 250.553 | 241.914 | 391.783 |

CPU0 timing includes allocation and preparation of both receivers of one
120 ms dwell. Six repetitions alternate control/candidate order; frees occur
outside the timed interval. The scalar candidate replaces two FP64 squares
with exact int32 component squares, unsigned32 addition, and power-of-two
scaling. Prefix sums remain exact within the supported 1.2 million samples.

The NEON candidate converts CI16 to exactly representable FP32 and constructs
the corresponding FP64 storage bits using integer vector operations, while
also generating normalized samples and integer energies. It preserves strict
aliasing via local uint64 arrays and memcpy. Its extra rearrangement and
conversion work overwhelms the avoided scalar arithmetic on this target.

Host and sanitizer checks cover all four rates. Physical ARM checks compare
every prepared element against the original implementation. The NEON test
explicitly covers all 65,536 signed16 values, zero, full-scale complex power,
and random input. Host builds do not execute the ARM-only NEON branch.

`builds/` is the scalar candidate. `builds-v2/` preserves an unsuccessful
cross-build attempt using an intrinsic unavailable on ARMv7; its host checks
completed but it has no ARM measurement. `builds-v3/` replaces that store with
ARMv7-compatible lane combinations and is the measured NEON candidate.
`arm-result.json` and `arm-result-v3.json` bind measured binary hashes.
Neither candidate is integrated into the GLRT pipeline.

A final blocked variant (`builds-v4`) separates 256 samples of NEON
conversion from scalar prefix accumulation to test whether frequent switching
between the two caused the regression. It remains slower: 98.328, 196.489,
295.006 and 393.755 ms at the four rates, against matched controls 60.590,
120.799, 181.116 and 242.183 ms. All exactness checks pass. This rules out
that particular scheduling fix; this input-preparation direction is stopped.
