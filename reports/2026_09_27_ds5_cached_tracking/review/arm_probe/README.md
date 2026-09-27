# ARM stateless saved-IQ probe

This package prepares a later Cortex-A9 component benchmark without contacting a
radio or target. It compares three hash-pinned executables under the same current
research detector flags:

* `packed_builtin_fp64`: common packed single-RX blind dwell with the built-in
  FP64 FFT;
* `packed_fftw_fp64`: the same packed path with target FP64 FFTW, retained as a
  non-strawman production-backend reference;
* `aligned_v5_fftw_fp32`: aligned dual-RX V5 ingress with the research static
  FP32 FFTW archive.

Each executable reads one full 120 ms dual-RX saved-IQ visit, creates two
workspaces outside the timed region, performs one warmup, then records three
repetitions. A repetition processes RX0 and RX1 serially, performs all six rank
screens and one blind confirmation per RX, and writes the complete rank,
confirmation, nuisance, candidate, grid, and native stage timing structures.
`CLOCK_PROCESS_CPUTIME_ID` and `CLOCK_MONOTONIC` surround C packing and detector
calls. Mapping/page-in and workspace/FFTW initialization are reported separately.
For packed methods the full dual-to-single-RX copy is explicitly timed; V5's
selected-window copy remains inside its detector total.

`plan.json` selects by metadata only: two consecutive development visits at each
supported rate and the 12 matching 2.5/5 MS/s controls from the prior frozen
suite. It contains no holdout case. `prepare.py OUTPUT` verifies source NumPy
hashes before and after reading and writes a transport bundle. `run_bundle.py`
rotates the three process orders across cases, verifies bundle and executable
hashes before execution, and rechecks input hashes afterward.

Builds use the existing Buildroot Cortex-A9 hard-float toolchain. No package is
installed. The candidate statically links the provenance-checked research
`libfftw3f.a`; the FP64 reference records and dynamically requests the target
`libfftw3.so.3`. `build.receipt.json` pins the compiler, profile flags, all
scientific sources, FFT libraries, provenance receipt, commands, and binaries.

The two-case `qemu.functional.json` receipt exercises actual ARM/NEON code for a
development visit and pilot railguard. It establishes deterministic execution,
matching rank/window/candidate structure, and the existing 2 us/8 kHz identity
bounds. QEMU measurements are explicitly invalid for performance.

On a later authorized target, stage the prepared bundle, these three binaries,
and `run_bundle.py` in a scratch directory. Do not connect the radio. Run against
saved IQ only, in an otherwise idle serialized session. The resulting comparison
is a stateless detector-component benchmark. It excludes capture, queueing,
causal cache misses/fallback, Python orchestration, and the production scanner's
11-probe/all-candidate policy, so it cannot establish whole-pipeline or deployed
10x performance by itself.

## Strict remote execution adapter

`remote_run.py` is the host-side adapter for a later authorized saved-IQ timing
run. The target firmware contains no Python, so the adapter schedules the C
executables from the host. It acquires `/run/leo-adaptive-pipeline.lock`
nonblocking before the normal capture authority lease and PPU serial lock. A
running scheduled capture therefore causes a refusal; the adapter never stops,
changes, or waits through the production timer or service.

Execution requires a root-readable binding JSON with exactly this schema:

```json
{
  "schema": "org.leo.research.arm-stateless-remote-binding/v1",
  "host": "192.168.1.20",
  "serial": "1040005e0b100007100010000bf33a5d4d",
  "firmware": "v0.59-plutoplus-spf-dual-rx-counter-fix",
  "fit_sha256": "CURRENT_64_HEX_FIT_HASH",
  "qspi_sha256": "CURRENT_64_HEX_QSPI_HASH",
  "deployment_receipt": "/absolute/current/deployment-receipt.json",
  "deployment_receipt_sha256": "64_HEX_RECEIPT_HASH",
  "deployment_receipt_id": "CURRENT_RECEIPT_ID",
  "known_hosts": "/absolute/current/known_hosts",
  "known_hosts_sha256": "64_HEX_HOST_FILE_HASH",
  "password_file": "/absolute/password-file"
}
```

Authentication is exactly one of `password_file` or `identity_file`. Identity
authentication forces `BatchMode=yes`, `IdentitiesOnly=yes`, disables the SSH
agent, and never forwards an agent. Password authentication uses the same
strict pinned-host route without reading the secret into the receipt.

The runner rejects extra fields, stale firmware, FIT/QSPI hashes, receipt ID,
host-key rotation, host, or serial before opening SSH. The reviewed
`remote_binding.v059.json` identifies the September 26 v059 deployment receipt,
its exact FIT/QSPI return attestation, and its rotated root-owned host key. The
older v058, r30, and v0.49 receipts are invalid.

The runner stages only the cases selected by `--case-limit`, their templates,
the three receipt-matched binaries, and the exact FP64 FFTW library into a
generated `/tmp/leo-arm-stateless.XXXXXX` directory. It requires 160 MiB of
available RAM and 96 MiB in `/tmp`, hashes every file remotely before and after,
runs a rotated method order, validates every complete dual-RX JSON result, then
removes only the registered paths and scratch directory. Existing deployment
helpers attest identity, idle buffers, and TX safety before and after.

`--max-seconds` is capped at 90 seconds to fit an idle cadence slot. Each target
process also has a watchdog derived from the remaining whole-run budget. The
runner requires the production service to be inactive and the next timer event
to be more than the requested deadline plus a 15-second safety margin away.
`--case-limit 16` is the complete 48-process plan; the default four-case run is
an explicitly labeled 12-process bounded-prefix receipt. The overall deadline
includes staging, both attestations, execution, and cleanup. Example, only after a
current binding has been reviewed and an idle slot is available:

```sh
sudo -n env \
  PYTHONPATH="$PWD/src:/home/mouse9911/gits/pluto-plus-utils-feature-103/src" \
  /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python \
  reports/2026_09_27_ds5_cached_tracking/review/arm_probe/remote_run.py \
  --binding "$PWD/reports/2026_09_27_ds5_cached_tracking/review/arm_probe/remote_binding.v059.json" \
  --bundle /tmp/leo-arm-probe-bundle-20260927-1 \
  --output /absolute/new-empty-output-directory \
  --case-limit 4 --max-seconds 90
```

The latest read-only preflight is recorded in `PREFLIGHT.md`. It stopped before
SSH because `LocalCaptureAuthority` reported an operator pause. The runner must
not bypass or resume that authority state.
