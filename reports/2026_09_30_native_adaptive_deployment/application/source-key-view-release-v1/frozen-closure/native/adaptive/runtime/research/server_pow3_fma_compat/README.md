# Server pow3 FMA compatibility research

This directory freezes an isolated experiment for reproducing the reference
server's `glibc 2.43` x86_64 FMA implementation of `pow(x, 3.0)` on the
Cortex-A9 target. It is not linked into the native runtime and does not change
the portable fractional-support calculation, a published authority, a golden,
or a numerical tolerance.

The reference machine runs Ubuntu `libc6 2.43-2ubuntu2.4`. Its
`pow@@GLIBC_2.29` wrapper selects `__ieee754_pow_fma` through the hidden
`__pow_finite@GLIBC_2.15` IFUNC when FMA and AVX2 are usable. The existing
compatibility prototype calls that system `pow`, so its exact result depends on
the host libm selection.

`e_pow.c`, `e_pow_log_data.c`, and `e_exp_data.c` derive from GNU glibc tag
`glibc-2.43`, commit `f762ccf84f122d1354f103a151cba8bde797d521`, and the
byte-identical Ubuntu source at
`bcb78c375b4d83d05825482edc665379b01f0c96`. The original copyright and
LGPL-2.1-or-later notices remain in those files; [COPYING.LIB](COPYING.LIB)
contains the license. `e_pow.c` makes the FMA variant's compiler contractions
explicit and is built with contraction disabled, allowing a target libm's
correctly-rounded `fma` operation to reproduce the selected x86 sequence.

Run `./build.sh host && ./test.sh host`. For QEMU, run
`./build.sh arm && ./test.sh arm`. The test derives both TSVs from the frozen
24,681-row projection fixture, verifies their authority hashes, and requires an
exact byte comparison covering all 11,747 retained observations. On physical
ARM, copy the two ARM artifacts plus the generated TSVs and run:

```sh
LD_PRELOAD=./libserver-pow3-fma.so ./leo-server-moments < input.tsv > actual.tsv
cmp expected.tsv actual.tsv
```

The physical proof is scientific compatibility evidence, not a performance
qualification. The measured full harness took 96.927 seconds with this layer
and 37.380 seconds using target system pow. Geometry memoization and production
integration remain separate future work. Python-compatible decimal authority
lexemes are tested by the separate named compatibility profile below.

`runtime_server_moments_cached.cpp` is a second research-only experiment. It
keeps one thread-local successful support result, keyed by every function input,
the exact fractional-offset binary64 bits, and the floating-point rounding mode.
The DS9 retained sequence has 11,747 calls, 9,510 distinct keys, and 2,237
adjacent duplicate keys, so one entry captures every possible hit with bounded
memory. `build_cached.sh` and `test_cached.sh` build and compare both paths.

## Python float repr compatibility profile

`server_python_float_repr_compat` is an isolated, research-only formatter for
the reference server's finite binary64 support moments. The server persists
these values through Python `json.dumps`, whose float tokens use `repr`. The
profile searches the 1--17 significant-digit decimal grids for the shortest
bit-exact round trip. At each precision it tests the correctly rounded `%g`
grid point and four neighbours on each side, then uses fixed-width integer
arithmetic to select the decimal nearest to the exact binary64 value, with an
even-significand tie break. It finally applies Python's fixed/scientific
threshold, exponent, and integral-fraction conventions. The convex binary64
round-trip interval means only the nearest grid point and its immediate
neighbours can qualify; the wider nine-point search covers decimal ties too.

The function checks rather than changes its environment: round-to-nearest and
C numeric decimal conventions are required, and non-finite values are
rejected. This avoids process-global locale or rounding mutations.

The target Linaro GCC 7.3.1 libstdc++ does not provide floating-point
`std::to_chars`, so
this bounded search is also buildable on the actual ARM toolchain. It is a
compatibility experiment rather than a production serialization API. No
CPython source is copied or linked, and the glibc-derived source and license in
this directory remain unchanged.

Run `./build_lexeme.sh host && ./test_lexeme.sh host`. The exporter preserves
the raw canonical-JSON moment tokens and independently requires the reference
Python interpreter to reproduce them with `repr`. The C++ test covers all
23,494 moment values in the 11,747 retained DS9 rows. Plain shortest C++
formatting differs only for 1,949 zero moment3 values (`0` versus `0.0`), while
the named profile is exact for every value. Current `max_digits10` native
spelling differs for 5,987 moment2 and 6,588 moment3 values.

The same test generates 116,364 unique adversarial finite binary64 values with
the reference Python 3.13.15 interpreter: every power of two and ten in the
binary64 range and their adjacent values, signed extrema, normal/subnormal
boundaries, both zeros, and 100,000 finite bit patterns from seed `0x5e71a1`.
Host and QEMU ARM output agrees exactly with Python `repr`. This test caught and
preserves the asymmetric power-of-two counterexample `2**-1017`: `%.17g`
spells it `7.1202363472230444e-307`, while Python's shorter round-trip spelling
is `7.120236347223045e-307`. The evidence qualifies the named corpus and
adversarial set; it is not a claim that this research formatter is a published
general-purpose CPython serialization contract.

`./test_compatibility_stack.sh host` composes the pinned server `pow(x, 3.0)`
implementation with the formatter and requires the recomputed binary64 output
and every persisted moment lexeme to match. Because candidate identity, support
times, and all four support-moment tokens are then identical to the supplied
graph authority. `./test_graph_compatibility.sh` then builds that authority
directly from the pinned-pow output, runs the native pipeline, and independently
recomputes the server support digests, partition seeds, observation IDs, and
training masks from `oracle-tracks.json`. All four values match for all 58
membership-identical tracks. The six known duplicate-rank candidate-ID ties
remain a tracking identity issue, not a decimal serialization issue.

The ARM formatter artifacts are produced with:

```sh
./build_lexeme.sh arm /tmp/leo-server-python-float-adversarial-arm
./test_lexeme.sh arm /tmp/leo-server-python-float-adversarial-arm
```

For a physical CPU-only rerun, copy `test-python-float-repr-adversarial` and
`adversarial.tsv` from that directory to the same target directory and run
`./test-python-float-repr-adversarial ./adversarial.tsv`. This does not access
radio hardware.
