# Mixed Q15 timing scout on signed receiver lanes

The mixed transform increased complete timing-scout CPU **88.3% on the dense prefix and 84.4% on the weak clips** before exact fallback. The guarded arm retried all **127** scouts and took about three times the original scout CPU. All signed native factors matched on this sample, including 27 secondary factors. The speculative arm still changed 19 primary and 10 signed residual peak orders. This implementation fails the frozen speed test. [Protocol](q15-timing-scout-protocol.md) · [Sealed receipt](measurements/q15-timing-scout.json.gz)

| Saved scope | Stereo visits | Primary / residual scouts | Timing scout CPU exact / speculative / guarded (ms) | Whole native lane CPU exact / speculative / guarded (ms) |
|---|---:|---:|---:|---:|
| DS30-0008 dense prefix, original mixed schedule | 24 | 48 / 9 | 10.178 / 19.160 / 31.591 | 89.102 / 97.620 / 110.343 |
| Weak signed clips, original cadence per capture | 18 | 36 / 34 | 12.967 / 23.917 / 39.003 | 141.306 / 151.682 / 167.547 |

These are medians of four alternating orders in one single-threaded CPU2 run under the shared Gauss lock. The dense prefix ran 16 full and 32 short lanes. The weak archive ran 34 full and two short lanes, and its high residual count describes the sampled clips. The exact arm used the original Float32 scout in the same overlay, with the same clock and trace boundary. Its native bytes matched the byte-identically relinked released full and short libraries on every lane and repeat. The receiver timing includes unchanged conversion from CI16, frame modes, signed carrier search and verification, with the secondary scout driven by actual signed cancellation. Input data came from the already staged signed prefix and pilot-edge clip archive. The timer starts after staged input preparation and ends before any solver or publication.

## Implementation and observed precision

The prototype replaces the two transforms in each of eight lag correlations. It uses a coprime 64×75 Good–Thomas factorization, with AVX2 Q15 length-64 decimation in frequency and the existing Float32 FFTW library for each length-75 transform. The 16,000-unit input ceiling leaves headroom for both complex components and six scaled butterfly stages. The measured scout includes whole-block extent scanning, conversion, both permutations, unscaling, the original filter multiplication and sliding-energy normalization, all 3,333 score cells, and the original twelve circular exclusions. Plan construction cost 0.235 ms on the first full native library and 0.037 ms on the subsequent short library. The independent scout clocks exclude this one-time cost. [Native transform and fallback](q15_timing_scout.inc) · [Matched runner](q15_timing_scout.py)

| Saved scope | Speculative changes in ordered primary / residual peaks | Changed peak sets, primary / residual | Original primary / secondary factors | Speculative changes in either factor rank |
|---|---:|---:|---:|---:|
| Dense | 13 / 2 | 3 / 0 | 30 / 6 | 0 |
| Weak | 6 / 8 | 1 / 1 | 36 / 21 | 0 |

All factor bytes agreed across every measured order, including integer and fractional epoch, signed CFO, scores and factor rank. That agreement applies to these 84 observed lanes. The guarded mode measures each winner's gap from the next eligible score after each circular exclusion. It retries the original eight lag correlations on the same prepared modes whenever any gap is too small to clear twice the score radius. The fallback also covers invalid transform extent, arithmetic range or rounding mode. Native checks exercised signed bin order and normalization in both transform directions, zero, nonfinite input, ties and circular exclusion.

The transform radius allows input rounding and four complex integer units per radix-2 stage. The score radius uses a worst-case forward-to-inverse transfer, minimum sliding energy and a small Float32 allowance. It ranged from 21.8 to 53.4 in score units, while the largest scout's minimum winner gap was 0.000130. No observed scout cleared it. The Float32 allowance was exploratory. The fixed-point radius is far too broad to qualify these peaks, and the measured unconditional mixed path already costs more than the exact search.

## Dense budget

Applying measured dense per-aperture scout times to the historical 1,696 full and 11,834 short calls gives **2.55 CPU s** for the current timing stage and **2.28 CPU s added** by speculative mixed precision. Guarded mixed precision adds 5.45 CPU s under the same projection. These are lane-mix extrapolations from the bounded prefix. The independent earlier oracle supplies the ordered twelve peaks for free and projects **3.08 CPU s** maximum dense savings, below the earlier 3.49 s requirement. Reducing the twelve subsequent signed carrier rows is a separate opportunity in the four- and eight-row oracle arms. This experiment preserves all twelve. [Free-timing oracle](timing-only-oracle.md) · [Dense budget](warm-recording-budget.md)

## Reproduction

The first Python invocation stopped on a missing helper import before construction. The measured invocation includes the helper directory below. Three component tests passed alongside the native checks registered in the receipt. The uncompressed receipt SHA-256 is `8063335e7b6f220a7368e272b1422df57ee1acd58b32ca72d52921c972d45bbf`.

```bash
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -w 60 -x /tmp/leo-algo08v2-2x-bench/gauss.lock \
  sudo -n -u leo ionice -c2 -n7 nice -n15 taskset -c 2 env \
  TMPDIR=/dev/shm OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 OPENBLAS_NUM_THREADS=1 \
  MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  PYTHONPATH="$PWD/reports/ALGO08/v3:$PWD:$release/src:$release" \
  timeout 90s "$release/venv/bin/python" -Bsm reports.ALGO08.v3.q15_timing_scout \
  /dev/shm/leo-v3-q15-timing-scout-reproduction
```
