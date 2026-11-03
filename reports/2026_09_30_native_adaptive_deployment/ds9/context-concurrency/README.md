# Production detector context concurrency

The production ordinary and additive fractional detector modes now permit
independent contexts to execute concurrently. Each context owns its regional
epoch inventory, conditioned-screen phase cache, proposal/search/fine FFT
plans and scratch, and prepared dwell buffers. A per-context atomic guard
returns `LEO_NATIVE_GLRT_BUSY` on same-context contention. The library creates
no worker threads.

FFTW plan creation and destruction remain behind one narrow process lifecycle
guard because FFTW planning is not generally thread-safe. Callers should build
all contexts before launching workers and destroy them after joining workers.
Concurrent lifecycle calls may return BUSY. The production build rejects
`LEO_NATIVE_GLRT_DISABLE_FINE_PLAN_REUSE`, whose fallback would create and
destroy a plan during analysis. The unused conditioned-CZT object, including
its former process cache and `atexit` destructor, is no longer linked. No
`fftw_cleanup` or `fftwf_cleanup` call exists in the detector.

Library CPU fields now measure the calling thread with
`CLOCK_THREAD_CPUTIME_ID`; their names and binary layout are unchanged. Wall
fields remain monotonic elapsed time. Replay-level whole-process accounting
continues to use process CPU. The published contract described these values as
CPU time without promising process scope, so the change does not alter the
persisted ABI. It prevents concurrent detector calls from charging each other.

`test_context_concurrency.c` covers independently owned ordinary and
fractional contexts on two distinct positive DS9 dwells, same-context BUSY
behavior, and concurrent 2.5/7.5 MS/s contexts. Both positive sequential
oracles must contain candidates and differ; each concurrent result equals its
own sequential result after only diagnostic timing is removed. The complete
detector test file passed 17 tests in 15.79 seconds. The same harness passed a
host ThreadSanitizer build with `TSAN_OPTIONS=halt_on_error=1`; every
detector-owned translation unit was instrumented, while the external FFTW and
system libraries were not.

The portable DS9 panel was replayed through the prior frozen host release and
this build in ordinary and additive fractional modes. All 80 calls in each
mode match exactly after CPU/wall/RSS/thermal diagnostics are removed:

- ordinary projection SHA-256:
  `5ec930e6547a83d87dc86deeb498bdd7a39420279e76ae95172824fddd9ee581`
- fractional projection SHA-256:
  `3fa4134c1196aff9102e99c81df355c49b358ac81406e02bd3ffd0c300e06252`

Regenerate the comparison after replay logs exist with:

```sh
python3 reports/2026_09_30_native_adaptive_deployment/ds9/context-concurrency/compare_portable80.py \
  reports/2026_09_30_native_adaptive_deployment/ds9/context-concurrency \
  reports/2026_09_30_native_adaptive_deployment/ds9/context-concurrency/portable80-parity.json
```

Host `/proc/self/status` measurements after one analysis per context show a
7,948 KiB marginal RSS increase for the second warmed 2.5 MS/s context in both
modes. The first context adds 12,592 KiB ordinary or 12,724 KiB fractional,
which also includes process-level FFTW/allocator initialization. These host
figures are sizing evidence, not a PLUTO RSS guarantee.

Frozen artifacts:

- `build-host/`: qualified host static/shared libraries and CLIs.
- `build-arm/`: Cortex-A9 cross-build; not physically run for this change.
- `qualification.json`: hashes, test outcomes, lifecycle audit, and limits.
- `qualification-supplement.json`: strengthened distinct-dwell race test,
  fully instrumented TSAN provenance, and ARM CPU-only test binaries.
- `portable80-parity.json`: exact non-timing 80-panel comparison.
- `host-context-rss.json`: one/two-context host RSS measurements.

The server-reference research closure still compiles and remains explicitly
process-serialized because its geometry controls are process-wide. Production
capabilities report `process_serialized=0`; research capabilities retain
`process_serialized=1`. Scanner/application integration and physical ARM
qualification remain outside this component receipt.
