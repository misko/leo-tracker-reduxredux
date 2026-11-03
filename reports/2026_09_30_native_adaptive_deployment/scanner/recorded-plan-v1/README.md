# Recorded-plan scanner v1

This additive scanner entry point replays an explicit saved visit plan through
the corrected 7.5 MS/s dual-receiver profile.  It preserves the original global
visit IDs, targets, frequencies, and source counters.  It bypasses adaptive SPF
selection, feedback, and acknowledgement.  The adaptive and recorded runners
share the same clipping, window assembly, energy, bounded slot, detector, and
event helpers.

Version 1 accepts only 120 ms visits.  Every row must declare an applied source
selection and the source transition receipt must match the row exactly.  The
causal counter order is
`previous_valid_end <= selection_counter <= transition_valid_start <= valid_start`;
later selections cannot precede the prior visit end.  Nonoverlapping omitted
intervals between rows are outside all dwells and are not counted as gaps.  A
gap inside a dwell still makes that visit incomplete and suppresses detector
submission.

The plan digest is caller-provided attestation.  The scanner requires it to be
nonzero but does not infer a filesystem identity or authenticate saved bytes.
CRC authority is likewise explicit: an unattested historical row carries no
CRC transition flag and a zero CRC.  No UTC authority is synthesized.

## Qualification scope

The focused component test covers two visits numbered 41 and 97 with an omitted
interval, exact emitted source authority, target/frequency/counter preservation,
malformed-plan rejection before scanner source operations, exact transition
mismatch before capture, and a one-sample in-dwell gap.  Host legacy, single-RX,
and corrected-profile scanner regressions pass after the shared-helper
extraction.  ASAN/UBSAN runs the same four tests.  ARM artifacts were cross
built with the production scanner flags.  A further unpaced 20-visit case with
queue capacity one and a delayed detector proves the recorded-only synchronous
drain completes every visit with zero queue drops and high-water one.

The physical result in `physical.log` used the immediately preceding focused
binary (`49f1c262...`).  It passed, but is **superseded evidence** because final
source preflight subsequently added the verified causal counter inequalities
and removed the unused SPF baseline requirement.  It does not qualify the final
source.  The later `physical-final.log` run used binary `f1e3c693...` and passed,
but was superseded when the final audit rejected unrepresentable time-boundary
authority and moved expected-frequency tolerance into preflight.  The final
`physical-final3.log` run used binary `c635bb61...`, includes the 20-visit
lossless-drain case, and passed in 2.899538542 s wall time with 23,352 KiB peak
RSS.  These are CPU-only fake-source tests with no RF.

This component does not claim a full raw DS9 replay, adaptive scheduling replay,
RF capture, detector/server identity closure, UTC qualification, or application
integration.  Those require the separately owned saved-store provider,
corrected detector adapter, geometry provider, and Analysis composition.

## Reproduction

From the repository root, with compiler temporaries outside the quota-limited
`/tmp`:

```sh
TMPDIR=/var/tmp/leo-recorded-compiler-tmp LEO_SKIP_SCANNER_CLI=1 \
  native/adaptive/scanner/build.sh host /var/tmp/leo-scanner-recorded-host-final3
sudo -n /var/tmp/leo-scanner-recorded-host-final3/test-scanner
sudo -n /var/tmp/leo-scanner-recorded-host-final3/test-scanner-single-source
sudo -n /var/tmp/leo-scanner-recorded-host-final3/test-scanner-profile
sudo -n /var/tmp/leo-scanner-recorded-host-final3/test-scanner-recorded-plan

sudo -n env TMPDIR=/var/tmp/leo-recorded-compiler-tmp \
  LEO_SKIP_SCANNER_CLI=1 native/adaptive/scanner/build.sh sanitize \
  /var/tmp/leo-scanner-recorded-sanitize-final3

TMPDIR=/var/tmp/leo-recorded-arm-tmp LEO_SKIP_SCANNER_CLI=1 \
  native/adaptive/scanner/build.sh arm /var/tmp/leo-scanner-recorded-arm-final3
```

The unprivileged host build reaches all binaries and then its legacy test aborts
when glibc `tmpfile()` uses the quota-limited `/tmp`.  The recorded raw log is
retained.  Running the already-built fake-only tests with `sudo -n` avoids that
environmental failure; no hardware or RF is accessed.
