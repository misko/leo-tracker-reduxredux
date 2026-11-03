# Corrected detector scanner profile v1

This component adds an opt-in scanner boundary for the corrected dual-receiver
7.5 MS/s detector profile.  Existing scanner ABI v2 structures and entrypoints
are unchanged.

The new `scanner_profile.h` contract separates two different qualified counts:
22 coarse-CFO storage slots and 22 peer-fallback anchor symbols.  A source-bound
geometry callback runs after transition validation and before capture.  Its
value-owned result is copied into the bounded detector slot, including receiver
centers, residual bounds, a profile-manifest digest, and a per-visit authority
digest.  The detector worker receives that immutable copy.  Version 1 accepts
only dual receiver, 7.5 MS/s, 120 ms dwell, 20 ms probes at 120 ms offsets, one
serialized detector worker, and a detector-declared 1.6 MHz maximum residual
span.  The qualified DS9 `[-800000,+800000]` geometry is accepted.  Server
parity remains a truthful boolean capability; false is accepted and propagated
to candidate events.

The focused test covers two queued visits with different geometry while the
first detector call waits, exact 1.6 MHz acceptance, over-wide rejection,
negative and unexpected-positive derive failures, non-finite centers, reversed
bounds, zero authority digest, wrong probe layout, profile-manifest mismatch,
malformed parity/serialization capabilities, transition target/frequency
mismatch, and legacy event parity propagation.  Every geometry failure occurs
before source capture or detector invocation.

Host and sanitizer focused tests passed.  Existing host and sanitizer scanner
and single-source suites also passed when invoked through `sudo -n`; glibc
`tmpfile()` ignored `TMPDIR` and the unprivileged `/tmp` quota caused their
otherwise unrelated JSON serialization test to fail at `fflush`.  The root
invocations used the exact rebuilt archives and required no hardware.

The physical ARM focused fake-provider test passed in 0.895 s CPU and 30,524
KiB maximum RSS.  It did not access RF or detector hardware.  See
`physical.time.json` and `installed-sha256.txt`.

This slice does not promote or link the corrected research detector and does
not change the portable live application.  The corrected adapter must live in
a separate explicitly named executable that links the corrected archive in
place of the ordinary archive; the two current detector archives export
incompatible structures and overlapping symbols.  Offline DS9 replay also
needs an additive recorded-plan runner.  Repeated one-visit adaptive runs reset
visit IDs, while an adaptive multi-visit run may choose a different target
order; neither is a truthful substitute for recorded visit authority.

## Reproduction

Builds used `native/adaptive/scanner/build.sh` with `LEO_SKIP_SCANNER_CLI=1`
for `host`, `sanitize`, and `arm`.  Because the build script executes the
legacy host tests before returning, the final current-source archives were
relinked explicitly and the tests were run as:

```sh
sudo -n /var/tmp/leo-scanner-profile-final-host/test-scanner
sudo -n /var/tmp/leo-scanner-profile-final-host/test-scanner-single-source
/var/tmp/leo-scanner-profile-final-host/test-scanner-profile

sudo -n env ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
  /var/tmp/leo-scanner-profile-san/test-scanner
sudo -n env ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 \
  UBSAN_OPTIONS=halt_on_error=1 \
  /var/tmp/leo-scanner-profile-san/test-scanner-single-source
ASAN_OPTIONS=detect_leaks=1:halt_on_error=1 UBSAN_OPTIONS=halt_on_error=1 \
  /var/tmp/leo-scanner-profile-san/test-scanner-profile
```

All six commands exited zero with empty stdout/stderr.

`source/` freezes the four component-owned changed files. `artifacts/` retains
the host, sanitizer, and ARM focused binaries and scanner archives. `logs/`
retains the raw empty success streams and the rejected unprivileged build-run
log that records the unrelated `/tmp` quota failure. `frozen-manifest.sha256`
binds all 17 files; `source-manifest.sha256` additionally binds unchanged
scanner headers and legacy tests used by the build.
