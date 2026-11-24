# Live short stereo schedule on the first dense DS30-0008 member

The frozen live schedule saved **38.3–39.3 ms CPU (12.8–13.3%)** through one complete verified original DS30-0008 member. It omitted 16 of 56 short stereo detector opportunities while keeping all eight full anchors. The receiver returned 49 of the original 67 factors. All retained measurements and omitted opportunity rows matched the exact independent mask of the signed dense reference. [Frozen protocol](live-stereo-0008-protocol.md) · [Timing and verification receipt](measurements/live-stereo-0008.json.gz) · [Live probe rows](measurements/live-stereo-0008-probes.json.gz)

| Arm | Issued / admitted / excluded | Full / short / omitted visits | Paid full / short radio calls | Selected full / short factors | Ordered probe rows |
|---|---:|---:|---:|---:|---:|
| Unmasked | 64 / 64 / 0 | 8 / 56 / 0 | 16 / 112 | 9 / 58 | 128 |
| Masked | 64 / 64 / 0 | 8 / 40 / 16 | 16 / 80 | 9 / 40 | 128 |

Both routes used the installed two-scan 20 ms anchor, pinned 12 ms rank-zero primary, and original within-lane factor selection. The immutable live adapter from `b9a51bdbb` consumed admitted metadata at the existing receiver callback. It skipped both native calls on each omitted visit and emitted two ordinary empty probes with the original counters. The two reversed pairs produced identical per-route row digests. Only after the live rows sealed did the audit load the signed dense reference and apply the archived `5bfaec81d` planner. The unmasked ordered prefix matched all 128 archived rows and the independent 67-factor seekable-member witness. The masked comparison accounted for all 18 removed factors. [Live adapter](live_stereo_blocks.py) · [Independent member witness](seekable-member.md)

| Launch order | Member CPU, unmasked → masked | Member elapsed, unmasked → masked | Short native CPU, unmasked → masked |
|---|---:|---:|---:|
| Unmasked first | 296.839 → 257.497 ms | 301.669 → 263.573 ms | 114.568 → 81.822 ms |
| Masked first | 299.634 → 261.366 ms | 410.632 → 287.577 ms | 117.674 → 83.472 ms |

The member timer charged receiver and schedule setup, verified ingress, per-window validity checks, callbacks, chronological digest construction and native cleanup. Elapsed varied more than CPU, including a 111 ms elapsed-minus-CPU gap in the last unmasked run. All runs used Gauss CPU 2 at nice 15 and best-effort I/O 7 under the shared lock. The existing private staged fixture stayed 18,952/18,952 pages resident in five checks. Each run authenticated the same 77,442,779 compressed payload bytes, 102,400,000 decoded bytes, original signed index and all 64 original windows. Every timed run charged zero process input blocks. No backing-waveform read, new staging, position solve or full-recording launch took place. The measured savings apply through this complete first member. The full recording has different stream boundaries and includes downstream work. [Exact source signatures and clocks](measurements/live-stereo-0008.json.gz)

The first command stopped at the storage-window adapter before the first native callback. The runner now uses the original stereo input adapter and the receipt covers two complete reversed pairs after that correction. Nine component tests passed. The receipt and pre-reference rows expand to SHA-256 `b19eda82126d41903e003b660242c3bf6ecc0b51efa5dca253f1a5b7c9dea35c` and `5e665017f5a9d98fe1d6b97631a283bedb7fa914b160c630bc43a89cb16c48c9`. [Runner](live_stereo_0008.py) · [Component tests](../../../tests/pipeline_eval/test_live_stereo_0008.py)

```sh
study=/dev/shm/leo-v3-live-stereo-0008
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
payload=/opt/leo-algo08/algo08v3/payload
output=/dev/shm/leo-live-stereo-0008-replay

flock -x -w 120 /tmp/leo-algo08v2-2x-bench/gauss.lock \
  ionice -c2 -n7 nice -n15 taskset -c 2 env \
  PYTHONPATH="$study:$study/reports/ALGO08/v3:$release/src:$release:$payload" \
  OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  timeout 30s "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.live_stereo_0008 "$output"
```
