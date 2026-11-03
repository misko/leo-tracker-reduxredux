# Single-receiver source-neutral scanner v1

This report qualifies an additive scanner component for one CI16 receiver at
2.5 MS/s. It joins the common source port, existing adaptive scan policy,
120/240/360 ms window assembly, and the separately qualified ordinary
single-receiver GLRT. The legacy two-receiver ABI and entry points are
unchanged. No CLI, application default, USB device, or RF path was enabled.

The public entry point is `leo_scanner_run_source_single_ex` in
`native/adaptive/scanner/scanner_single_source.h`. Its source contract is
deliberately weaker than the PLUTO contract: a software-delivered ordinal and
delivered watermark, frequency attestation, and a valid post-selection
boundary. A target number remains a logical scan-policy key. The scanner clears
provider target and CRC attestations, emits CRC zero, and never labels the
coordinate physical or UTC-qualified. It rejects a single-detector result
before result/candidate events if the row count, receiver, probe geometry, or
candidate count violates the contract.

The fake-provider component test proves both 120→240 ms and 120→360 ms ACTIVE
adaptation. It also covers two detector workers, fail-closed capability
preflight, extra provider attestation removal, malformed detector output, and
discontinuities on each side of the validity boundary. A discontinuity wholly
inside explicitly discarded settling data is ignored for the visit. An
unknown discontinuity overlapping valid samples makes the visit UNKNOWN and
suppresses detector analysis. The original dual profile retains its prior
discontinuity behavior.

The recorded-data test deinterleaves RX0 and RX1 from one positive portable
DS9 dual-receiver dwell. For each view it compares the scanner result with a
fresh direct call to the frozen single-receiver detector, including candidate
count, epoch, scores, CFO fields, proposal decision, and fractional fields.
Host, ASAN/UBSAN, fully instrumented scanner TSAN, ARM cross-build, and physical
ARM CPU-only runs pass. Physical ARM measured 0.417552196 s wall and 9,820 KiB
RSS for the fake suite, and 0.795950840 s wall and 27,608 KiB RSS for the DS9
comparison. [qualification.json](qualification.json) binds sources, detector
archives, fixtures, binaries, and logs.

Rebuild the host component with the frozen detector dependency:

```bash
TMPDIR=/var/tmp/leo-scanner-single-host-tmp \
LEO_SKIP_SCANNER_CLI=1 LEO_REAL_DS9_TEST=1 \
LEO_DETECTOR_STATIC="$PWD/reports/2026_09_30_native_adaptive_deployment/usb/single-rx-detector-v1/build-host/libleo-adaptive-detector.a" \
LEO_FFTW_FLOAT_STATIC=/usr/lib/x86_64-linux-gnu/libfftw3f.a \
LEO_FFTW_DOUBLE=/usr/lib/x86_64-linux-gnu/libfftw3.so.3 \
native/adaptive/scanner/build.sh host /var/tmp/leo-scanner-single-host
```

The physical ARM commands used the staged copies of the two frozen binaries:

```bash
./test-scanner-single-source
./test-scanner-single-ds9 \
  lower-exact.c128 lower-control.c128 \
  607957d70258c2ae53439f9b149821eea15ee95d1863ee5bb845412a2cc3fdc8.ci16
```

The present RTL/Soapy adapter remains unsupported because no provider has yet
proved the required retune-valid delivery boundary. Even after that source
contract is available, current live ingestion requires a nonzero profile CRC
and measured counter/UTC mapping. This component therefore stops at truthful
candidate events; it does not create qualified physical observations or close
the downstream timing contract.
