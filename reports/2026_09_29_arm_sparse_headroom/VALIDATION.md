# Host validation of sparse preparation

This review covers the working tree based on commit
`32f71e25b35390a73a5d3a79a222d923b07b40ff`. It is host-only; it does not
claim Cortex-A9 timing or hardware qualification. The reviewed source hashes
were:

- `native_glrt.c`: `600df997e2d8e41135c60cb19ca894ce3b036dbfc1dd409c8c57891448a7742f`
- `native_glrt.h`: `abbc657d54a37f4e7031200d4f91653d8d5a96ba1d2871e7d3924eb43f0c660f`
- `dwell_input.h`: `4bbc82c77598fccd76732c4903e982c9cbfe950892ac8bdd61edf1e8b4609abf`
- `fine_precision.h`: `62bfcec3559229556fbd13bc96b7a73c0839424adab72a8e5c1e5d647f33e731`
- `full_search.c`: `ba0b355ee211eefb478548e5a56d0818f6d473d14ac5eef5210aa474e95d25cb`
- `full_search.h`: `6eac36d36c4ea92889fbd7c929b7b9eb9dfdcaee2f0f04e30f460f7a0a573fa8`
- `private_namespace.h`: `2d0a6def884fc24ac453dd475a8730b014c34ea1f30e9ba271dfa4b5d176b5c0`
- `provenance.json`: `469ea7264f6bdaf4d06c21cae39ac7178cd9f07ff4cc97232222067dfbb7e389`
- `test_native_glrt.c`: `2bde7a32e3a691fd27adb12448504bfd93d3df5578a360a99d38a14bb73fa3b7`

## Commands and outcomes

The package-owned native GLRT tests were run with:

```sh
.venv/bin/pytest -q \
  tests/analysis/test_native_glrt*.py \
  tests/qualification/test_*glrt*.py
```

Outcome: `10 passed in 12.58s`.

This includes both maintained release-builder modes, persistent-context
benchmark execution, saved-input CLI candidate parity, profiler-wrapper
linking, cached and literal conditioned-boundary controls, public/private
symbol coexistence, and the C component suite. The C suite executes every
combination of four supported rates, three supported dwell lengths, and three
supported strides. It also exercises invalid rates, dwell lengths, strides,
sample counts, and non-finite or out-of-range templates, plus repeated
valid/invalid/valid use of one context.

The sparse science checks compare the two rows from the 120 ms stride call to
the matching first two rows from the full-preparation 20 ms stride call. The
comparison is bitwise for candidate structures and exact for counters. It runs
at every supported rate on coherent positive input, deterministic full-range
noise, and alternating `INT16_MIN`/`INT16_MAX` input.

An independent full-preparation control archive and C component executable
were built in a fresh temporary directory using the maintained builder with
`full_prep=True`. The C executable was compiled with
`-DLEO_NATIVE_GLRT_FULL_PREP=1` and run without a geometry filter. Its ordered
diagnostics covered all 12 rate/dwell sections and ended with:

```text
native GLRT RAM API tests passed
```

The temporary build receipt was
`/tmp/leo-sparse-validation.biLt3K/out/build-receipt.json`. This path is local
validation evidence rather than a publication artifact.

## Final sanitizer lifecycle run

The final default source was rebuilt on the host through the maintained release
builder. The compiler wrapper added only
`-fsanitize=address,undefined -fno-omit-frame-pointer` to `/usr/bin/gcc`; all
production feature macros and private source selection came from the maintained
builder unchanged. The component executable was then linked from that archive
and run with:

```sh
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1:abort_on_error=1 \
UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 \
/tmp/leo-native-glrt-san-final.pcWwRq/test-native-glrt-san
```

The exact component link command was:

```sh
/tmp/leo-native-glrt-san-final.pcWwRq/gcc-san \
  -std=c11 -O1 -Wall -Wextra -Werror \
  -I/var/tmp/leo-arm-realtime-publication/src/leo/analysis/native_glrt \
  /var/tmp/leo-arm-realtime-publication/tests/analysis/native_glrt/test_native_glrt.c \
  /tmp/leo-native-glrt-san-final.pcWwRq/out/libleo-native-glrt.a \
  /tmp/leo-native-glrt-san-final.pcWwRq/fftw/lib/libfftw3f.a \
  /usr/lib/gcc/x86_64-linux-gnu/15/../../../x86_64-linux-gnu/libfftw3.so -lm \
  -o /tmp/leo-native-glrt-san-final.pcWwRq/test-native-glrt-san
```

All 12 rate/dwell sections completed, including all three strides within each
section, coherent/noise/extrema sparse-versus-dense comparisons, repeated
context use, cross-stride buffer release and refill, and invalid-call then valid
call recovery. The final line was `native GLRT RAM API tests passed`. Sanitizer
stderr was empty, including leak detection.

Artifact hashes:

- Sanitized archive: `91bad3e38e2dc97674e1ef28fde39a1e4f361148a3287e76ca48bffabbaddee4`
- Maintained build receipt: `6b4a76b85eb231557010d19134d44a206f5f12fa649d2a21664f0df3af5bb314`
- Sanitized component executable: `e3f45e4cb36a548bc5678799610922e0b7e0ee14ae3bd4fc7e8c6f90bc408d56`

The earlier expanded ARM geometry unit was cross-linked, without execution,
against the frozen normal tile-and-reuse archive
`/var/tmp/leo-native-glrt-headroom-tile-reuse-final-v1/libleo-native-glrt.a`.
The archive SHA-256 is
`6f70612cf2fc811add68c4bd9130f2fc6879ac7f14b985eac66dc4952399e3f7`.
The unit is `/tmp/test-native-glrt-tile-reuse-final-arm`, with SHA-256
`5a7f5fc13d7c1c817883f509a2676def9ce7c16e95f97c4c6738ce844c739545`.
Its exact compiler arguments and all input hashes are recorded in
`builds/geometry-unit-tile-reuse/build-receipt.json` (receipt SHA-256
`08b605ae1680ec4d31c72543bd9613ed4453c50c8347d145b86e5571f620297d`).
Physical execution remains the root hardware owner's responsibility.

That unit is superseded by the final V3 unit after lazy sparse-buffer release,
persistent fine-plan reuse, and private-symbol namespace correction. The V3
unit is `/tmp/test-native-glrt-final-v3-geometry-arm`, with SHA-256
`c20cf56d19fa28fd31210c24b8b1673e7a66cc721ce20af7ef39f1c33a1bcf41`.
It links only the frozen normal archive
`/var/tmp/leo-native-glrt-headroom-final-v3-frozen/libleo-native-glrt.a`
(SHA-256
`ada0098eb88e8f956db7f548b6eb8da37c422f90a16efebad88387f80da3b3e1`).
Its receipt is `builds/geometry-unit-final-v3/build-receipt.json` (SHA-256
`ac0a0afa7bca25673f2da3976ab054aaeb24d1f275729c46190c5cee059cd37a`).

## Correctness review

For `dwell_ms == 120` and `probe_stride_ms == 120`, layout produces one window
per receiver at sample offset zero. Proposal generation reads the original
CI16 input directly. Each full search receives exactly `rate / 50` complex
times and therefore reads only the prepared first 20 ms. Preparing `rate / 50`
instead of the validated 120 ms input cannot change any value consumed by
either search. Other dwell/stride combinations retain full-dwell preparation.
The `LEO_NATIVE_GLRT_FULL_PREP` build restores the former behavior without
changing candidate settings.

The existing analyzer remains a wrapper around the common implementation and
commits neither its result nor its optional profile on failure. The outer
detector CPU interval still begins before temporary allocation and ends after
prepared-input and bookkeeping cleanup. The five profile categories are
disjoint outer intervals in successful calls: bookkeeping allocation, input
preparation, scheduled proposal loop, search loop, and cleanup.

## Remaining risks and interpretation

The null-profile compatibility path still takes all stage clocks. A successful
call now performs the detector boundary reads plus two CPU/wall reads around
each of the five stages, even when `leo_native_glrt_analyze` passes a null
profile. This is a small but real baseline overhead and must be included in the
physical ARM comparison. It does not affect numerical results.

For dense 10 ms operation, a proposal fallback executed from inside the search
loop is charged to the outer `search` profile interval. Thus the profile names
describe code regions, not a fully semantic attribution of every nested
operation. The target 120/120 sparse geometry has no odd-window fallback, so
this limitation does not affect its proposal-versus-search split.

The host suite proves supported geometry, failure behavior, and numerical
equivalence. It does not establish Cortex-A9 CPU or wall targets, memory peak on
the constrained device, PGO benefit, or thermal stability. Those require the
separately controlled physical runs.

The reusable sparse prepared workspace costs `64 * rate / 50` bytes while it is
resident: 3.2, 6.4, 9.6, or 12.8 MB at the four supported rates. It is now
allocated lazily by a 120/120 call and released before any longer or denser
geometry allocates its full call-local workspace. Thus longer geometries no
longer combine both prepared allocations. The final physical V3 rerun passes
7.5 MS/s by 360 ms and 10 MS/s by 240 ms, including all three strides. The
10 MS/s by 360 ms case still returns the known constrained-memory failure.
See `hardware-geometry.json`; these three final physical boundary cases do
not constitute a final-source full 36-geometry hardware campaign.

The expanded contract, component, qualification, CLI and report test command
is recorded in [EXECUTION.md](EXECUTION.md): **63 passed in 20.96 seconds** on
the final publication tree. Ruff checks for the changed Python components,
tests and report scripts passed (the byte-frozen execution runner was excluded
from formatting). Final sanitizer validation above
uses the same native source as the sealed v3 timing builds.
