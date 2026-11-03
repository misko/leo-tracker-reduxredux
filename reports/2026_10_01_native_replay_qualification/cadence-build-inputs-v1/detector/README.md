# Native GLRT RAM component

This is an opt-in production-owned analyzer for saved dual-receiver CI16
dwells. It is not selected by default, is not part of the deployed scanner
worker or radio capture path, and does not replace persisted adaptive-hop or
fractional-analysis products. Its output is separate candidate evidence under
the `leo-native-glrt/v1` and `wave8-gate314-source-v1` identities.

The component supports sample rates 2.5, 5, 7.5 and 10 MS/s; dwell lengths
120, 240 and 360 ms; fixed 20 ms probes; and probe strides 10, 20 or 120 ms.
Geometry support is conditional on sufficient RAM: whole-dwell preparation
has **not** been memory-qualified for 10 MS/s × 360 ms on the attached PLUTO+.
That case fails allocation under a 220,000 KiB process limit; an unbounded
all-geometry test was OOM-killed. All 120 ms saved-data modes were qualified.
See `reports/2026_09_29_arm_strides/README.md` for measured scope and evidence.
The default stride in `ArmGlrtConfigurationV1` is 10 ms. Selection of 20 or
120 ms must be explicit and is persisted in that configuration. The CI16 file
is little-endian, time-major
`rx0_i, rx0_q, rx1_i, rx1_q`; it contains exactly
`rate_hz * dwell_ms / 1000` complex times. Each template contains exactly
`round(rate_hz / 750)` native little-endian complex128 values.

The 10 ms schedule evaluates proposals at every 20 ms anchor and uses neighbor
tracking with the frozen fallback on intervening probes. Sparse schedules
evaluate only their selected anchors. Thus 20 ms probes share anchor
construction with the even 10 ms probes, while a 120 ms dwell at stride 120
contains only the probe starting at zero.

For that two-window geometry, input preparation now converts only the first
20 ms per receiver while still validating the complete 120 ms input buffer.
Clipped-grid conditioned scoring also caches repeated FP64 rotation vectors
within a call. These changes preserve window placement, candidate settings,
and arithmetic; `kernel/provenance.json` identifies the owned change to the
copied scorer. The original dense and longer-dwell preparation paths remain.

## Boundaries and routing

`native_glrt.h` is the public in-memory C boundary. It accepts caller-owned RAM
and returns bounded result structures; it performs no file, database, QNAP,
radio, or network access. The static `libleo-native-glrt.a` can coexist with
the legacy native-presence library because every embedded helper has a
`leo_native_glrt_private_` symbol name.

`native_glrt_cli.c` is the strict saved-input adapter. It emits one JSON
document only after complete success. The Python route
`python -m leo.cli.arm_glrt` additionally validates an
`ArmGlrtInputBindingV1`, hashes the binary, input, and templates before and
after execution, validates the native document, and creates a new output file
without overwriting an existing result. This remains an explicit analysis
command; installing or building it does not enable it in scanner operation.

The frozen kernels contain mutable process-global FFT and phase caches. API
operations are process-serialized and concurrent calls return
`LEO_NATIVE_GLRT_BUSY`. The library never changes CPU affinity. The ARM build
pins only the standalone CLI to CPU 0.

`leo_native_glrt_analyze_profiled` is an additive API for outer-stage CPU and
monotonic-wall diagnostics; the existing analyze entry point remains available.
The maintained `leo-native-glrt-bench` qualification client preloads bounded
saved input buffers, reuses a context, pins CPU0 on ARM, and records call,
serialization, flushed-output and client-cycle timing. It is not a capture
worker. Context creation/readiness must occur before a persistent RAM service
accepts deadline-bound dwells; process-per-dwell CLI costs remain separate.

## Saved-input examples

The native executable has the same arguments at every rate and stride:

```bash
leo-native-glrt \
  --rate-hz 2500000 \
  --exact-template exact-2500000.c128 \
  --control-template control-2500000.c128 \
  --input-ci16 dwell-2500000-120ms.ci16 \
  --dwell-ms 120 \
  --probe-stride-ms 20 > result-2500000-stride20.json
```

This bounded loop shows every supported rate and stride. Each rate names its
own correctly sized templates and saved dwell:

```bash
for rate in 2500000 5000000 7500000 10000000; do
  for stride in 10 20 120; do
    leo-native-glrt \
      --rate-hz "$rate" \
      --exact-template "exact-${rate}.c128" \
      --control-template "control-${rate}.c128" \
      --input-ci16 "dwell-${rate}-120ms.ci16" \
      --dwell-ms 120 \
      --probe-stride-ms "$stride" \
      > "result-${rate}-stride${stride}.json"
  done
done
```

For persisted, hash-bound evidence, invoke the Python route instead:

```bash
python -m leo.cli.arm_glrt \
  --native-binary ./leo-native-glrt \
  --input-ci16 dwell-2500000-120ms.ci16 \
  --exact-template exact-2500000.c128 \
  --control-template control-2500000.c128 \
  --input-binding dwell-2500000.binding.json \
  --rate-hz 2500000 \
  --dwell-ms 120 \
  --probe-stride-ms 120 \
  --timeout-s 300 \
  --output result-2500000-stride120.json
```

## Timing scope

All JSON timing values are process CPU milliseconds from
`CLOCK_PROCESS_CPUTIME_ID`; they are not wall-clock deadlines. `io` covers CPU
spent reading the three files, `setup` covers context construction, and
`detector_cpu` covers prepared-input allocation, required input preparation,
proposal work, all selected searches, and per-call cleanup. It excludes file
reading, context setup and destruction, JSON serialization, process startup,
capture, transfer, scheduling delay and storage latency. Per-row stage timings
are diagnostic subsets and need not sum to the outer detector interval. The
Python `--timeout-s` is a wall-clock failure bound for the subprocess, not a
performance guarantee.

## Reproducible build

The builder consumes only installed/package source under this directory. It
requires Python 3.12 or newer, a C11 GCC toolchain with its LTO-aware
`gcc-ar`, an FFTW prefix containing `include/fftw3.h` and static
`lib/libfftw3f.a`, and a target `libfftw3.so` resolvable by the compiler. The
resulting receipt records source, compiler, archiver, FFTW and output hashes
plus every command and flag. A Cortex-A9 build is:

```bash
python -m leo.qualification.arm_glrt_release \
  --output-dir /absolute/output/native-glrt-arm \
  --work-dir /absolute/work/native-glrt-arm \
  --compiler /absolute/toolchain/bin/arm-linux-gnueabihf-gcc \
  --archiver /absolute/toolchain/bin/arm-linux-gnueabihf-gcc-ar \
  --fftw-prefix /absolute/target/fftw-prefix \
  --target arm-cortex-a9
```

The output contains `libleo-native-glrt.a`, the standalone
`leo-native-glrt`, and `build-receipt.json`. Host builds use `--target host`
with host GCC, `gcc-ar`, and a host FFTW prefix. Fresh PGO is optional through
`--pgo generate|use --profile-dir /absolute/profile-directory`; generate and
use builds must reuse the same absolute `--work-dir`. The use build fails on
absent profiles and treats compiler-reported missing profile data as an error.

The copied numerical closure is bound by `kernel/provenance.json` and has no
runtime dependency on a research report directory. `proposal_core_wrapper.c`
alone retains the measured `-fno-lto` exception; the remaining production
objects use the recorded safe optimization flags without blanket fast-math.
The provenance file retains original hashes and separately identifies owned
modifications. `--with-benchmark` builds the qualification client;
The default sparse path retains its 20 ms prepared input buffers in the context
and reuses them across calls. The exact conditioned screen evaluates four
adjacent regular boundary dots as a tile while retaining each dot's original
FP32 lane and FP64 reduction order. `--disable-prepared-reuse` restores
per-call allocation for the sparse buffers, and `--scalar-boundary-dots`
restores one-at-a-time regular boundary dots. These two release-builder options
are measurement ablations. Sparse input buffers allocate lazily on the first
120/120 call and are released before a different geometry runs. Fine FFT plans
are created with the context and reused; `--disable-fine-plan-reuse` restores
two per-call plan creations for measurement. Lazy input allocation remains
inside the first detector call; context and plan setup is timed separately.
First calls remain in reported detector distributions.
`--full-prep --uncached-boundary` restores the
matched earlier preparation and irregular-boundary behavior.
`--diagnostic-wrap` additionally measures inclusive allocator/FFTW activity;
its instrumentation overhead must not be presented as an ordinary release
timing. Expanded build receipts use a separate schema version.
