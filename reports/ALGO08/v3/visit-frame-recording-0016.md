# Standard-format visit frames for the complete staged DS30-0016 recording

The conventional writer sealed **808 visits across 13 members** with per-visit Zstandard frames and separate authenticated seek tables. Writing both segments and the detached authority took **2.046 s elapsed**. The unmodified installed reader independently recovered all the original indexed windows and whole-member hashes, and the optional seek reader independently decoded all 808 committed prefixes. The child used a fresh ordinary source identity. [Measurement receipt](measurements/visit-frame-recording-0016.json) · [Detached authority](measurements/visit-frame-recording-0016-authority.json)

| Measured phase | CPU (s) | Elapsed (s) |
| --- | ---: | ---: |
| Authenticate staged inputs and hydrate owned windows, one member at a time | 2.166870 | 2.167080 |
| Standard writer constructor, input and sealing, both segments | 2.044815 | 2.044873 |
| Write and sync the 13 optional seek tables | 0.001451 | 0.001451 |
| Seal and sync the detached recording authority | 0.000161 | 0.000161 |
| **Writer, seek tables and authority** | **2.046427** | **2.046485** |
| Independent installed full readback, including reference prefix hashes | 2.576440 | 2.576540 |
| Independent full-authenticated seek prefix checks | 1.622308 | 1.622378 |

Both readbacks were separate from writing and from raw analysis. The prefix verification authenticated all **991,704,602 encoded bytes** and decoded **517,120,000 bytes**, feeding 396,672,304 compressed bytes to the decoder. It compared the prefixes with digests independently computed from the installed reader's full-window results. The original 512-visit rotation and the 296-visit faulted final segment retained their original status, reason, fault, configuration and RF/time index metadata. The new manifests carry new writer lifecycle timestamps, and the authority preserves both sets. [Staged checks and verified counts](measurements/visit-frame-recording-0016.json) · [New and original lifecycle](measurements/visit-frame-recording-0016-authority.json)

### Format and identity

The research driver calls the installed `ShortWindowWriter` constructor, append and finish. Within the private rehearsal, it supplies the qualified `VisitFrames` payload sink. The ordinary writer still seals ordered index rows and whole decoded hashes, and writes and syncs its usual `manifest.json`. The first emitted member reproduces the exact compressed digest from the signed single-member proof, which stopped both sidecar corruption and a genuine unused short suffix corruption before serving any visit. The full-recording sidecars use `visit-frames-XXXXXX.json` and bind the actual conventional segment manifest, member index, member compressed digest, chronological visit sequence and its prefix extents and SHA-256. Positions are member-relative and visit numbers are segment-absolute. The external authority authenticates the sidecar hashes in ordinary segment/member order. It is published after independent readback. [Writer and validation](visit_frame_recording_0016.py) · [Signed single-member qualification](frame-visit-0016.md) · [Generalized selective reader](frame_visit_0016.py)

All **13 compressed digests changed** compared with the original staged frames, with total encoded payload **29,995 B smaller**. All original index and uncompressed member digests agree. The entire ordinary-compatible archive and its optional tables occupied **994,061,776 B**, **128,095 B** more than the staged original. The one-member owned-buffer and output accounting topped out at **1,074,854,564 B** against the 1.6 GB bound. All measured scopes recorded zero input blocks and zero major faults. This is a tmpfs file and directory sync boundary. Power-loss persistence on the recording filesystem is outside the run. [Byte and clock evidence](measurements/visit-frame-recording-0016.json)

| Identity | Original | Visit-frame archive |
| --- | --- | --- |
| Ordinary inventory SHA-256 | `e22b918df63370a0590757b70f71a0e620792cf90cf78a833e601af7a0b395a6` | `c542d45d28d2ed8894a5b67695154b632d93bf5f61dc92bea54fef028c13549f` |
| Ordinary raw authority SHA-256 | `64e945e9717c2612fdb3118d7b65c713076a1b56f5de49f8fdf291a3220fc252` | `af1c330c67b47d59dabe62aefd2f1b1fabf9ad22d95b366946f60847a780582b` |

The new ordinary inventory allocated `fast-c542d45d28d2ed8894a5b67695154b63` to the recording at `/dev/shm/leo-v3-frame-visit-0016-recording01/recording-688de432d5ba473087247a6cbc8b5cb8`. Its detached authority SHA-256 is `afb5a48420d0c1ab9d021e61aab59e3898298b27b0a998fd193dd823ef2383a3`. The receipt SHA-256 is `bf246173e0a702ac89cc1a589e6db57388fe65a60f436b77c747ad05b33e3ebc`. These identities belong to the new archive. Equivalent decoded words and original index hashes establish the scientific input match. [Detached authority](measurements/visit-frame-recording-0016-authority.json)

### Reproduce

The measured writer is commit `9cb5fd51` with the `e33625bc1` readback interface. The job used staged resident tmpfs source files and one CPU 2 slot at nice 15, best-effort I/O priority 7 and one numerical thread. The first bootstrap stopped at decorated-function source inspection before creating an output or opening staged waveforms. The corrected job emitted one archive and ran no receiver or solve. Twelve tests cover writer, corruption qualification and multi-member access, including an all-empty member followed by zero, shortened and complete visits. [Tests](../../../tests/pipeline_eval/test_visit_frame_recording_0016.py)

```sh
repo=/dev/shm/leo-v3-frame-visit-0016-recording
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
out=/dev/shm/leo-v3-frame-visit-0016-recording-replay

sudo -n systemd-run --quiet --wait --pipe --collect \
  -p User=leo -p Group=leo -p Nice=15 -p CPUAffinity=2 \
  -p IOSchedulingClass=best-effort -p IOSchedulingPriority=7 \
  /usr/bin/flock -x -w 180 /tmp/leo-algo08v2-2x-bench/gauss.lock \
  /usr/bin/env PYTHONPATH="$repo:$repo/reports/ALGO08/v3:$release/src:$release:$payload" \
  PYTHONDONTWRITEBYTECODE=1 OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 \
  OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  /usr/bin/timeout 60s "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.visit_frame_recording_0016 "$out"
```
