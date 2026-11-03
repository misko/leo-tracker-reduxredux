# Portable native adaptive detector

This directory is the repository-owned compile closure of the maintained native
GLRT detector. It was copied from the source recorded in `SOURCE_LICENSE.md` and
has no runtime dependency on `/var/tmp`, another checkout, a report, QNAP, a
database, or a device.

`native_glrt.h` is the C boundary. An opaque context owns its templates,
workspaces, and FFT plans. Input is little-endian dual-receiver CI16 ordered as
`[sample][receiver][I/Q]`; templates are native little-endian complex128. The
supported rates are 2.5, 5, 7.5, and 10 MS/s, dwells are 120, 240, or 360 ms,
and strides are 10, 20, or 120 ms. The deployment geometry calls
`leo_native_glrt_analyze(context, input, rate * 120 / 1000, 120, 120, result)`;
the 120 ms stride is explicit in the ABI.

Production contexts own their mutable search state, FFT plans, caches, and
scratch and may analyze concurrently. One context permits one operation at a
time; same-context contention returns `LEO_NATIVE_GLRT_BUSY`. FFTW plan
creation and destruction retain a narrow process lifecycle guard because FFTW
planning is not generally thread-safe, so concurrent lifecycle calls may also
return BUSY. Construct contexts before worker launch and destroy them after
their workers join. Per-call CPU timing is calling-thread CPU; wall timing is
monotonic elapsed time. The library does not change affinity or create workers.
Production compilation rejects `LEO_NATIVE_GLRT_DISABLE_FINE_PLAN_REUSE` because
that diagnostic path constructs and destroys FFTW plans during analysis, beyond
the lifecycle guard. All supported production plans are created eagerly.

The optional server-reference build remains process-serialized because its
research wrapper still has mutable process-wide geometry controls. Its build
receipt continues to advertise `process-serialized-busy-on-contention`.

The release build contains the two deployment modes:

- `LEO_NATIVE_GLRT_MODE_ORDINARY` preserves the maintained ordinary output.
  Its additive `fractional_epoch` status is `not_evaluated`, and the JSON values
  that depend on fractional evaluation are null.
- `LEO_NATIVE_GLRT_MODE_ORDINARY_WITH_FRACTIONAL_EPOCH` preserves those
  ordinary fields and evaluates the maintained five-cell epoch lattice for
  every retained candidate at its acquired CFO. An interior concave maximum is
  log-parabolically refined and confirmed by the 16-frame continuous GLRT. The
  status is `complete` or `unbracketed`; unavailable values remain null.

`single_rx_glrt.h` is an additive C boundary for one-receiver sources such as
an RTL-SDR adapter. It consumes native signed-16 samples ordered as
`[sample][I,Q]`, reports one row per probe window, and retains the same
proposal-guided ordinary search and eight-candidate row limit used for either
receiver of `native_glrt.h`. It has its own opaque handle, layout query, and
capability structure; handles cannot be passed to the dual-receiver entry
points. `peer_recovery_available` is false: the single path neither duplicates
nor synthesizes an absent receiver and performs no peer-triggered recovery.
The additive fractional mode is available, while server parity remains false.
The existing dual-receiver ABI and capability response are unchanged.

An explicit `--enable-server-reference` research build adds two diagnostic
modes in a separate compile closure. Keeping these sources out of the release
LTO unit preserves the qualified Cortex-A9 code generation:

- `LEO_NATIVE_GLRT_MODE_SERVER_COVERAGE_FRACTIONAL` is a separate slow
  scientific mode. It bypasses the ordinary Wave4 coarse gate, keeps all eight
  retained native hypotheses, runs the full conditioned CFO lane, and then
  performs fractional epoch confirmation. It does not preserve the ordinary
  candidate inventory and does not claim to port the Python symbolwise
  acquisition.
- `LEO_NATIVE_GLRT_MODE_SERVER_REFERENCE_FRACTIONAL` is an isolated portable
  translation of the deployed symbolwise acquisition. It evaluates the full
  FP64 11-CFO folded-anchor grid without native proposals, retains eight basins
  with the deployed 20-sample/80 kHz separation, runs every supported frame in
  the 500 Hz fine and direct 100 Hz conditioned searches, applies the deployed
  verification ordering, and then performs fractional confirmation. The C ABI
  accepts receiver centers and residual bounds through
  `leo_native_glrt_set_server_reference_geometry`. The component test freezes
  its candidate inventory against the maintained `acquire_symbolwise` result.
  The research setter rejects residual spans above 880 kHz before storing the
  geometry because this profile has twelve coarse-frequency slots. Earlier
  builds accepted spans through 900 kHz even though some such grids need a
  thirteenth endpoint. Wider authority remains a separate research profile.
  This mode does not change either ordinary inventory.

The reference mode is not the complete deployed adaptive wrapper. That wrapper
derives a distinct residual domain for every visit and conditionally reruns a
receiver with 22 fallback anchor symbols when its peer detects. The replay TSV
does not yet carry those per-visit inputs and this detector does not perform the
peer-dependent rerun. Consequently the default-geometry 80-case run is a kernel
qualification only, not server parity or a deployment candidate.

The fractional mode is implemented and structurally tested, but server parity
has not been qualified. `leo_native_glrt_get_capabilities` reports that
distinction explicitly. `refinement_skipped` describes the pre-existing CFO
conditioning/verification lane and is not a fractional-epoch status.

`native_glrt_cli.c` performs one saved-IQ call and emits `leo-native-glrt/v2`.
`native_glrt_replay.c` preloads a bounded TSV schedule, constructs one context,
and emits setup, call, and summary JSONL. Each TSV row has eight tab-separated
fields:

```text
sequence  rate_hz  dwell_ms  stride_ms  exact.c128  control.c128  input.ci16  metadata
```

Sequence numbers start at zero within each schedule. A schedule must contain a
single rate/template context, at most 32 unique inputs, and at most 128 MiB of
preloaded input. `--fractional-epoch` selects the additive mode. The metadata
column is carried as a JSON string without interpretation. Use
`--server-coverage-fractional` for the separate coverage experiment.
Use `--server-reference-fractional` for the translated reference mode.
Those two switches exist only in a build made with
`build.py --enable-server-reference`; the build receipt reports both research
capabilities as false for a release build and true for a research build.

Build the static library, shared library, one-call CLI, and persistent replay
CLI with:

```bash
python3 native/adaptive/detector/build.py \
  --output-dir /absolute/output \
  --work-dir /absolute/work \
  --compiler /usr/bin/gcc \
  --archiver /usr/bin/gcc-ar \
  --fftw-prefix /absolute/fftw-prefix \
  --target host
```

The FFTW prefix supplies `include/fftw3.h` and `lib/libfftw3f.a`; the compiler
must resolve its target `libfftw3.so`. For Cortex-A9 use the matching GCC,
`gcc-ar`, target FFTW prefix, and `--target arm-cortex-a9`. The build receipt
hashes source, tools, dependencies, commands, and these outputs:

- `libleo-adaptive-detector.a`
- `libleo-adaptive-detector.so`
- `leo-native-adaptive-detector`
- `leo-native-adaptive-replay`

The DS9 report contains the 80-dwell manifest, exported replay schedules,
ordinary parity evidence, fractional coverage, generated 7.5 MS/s templates,
and a complete metadata inventory for the location source session. Large CI16
fixtures are hash-bound local artifacts and remain ignored by Git.
