# Accelerated original receiver command

`tools.pipeline_eval.original_receiver` replays authenticated saved 10 MS/s dual-CI16 I/Q using the capture’s installed original `FastScanPolicyV2`, the prepared FFT kernel and the qualified conditioned and fractional refiners. Complete detector output from the measured shards feeds the compact position release in both calibration arms. The command writes results and receipts locally. Geographic scoring is a separate evaluation. [Prepared kernel and exactness tests](../original-kernel/README.md) · [Existing complete prepared waveform study](../prepared-waveform/README.md)

```sh
.venv/bin/python -m tools.pipeline_eval.original_receiver \
  --case DS26-0237 --out /var/tmp/original-ds26-0237 \
  --cpus 0 1 2 3 4 5 6 7 --raw-limit 600 --position-limit 180
```

The receiver accepts available, distinct CPU numbers and a new output directory outside the recording archive. Each raw worker has a 512 MiB charged cap, zero swap, one pinned CPU, one numerical thread and its own deadline. The compact fit has the same memory cap and uses the first selected CPU. Both service limits accept 1–600 seconds. `source-lock.json` binds the producer, staged read-only kernel copies and both numerical and acquisition inputs. `summary.json` records stage completion and authenticated terminal receipts. The full path constructs `native.json` only after every chunk authenticates and the original capture validity matches the signed indexes. `position/position.json` carries both arms on a successful fit. Interrupted or failed workers retain their logs and receipts.

## Supply a recording locator

Pass `--input` with the trusted SHA-256 of its exact bytes. The [example locator](example-input.json) identifies the existing DS29-0174 waveform independently of benchmark ID resolution. Its [truth-free request template](example-request.json) leaves the native input, derived run identity and output path for the receiver to fill. It needs the capture session and run IDs, each saved segment manifest and its SHA-256, the scheduled visit count, the offered region, and a request file with its digest. Relative request paths resolve beside the locator. The request supplies the original baseline role, the same session and offered region, the bound TrackConfig, and a directory containing exactly the listed causal TLE snapshots. A template can omit the previous native locator or any prior scientific detector products. A frozen benchmark case additionally checks the historical request’s native digest declaration against its case receipt.

```sh
.venv/bin/python -m tools.pipeline_eval.original_receiver \
  --input reports/2026_11_19_receiver_screening/original-support/receiver-command/example-input.json \
  --input-sha256 f1e73480f5552bdabbd948e51eb22c76adbe73bbb1c9a35acfb665f2ed8c5bad \
  --out /var/tmp/original-saved-iq-smoke --cpus 9 --raw-limit 90 --smoke
```

The saved segments must retain their canonical locations under the supported archive, complete integer-RF capture metadata, and the version-2 10 MS/s, 20 ms, two-receiver format. Producer resolution uses the signed manifest inventory and a matching installed release and interpreter. The host needs the read-only `leo` archive account, a working systemd user manager, and the pinned x86-64 kernels and compact phase-release installation. An alternate `--kernel-dir` must carry the same qualified `original_kernel.so`, `capture_batched_fft.so`, `conditioned.so` and `fused.so`. An alternate `--receiver` must carry the same verified compact runtime and native source. These checks keep the package within its measured producer and executable scope.

## Measured launch checks

The two actual command smokes use the first authenticated chunk of each saved recording. They are incomplete waveforms and position is unmeasured. The explicit locator verified the screened producer and supplied neither a previous native locator nor scientific packets. An authenticated locator giving an unknown producer run ID was rejected before a worker or output directory was created. Initial setup attempts stopped before reading IQ when the archive interpreter imported plotting dependencies or could not read the checkout binary. The final command loads its assembly helpers only in the coordinator and stages verified read-only libraries for the worker. [Smoke and rejection receipts](smoke-evidence.json)

| Input mode | Core | Visits replayed / recorded | Valid / original invalid | Prepared grids | Raw wall |
| --- | ---: | ---: | ---: | ---: | ---: |
| Frozen case DS29-0082, legacy producer | 8 | 64 / 6,772 | 48 / 16 | 109 | 43.99 s |
| Authenticated locator for DS29-0174, screened producer | 9 | 64 / 6,774 | 64 / 0 | 141 | 47.19 s |

## Complete post-raw handoff

The normal command’s shard verifier assembled all 6,768 recorded DS26-0237 visits from the existing eight completed prepared detector workers. It retained 6,766 valid and two capture-invalid visits. A truth-free locator and request template with no archived native input then bound the newly assembled native SHA-256 and launched the normal compact service. The fit took 47.16 s of service wall and 46.88 s of CPU on core 0, with 355.21 MiB charged peak under 512 MiB and zero swap. Both positions and conditional RMS values matched the independently executed prepared study exactly. Conditional RMS was 80.6700 Hz at `c = 0` and 80.6079 Hz with fitted `c`. This check reused authenticated raw shards and measured the complete assembly-to-position handoff. [Full post-raw receipt](full-handoff.json)
