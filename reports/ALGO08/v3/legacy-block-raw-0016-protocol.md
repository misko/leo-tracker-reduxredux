# Original DS30-0016 mixed legacy block read protocol

Use the complete already staged DS30-0016 capture, the original signed offer and the 46 causal snapshots. Bind the staged directory read-only at its original recording path in one private mount namespace. The installed inventory, acquisition authority and recording title must retain the original identity. Verify the exact staged admission receipt, canonical recording, all 28 resident manifest/index/payload files and the earlier causal portable index. Exit if any required source or page is unavailable. Preserve the original waveform bodies and layout. [Source custody and original paired reference](history-risk-0016-cairo.md) · [Earlier causal index and conservative renderer](frame-portable-0016.md)

Build only detached maps in fresh private tmpfs. During one installed reader pass, authenticate the original index and encoded snapshot, exhaust every ordinary window and the whole decoded member hash, and census all 13 exact in-process snapshots. Compute each eligible prefix digest as its original window passes. Publish each map after installed iteration reaches EOF and bind the ordered map pins to the actual original inventory. Verify observed eligibility against census SHA-256 `6f9fc7a4469b34c744fea8fedc1ee3b04a6b9e61f9e1401c8a6fda9ff52c567b`. Five members carry 320 issued visits and 393,072,334 compressed bytes. The other eight use the full ordinary authenticated reader for 488 visits. A present corrupt or inconsistent map fails the run. [Qualified member reader](legacy-block-seek-protocol.md)

Measure one ordinary then one indexed original-input child. Both use the bounded compressed prefetch, exact 20/8 receiver, earlier portable orbit index with history-risk, and conservative residual Cairo/layout with the four unchanged ordinary orbit figures. The sole science input option difference is the indexed child's pinned map table and decoder. Retain each original member authentication and matching aperture checks. Compare exact native bytes and ordered probes, source authorities, both calibration positions and RF, ordered owners, complete 179-point grid, path, and all eight encoded PNG and RGBA digests. Require the actual rendered title to equal the original recording name in both arms. Verify portable activation and its cold completion, renderer activation and the published sidecar bindings from real output. Keep the already measured installed v3 as a historical reference.

Run one low-priority task on CPU 2 at nice 15 and best-effort I/O priority 7, numerical threads 1, under the common Gauss lock. Give the controller a 65 s deadline and each existing child its inherited 75 s limit. Report both child wall/CPU through exit with authenticated raw acquisition and publication phases, prepared and first-use clocks, distinct complete validation and incremental map CPU/wall, compile and past portable producer separately. Keep offline sealing and scientific scoring outside the child clocks. The extra map cost is instrumented within the common full validation pass and includes the write/sync stages. Execution uses the existing tmpfs copies with no new waveform files, cache clearing, RF acquisition, backing waveform reads or scene export.

```sh
repo=/dev/shm/leo-v3-legacy-block-raw-0016
stage=/dev/shm/leo-v3-guarded-selective-0016-stage01
name=fast8-auto-20261113-112146-b04f5461-1-lower
original=/srv/bulk/leo/fast-scan-recordings/$name
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
out=/dev/shm/leo-v3-legacy-block-raw-0016-result02

sudo -n systemd-run --quiet --wait --pipe --collect \
  -p User=leo -p Group=leo -p Nice=15 -p CPUAffinity=2 \
  -p IOSchedulingClass=best-effort -p IOSchedulingPriority=7 \
  -p BindReadOnlyPaths="$stage/$name:$original" \
  /usr/bin/flock -x -w 180 /tmp/leo-algo08v2-2x-bench/gauss.lock \
  /usr/bin/env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  /usr/bin/timeout -k 2s 65s "$release/venv/bin/python" -IB \
  "$repo/reports/ALGO08/v3/legacy_block_raw_0016.py" launch "$out"
```
