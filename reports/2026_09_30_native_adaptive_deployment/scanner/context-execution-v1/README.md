# Scanner context execution v1

This receipt qualifies the additive scanner execution API with one to four
borrowed detector contexts. Legacy entrypoints and public structures retain
their existing behavior. The new entrypoints validate every binding and its
reported capabilities before the first source callback, bind a stable context
to each executor worker, drain accepted work before return, and account for
queued, active, and acquisition dwell ownership in the memory guard.

The configuration digest is caller attestation. It must cover the detector
build and algorithm, sample rate, exact/control template hashes, and selected
mode. The scanner checks nonzero equality across bindings and does not claim to
inspect the contexts behind those bytes. Worker count is explicit and bounded
to four so an application can share a deliberate CPU budget with tracking and
other work.

The fake-source suite exercises one, two, and four contexts, concurrent routing,
two active plus four queued admission, queued-only high water, detector failure,
partial validation failure before source access, serialized event callbacks,
and drain with no callback after return. The DS9 test uses the lower templates
and two distinct positive 120 ms dwells. It compares serial and two-context
scanner events keyed by visit and requires byte equality after clearing only
enqueue, start, finish, queue, and runtime telemetry.

Host, ASAN/UBSAN, and fully instrumented scanner/runtime TSAN tests passed. The
DS9 TSAN executable links the separately qualified detector and FFTW closures,
which are not TSAN-instrumented; the fake test covers the scanner-owned closure.
The ARM binaries cross-compiled and then passed CPU-only physical tests. See
`qualification.json` and `physical-arm/receipt.json` for exact hashes and
measurements. This evidence does not install or enable multiple scanner workers
in the application and does not include RF.

Rebuild the host qualification with:

```bash
LEO_SKIP_SCANNER_CLI=1 LEO_REAL_DS9_TEST=1 \
LEO_DETECTOR_STATIC="$PWD/reports/2026_09_30_native_adaptive_deployment/ds9/context-concurrency/build-host/libleo-adaptive-detector.a" \
LEO_FFTW_FLOAT_STATIC=/usr/lib/x86_64-linux-gnu/libfftw3f.a \
LEO_FFTW_DOUBLE=/usr/lib/x86_64-linux-gnu/libfftw3.so \
native/adaptive/scanner/build.sh host /tmp/leo-scanner-context-host
```

The physical DS9 invocation used the ARM test plus these four arguments:

```text
lower-exact.c128 lower-control.c128 \
607957d70258c2ae53439f9b149821eea15ee95d1863ee5bb845412a2cc3fdc8.ci16 \
d302949a8ce74cc8ef27d24acffe89266847a34c9795e895d086c7fd703443fd.ci16
```
