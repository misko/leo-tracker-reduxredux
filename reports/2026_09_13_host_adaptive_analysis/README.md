# Native host-adaptive analysis and PNG publication checkpoint

2026-09-13. Continues capture checkpoint `6e1cff3b`. This is tested application
integration, not production activation or live adaptive qualification.

## Completed path

`capture_host_adaptive_hop_session` admits only the new host-adaptive major and
uses the existing lifecycle implementation through typed ports. The storage
entry point waits for radio closure and the external publication barrier before
sealing its native single-RX recording. Errors preserve cleanup and terminal
evidence without publishing incomplete IQ.

`HostAdaptiveAnalysisSource` admits the native receipt and reads exactly one
physical receiver from payload column zero. Offline analysis uses **10 MS/s**
and the existing fractional GLRT/CFO detector. The online 2.5 MS/s decision copy
is not substituted for native scientific analysis. Actual visit order, gaps,
fractional timing and integer counters beyond 2^53 remain authoritative.

New major-2 configuration, visit, binding, reference, metrics, overview and status
contracts keep published legacy majors closed. Native checkpoints use `.v2`
paths within their source/configuration digest. Both old and new stores retain
bounded, immutable, hash-verified reads and atomic publication. Four native
analysis workers read IQ only through the owner; partial batches checkpoint
successful earlier visits and resume only missing work. Legacy jobs retain their
two-worker maximum.

The overview uses only sealed native metrics, renders the selected physical RX,
and keeps actual target/candidate associations. All three PNGs carry native
rate, decision rate, physical RX, detector configuration, binding and metrics
identity. Visible labels distinguish native 10 MS/s recording from 2.5 MS/s host
decisions and display duty, accepted-feedback count and observed policy fallback.
Candidate association lines remain explicitly distinct from satellite IDs.

The existing analysis CLI dispatches by the published capture major. Native
captures use `--host-maximum-workers` (default 4, range 1..4); legacy
`--maximum-workers` remains 1..2. Pending selection and retries can finish metrics
and PNGs without re-reading IQ or repeating completed analysis. No new scheduler
or database job system was added.

## Evidence

The final focused suite passed **182 tests in 17.02 seconds**:

```sh
.venv/bin/python -m pytest -q --tb=short \
  tests/scanner/test_host_adaptive_application.py tests/scanner/test_adaptive_hop_application.py \
  tests/scanner/test_host_adaptive_analysis.py tests/scanner/test_adaptive_hop_analysis.py \
  tests/scanner/test_adaptive_hop_products.py \
  tests/application/test_host_adaptive_analysis.py tests/application/test_adaptive_hop_analysis.py \
  tests/application/test_adaptive_hop_overview_service.py \
  tests/storage/test_adaptive_hop_analysis_source.py tests/storage/test_host_adaptive_analysis.py \
  tests/storage/test_adaptive_hop_analysis.py tests/storage/test_adaptive_hop_overview_store.py \
  tests/cli/test_host_adaptive_analysis_cli.py tests/cli/test_adaptive_hop_analysis_cli.py
```

An earlier projection/rendering and overview-store matrix passed **41 tests in
86.84 seconds**, including `tests/presentation/test_adaptive_hop_overview.py`.
Ruff, mypy for all fourteen changed production modules, and `git diff --check`
passed. Scientific golden fixtures and sealed host DSP code were unchanged.

The new tests include both physical RXs and modes, a synthetic producer-to-store
run, cleanup/publication failures, native-rate detector serial/parallel parity
on a synthetic repeated pilot, exact counter/fractional mapping, source mismatch
rejection, four-worker resumable checkpoints, mixed-major refusal, PNG decoding
and metadata verification, and native CLI partial/metrics/figures/idle progress.
The synthetic pilot verifies numerical execution/parity, not RF sensitivity or
false-alarm performance. These tests do not establish full 300-second native
adaptive analysis throughput or live radio feedback timing.

Read-only production observation: the 19:00 UTC **fixed** scan published 2,386
visits with 954,233 ppm valid duty. Acquisition remained active and the 19:10
operation was leased at the last check. No production release, profile, radio,
worker service or firmware was changed during this checkpoint.

## Still required

- Wire the durable native adaptive intent and source-pinned engine into real
  scheduler admission and capture dispatch, preserving leases and ten-minute
  slots. Keep radio `104000bac4950008230026001b440a003a` as the sole RF target.
- Add new-major history/detail/API/UI presentation and native refinement /
  trajectory/TLE reader support. The CLI's published PNGs do not prove that the
  current production web API can serve these new recordings.
- Qualify representative saved native data for complete analysis cadence; fix
  measured throughput issues without changing the frozen online detector.
- Package/verify compatible provider, PPU, native library, templates and filter;
  run the four reserved live canaries, deploy between scans, and verify the
  first scheduled adaptive scan through all required analysis and browser assets.

No RF collection was added. The previous ledger remains 237.331441 seconds
charged, 1,562.668559 remaining, with 1,500 seconds reserved for the five live
qualification/verification scans. The deployment goal remains incomplete.
