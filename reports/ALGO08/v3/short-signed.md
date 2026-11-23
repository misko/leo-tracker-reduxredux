# Twelve milliseconds per signed two-scan visit

A 12 ms receiver cut native CPU by **39.1%** across the first 48 stereo visits of DS30-0008. It preserved **56 of 80** factors within two wrapped samples and 250 Hz of signed CFO at the same scan rank, including **16 of 28** residual factors. On the independent weak challenge archive it preserved **45 of 58**, including **15 of 22** residuals. A fallback with advance knowledge of every mismatched factor set would project to only **1.07×** faster acquisition on DS30-0008 at these tolerances. The short receiver also lost all four independently planted late-only pilots. [Per-lane receipt](measurements/short-signed.json.gz) · [Frozen protocol](short-signed-protocol.md)

## Aperture and control

The saved, integrity-verified native visits contain 200,000 CI16 complex samples per antenna at 10 MS/s. The branch consumes the first 120,000. Eight frame origins at 750 Hz provide support for the whole timing phase range. The latest complete later-symbol confirmation ends at exclusive sample index 119,777. The last required scout FIR support ends before 112,338 and the fractional verifier support before 109,579. For each antenna, both carrier searches use the same full signed band and timing offsets. Frame covariance, full-rate refinement, parity normalization and later confirmation use only the retained origins. Early-symbol confirmation uses four disjoint two-frame groups, preserving two origins per group. The reference uses seven such groups.

For a confirmed first scout, the resident floating path or shifted-center CI16 path fits and subtracts the signed pilot inside the same prefix. The residual can propose a second independent factor. Both factors go to the original integer stencil and exact-versus-rolled fractional gate on untouched CI16 from the prefix. The GLRT score divides the best spectral power by the sum of retained per-frame ceilings, and the original 0.025 margin still applies. The verifier preserves the 15-frame packed stencil storage stride while limiting computation to eight. Replacing the suffix in all 148 tested lanes with saturated values left every short factor byte identical. Authentication, decoding and sample counters used the original 20 ms input.

The historical seven-frame receiver shortened only nomination. It restored the full capture for signed refinement, cancellation and verification. The frame-plane receiver preserved all 14 origins and changed data layout. The tracking receiver narrowed search work or reused previous RF history while keeping later full verification. The shorter receiver here changes the support for both complete scans and their independent verifier and retains every RF visit. [Earlier 10 ms scout](../single-core-2x/receiver-aperture.md) · [Frame planes](../single-core-2x/receiver-frame-planes.md) · [Tracking and shortened blind scout](../single-core-2x/receiver-tracking.md)

The native build relinks the archived objects to installed v3 SHA-256 `2258f592b18b78529e5acd408deb7ad28d55aae736011519a37dd49abf38afa5`. Fresh full and short arms train their modified timing, refinement and cancellation objects on the original site-free mixed-center inputs and require GCC coverage compatibility. The rebuilt full control `f4cd09ae4704f8d4d1e14260014c3b2b9fe849d4ee4e9e7ba9546395ce1ace53` has a different library digest, reproduces every tested installed factor byte and selected observation, and measures within 0.5% of installed aggregate native CPU on each physical slice. The short receiver SHA-256 is `74464b62ae5cc5763dd62fa611e14133ef602578e11200c3152b0dc9555cd169`.

## Coverage and cost

The dense slice includes both antennas and all eight RF channels. The weak archive contains 18 previously nominated stereo visits over five DS26 recordings. The match is one-to-one with a preserved scan rank, a circular timing difference of at most two samples and a signed CFO difference of at most 250 Hz. Lower and upper refer to the known pilot edges. Extras are relative to installed v3. An empty physical lane is an empty v3 factor set.

| Saved group | Lanes | Primary matches | Residual matches | Total matches | Matches ignoring rank | Rank-preserving extras | Extras on empty stock lanes |
|---|---:|---:|---:|---:|---:|---:|---:|
| DS26 weak | 36 | 30/36 | 15/22 | 45/58 | 49/58 | 10 | 0 |
| DS30 dense | 96 | 40/52 | 16/28 | 56/80 | 61/80 | 9 | 1 of 44 |

Among rank-preserving hits, the maximum timing, CFO and margin changes were 0.818 samples, 200.6 Hz and 0.152 on the weak slice and 0.932 samples, 213.6 Hz and 0.098 on the dense slice. The weak sample had no continuation selections. Dense continuation selected the same lane and rank at the same visit, with a different measured tuple and a CFO change of 6.55 Hz.

The four planted signed two-carrier lanes recovered both expected factors at each edge including the shifted mixer. The four independent noise lanes returned no factors in either arm. The four late-only pilots were recovered by the 20 ms control, and the short receiver returned empty in all four. Both arms also detected the adversarial rolled waveform at a shifted epoch on all four rolled input lanes. This is a blind acquisition ambiguity already present in v3 and cannot serve as a negative for the signed full-search acceptance rule. The branch inherited one of the two unplanted residuals on those lanes. These controls are limited spot checks.

Five interleaved repeats use the same native call boundary for every lane. The native speedup comes from fewer samples and reduced covariance and refinement. It also includes the cheaper processing of lanes that return fewer factors. On the 20 dense lanes where both arms emitted two factors, the short arm used 63.6% of installed aggregate native CPU. Equal counts permit different factors.

| Saved group | Installed median lane CPU | Full control median lane CPU | Short median lane CPU | Installed / full control / short median total CPU | Native median total elapsed, installed / short |
|---|---:|---:|---:|---:|---:|
| DS26 weak | 4.069 ms | 4.093 ms | 2.635 ms | 142.94 / 143.54 / 89.26 ms | 142.98 / 89.30 ms |
| DS30 dense | 3.408 ms | 3.376 ms | 1.062 ms | 256.25 / 257.23 / 156.03 ms | 256.34 / 156.10 ms |

## Fallback and whole acquisition

The complete reference acquisition used 37.338 CPU s in detector callbacks and 21.623 CPU s outside them. Halving that CPU boundary with unchanged outside work requires callbacks to cost at most **21.0%** of their current time. The dense short arm gives **60.9%** native cost before fallback. Applying that relative ratio to the full callback CPU projects **44.36 s** instead of 58.96 s, or **1.33×** for the measured input-to-solver boundary. The timings used to compute the ratio exclude continuation and the projection applies it to the full callback budget, which includes continuation. This assumes the positive and empty lane mix and per-hit cost ratios transfer across the recording. It is an optimistic CPU projection without matched factors. It supplies no end-to-end elapsed or solved-position result. [Complete installed acquisition timing](acquisition-split.md)

The tolerance oracle charges a measured complete stock callback on each lane with a missed or extra same-rank factor. It requires 10/36 retries on weak and 20/96 on dense. Dense short plus these retries costs 231.37 ms at the native boundary, projecting to **55.34 CPU s** and **1.07×** acquisition speedup. Even this oracle preserves only the stated tolerances on accepted short lanes. Exact factor-byte parity needs 53/96 full dense retries, which exceeds baseline native CPU by 39.9%. Retrying on every short-empty lane costs 238.78 ms and leaves twelve mismatched dense lanes with a short factor. Every retry projection charges the short attempt first and uses observed stock per-lane clocks. No adaptive selector or full-recording replay was used.

## Reproduction

Run the trial in a fresh research directory on Gauss. The dense input uses the original DS30-0008 binding SHA-256 `a9ced88711b3a8174e47f7a337e2d5a497642c81eb4a7b5c877c2402d607f77a`. Its first touched member is decoded to the member end and validated, while DSP is scoped to the first 48 scheduled visits. The weak reader checks each selected entry's I/Q digest. The receipt records compiler commands, sources, training, indexed sample hashes, factors, continuation publications and paired lane clocks. [Runner](short_signed_trial.py)

```bash
bench=/tmp/leo-algo08v2-2x-bench
tree=/home/mouse9911/gits/leo-tracker-reduxredux
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
lock() {
  flock -x "$bench/gauss.lock" ionice -c2 -n7 nice -n15 taskset -c 2 timeout 55s "$@"
}
lock sudo -n -u leo env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$release/venv/bin/python" -BPs \
  -m reports.ALGO08.v3.short_signed_trial "$bench" "$new_work" \
  /opt/leo-algo08/algo08v3/payload/receiver.so "$release/assets" \
  "$tree/reports/2026_11_20_single_scan_glrt/satellite-reference.zip" \
  /srv/bulk/leo-dev/ds30-full-20261121/bindings/DS30-0008.json /srv/bulk > "$new_receipt"
lock env OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
  BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 PYTHONDONTWRITEBYTECODE=1 \
  PYTHONPATH="$PWD:$release/src:$release" "$tree/.venv/bin/python" -BPs -m pytest -q \
  tests/pipeline_eval/test_receiver_short_signed.py tests/pipeline_eval/test_receiver_scout_readout.py
```
