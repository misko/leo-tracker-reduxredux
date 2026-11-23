# Escalating the one-lag timing scout before carrier search

The fixed peak-shape gate preserved **all 100 signed factors** on the saved dense and weak lanes, including 20 secondaries. It escalated **93 of 96** dense lanes and **all 36** weak lanes. Native CPU rose from **117.15 to 117.46 ms** dense and **102.55 to 104.31 ms** weak. Even a post-hoc choice of both independent ratio thresholds projects at most **1.53 CPU s** saved on dense with free routing and no cue overhead. The current model needs **3.49 s**. Retire these two ratios as a route to that acquisition target. [Frozen protocol](precarrier_timing_gate_protocol.md) · [Sealed receipt](measurements/precarrier-timing-gate.json.gz)

## Frozen cue and full fallback cost

The lag-28 timing scan reads one extra peak after the existing circular exclusion. The narrow route requires first/fifth power **>2.0** and fourth/fifth power **>1.125**, with finite scores and positive fifth power. It sends the original first four phases to the full signed carrier grid. Other windows run the original eight-lag timing search and all twelve carrier rows before native refinement. The fallback reuses input conversion, FIR and both frame modes. It recomputes lag 28 inside the original reduction order. Each reached residual scout measures its own peaks after actual signed cancellation. It takes neither a decision nor evidence from the primary scout or the other antenna.

The protocol and implementation were committed at `2929707c1` before collecting peak features. Previous receipts held factor outcomes and per-lane clocks with no peak scores. The test reuses the same 18 weak stereo clips and 48 dense stereo visits, so this is retrospective transfer on known samples. Both pinned native binaries relinked byte for byte. The local alternatives trained on deterministic site-free signals, and the extra fifth readout returned exactly the same factor bytes as uninstrumented one-lag mode. The dense stock rows match the original signed mixed publication packet. [Prior one-lag study](short-timing-lags.md) · [Native overlay and runner](precarrier_timing_gate.py)

| Scope | Lanes | Full control / one lag / guarded, CPU ms | One-lag changed packets / published selection | Escalated lanes / false escalations | Guard changes |
|---|---:|---:|---:|---:|---:|
| DS30-0008 dense, mixed | 96 | 117.15 / 88.85 / 117.46 | 7 / 7 | 93 / 86 | 0 |
| Dense 12 ms primaries | 80 | 76.02 / 54.20 / 76.78 | 7 / 7 | 77 / 70 | 0 |
| Dense 20 ms anchors | 16 | 41.12 / 34.66 / 40.76 | 0 / 0 | 16 / 16 | 0 |
| All weak, mixed | 36 | 102.55 / 76.64 / 104.31 | 9 / 6 | 36 / 27 | 0 |
| DS26-0020 | 4 | 14.30 / 9.53 / 14.59 | 2 / 1 | 4 / 2 | 0 |
| DS26-0036 | 8 | 20.01 / 15.09 / 20.16 | 1 / 1 | 8 / 7 | 0 |
| DS26-0066 | 6 | 22.35 / 16.71 / 22.29 | 1 / 1 | 6 / 5 | 0 |
| DS26-0162 | 10 | 21.67 / 18.14 / 22.40 | 1 / 1 | 10 / 9 | 0 |
| DS26-0237 | 8 | 24.63 / 17.57 / 24.97 | 4 / 2 | 8 / 4 | 0 |

An escalated lane is false when its plain one-lag signed factor packet already matches stock byte for byte. On the dense slice that includes all 52 empty lanes. The guard paid for **92 of 96 raw** and **8 of 9 residual** full searches. Of those 100 broad searches, 93 were on byte-matching lanes. It paid for **36 of 36 raw** and **23 of 24 residual** full searches on weak, of which 43 were on byte-matching lanes. The three order-rotated repeats include all actual branch costs and verification. Across the whole dense recording, applying the per-aperture paired cost ratios to 12.635 short and 4.716 full native CPU seconds implies **0.08 s more** CPU. This projection is near parity and is not a whole-recording timing. [Dense CPU split and projected requirement](warm-recording-budget.md)

## Why tuning the ratios has too little remaining budget

Define lane confidence as the minimum over the reached unguarded scouts of `min(first / (2 × fifth), fourth / (1.125 × fifth))`. On dense, the seven incorrect signed packets reach **0.838** and the median of 89 correct packets is **0.712**. Covering every dense failure by choosing a threshold after reveal needs 54 false escalations among those 89 correct lanes. On weak the nine incorrect packets reach **0.864** and the 27 correct packets have median **0.899**, requiring nine false escalations. Transferring the hindsight dense cutoff to weak misses one bad packet. Applying the weak cutoff to dense catches the seven observed failures while escalating 55 already-correct lanes. These are outcome-guided separation diagnostics on reused data.

Allowing the two ratios to have independent thresholds still needs 54 false escalations on dense for the best CPU result that covers all seven changes. That estimate grants advance knowledge of each reached residual cue, lets each correctly routed lane run either untouched stock or uninstrumented one-lag for free at the decision boundary, and charges no cue, switch, or extra original timing. It projects only **1.53 s** saved. This is a ceiling for the studied monotone threshold family under the per-aperture transfer model. It does not bound an independent feature from the waveform. The earlier perfect answer-key route approached 3.67 s because it could flag wrongly measured lanes without using either ratio. [Early-routing oracle](short-timing-lags.md#costs-at-the-dense-acquisition-boundary)

## Reproduce

Run on the existing private DS30 member and archived weak clips. A preliminary command stopped when the sparse worktree excluded two adjacent test files. After restoring those files, one bounded native job captured both panels. Nine component tests passed, including strict equality handling, finite checks, hindsight cost and existing row-order and mixed-packet tests. No position solve or full waveform traversal ran.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
tree=/home/mouse9911/gits/leo-tracker-reduxredux
private=/srv/bulk/leo-dev/leo-physical-stage-envelope-2j7mlwtt
dense="$private/fast8-auto-20261113-075937-d9ab96ee-1-lower-segment-00000000"
packet=(/var/tmp/leo-full-short-dense-DS30-0008/publication/fast-scan-automatic-work/*/detections.json)
work=$(mktemp -d /dev/shm/leo-v3-precarrier-gate.XXXXXX)
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env TMPDIR=/dev/shm OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" timeout 65s "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.precarrier_timing_gate bench "$work/native" "$release/assets" \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" "$dense" \
  "${packet[0]}" > "$work/receipt.json"
PYTHONPATH="$PWD:$release/src:$release" OPENBLAS_NUM_THREADS=1 \
  "$release/venv/bin/python" -BPs -m reports.ALGO08.v3.precarrier_timing_gate analyze \
  reports/ALGO08/v3/measurements/precarrier-timing-gate.json.gz
```

The uncompressed receipt SHA-256 is `f7e34c8998ff3a3e4bf1db72da780d25b267d35eb3d9f5edbb95a26eeee3fc29`. It includes each reached scout's five peak scores, the actual fallback, all ordered factor bytes, rotated clocks and the pinned input and build digests.
