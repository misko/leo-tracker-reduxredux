# Packed CI16 on the normal guarded raw path

On the authentic first DS30-0016 member, packed input reproduced the ordinary combined receiver's native packet, supplied region and guarded withholding through exit. Packing added **4.93 and 5.19 ms** to verified acquisition and **5.49 and 9.93 ms** to whole-process elapsed in the two opposite orders. Both paths decoded and authenticated the same complete 102.4 MB of original CI16. This experiment stopped at the matched member. [Frozen protocol](packed-combined-input-protocol.md) · [Machine receipt](measurements/packed-combined-0016.json.gz)

| Serial order | Verified acquisition wall, ordinary / packed | Whole process wall, ordinary / packed | Whole process CPU, ordinary / packed |
|---|---:|---:|---:|
| Ordinary then packed | 294.96 / 299.89 ms | 697.49 / 702.97 ms | 696.08 / 701.59 ms |
| Packed then ordinary | 287.42 / 292.61 ms | 677.33 / 687.26 ms | 675.99 / 685.92 ms |

The parent created the sidecar in **272.32 ms wall / 272.30 ms CPU** from the already resident original. The packed payload was **76,600,256 bytes** versus 78,554,951 ordinary compressed bytes. The map and sidecar metadata were additional, and the original was retained. The initial packing and codec build were outside both child clocks. Each packed child spent 43.75–45.06 ms opening and authenticating the sidecar and 91.03–93.16 ms decoding and checking original bytes. All four children recorded zero input blocks and zero major faults. Ordinary verified the two original staged member files. Each packed child used only the canonical manifest and the packed file pair and checked all **128 packed blocks, 64 original IQ digests and the original decoded member SHA-256**. These are resident first-use clocks with a retrospective sidecar. The previous capture-to-first-use measurements had a different aperture-verification boundary. [Capture experiment](ci16-packed-storage.md)

Both paths issued 64 visits, admitted 58, scheduled eight full and 50 short stereo visits and selected 45 signed factors. Seven paid 20 ms CFO retries made six edits. The held-cycle selector kept the unfiltered set. The original 25 km region retained its different center and screen center. The raw authority, ordered detections, graph proof, causal cutoff and terminal matched byte for byte. Both calibration arms withheld with `no_active_curvature` and no figures or fix. This member has a 2.481 s maximum track span. There was one verified handoff per process. The result qualifies storage parity on a real bounded prefix. It supplies no positive-fix or full-recording clock.

## Input and fallback

The normal combined CLI accepts `--packed-ci16-map FILE --packed-ci16-map-sha256 SHA256 --packed-ci16-codec LIBRARY` together. The private map contains schema `private-algo08-packed-input-map-v1`, `codec_sha256` and a `members` list. Each unique member binds `manifest_sha256`, `chunk_index`, a sibling `directory` and `seek_sha256`. Provide the expected map digest from trusted capture or archive metadata. The original recording command, manifest path and input authority keep their ordinary semantics. The packed reader checks the exact manifest and index association before releasing any data. The codec is loaded from a verified private copy. Both capture arms continue using the original supplied `--region` and `--archive`. [Input source](packed_combined_input.py) · [Entry binding](unified_short_bootstrap.py)

An unmapped span or a packed sidecar that fails admission goes through the original verified source. A post-admission decoder or original decoded digest failure aborts before publication, including failure on a later window after the chronology has advanced. The component tests verify mixed original/packed visitation, fallback on a corrupt encoded tail and rejection of a decoded hash mismatch after partial delivery. The full set of 22 focused and neighboring tests passed. [Tests](../../../tests/pipeline_eval/test_packed_combined_input.py)

## Reproduction

The driver admits only the existing DS30-0016 first member with its original signed extents. It authenticates the local staging before timing and verifies original residency afterward. It uses a bench-only inventory cap for both arms. Two setup attempts precede the reported pairs. The first worker stopped at an early research import and the second completed ordinary acquisition before the scorer looked in the wrong receipt for the withholding reason. The final pairs used fresh processes and the corrected scorer. The uncompressed receipt SHA-256 is `4c2a467306118dc7ce28867c7890c738726d67071fbc83c326612d7d9505d457`.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
  sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
  TMPDIR=/dev/shm OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  PYTHONPATH="$PWD:$PWD/reports/ALGO08/v3:$release/src:$release" \
  timeout 75s "$release/venv/bin/python" -B reports/ALGO08/v3/packed_combined_trial.py \
  /dev/shm/packed-combined-reproduction
```
