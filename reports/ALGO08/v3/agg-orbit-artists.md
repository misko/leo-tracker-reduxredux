# Exact Agg orbit artists with fixed plot limits

Using the native Agg artists with fixed plot limits saved **129 ms CPU on DS30-0402** and **144 ms on DS30-0008** for the four orbit sheets, including PNG encoding. The ordinary renderer was 72 ms faster on the small DS30-0016 scene. The **200 ms** continuation gate failed on both long cases. All four orbit PNGs on each case were byte-identical to the independently stored ordinary products. The release continues to use its existing renderer. [Frozen protocol](agg-orbit-artists-protocol.md) · [Evidence](measurements/fixed-orbit-artists.json.gz)

## What changed

The released plots already set both view limits before layout. Matplotlib 3.11.1 still accumulates data limits and resolves pending autoscale work per scatter and line as the artists are attached. The prototype uses the same `PathCollection` and `Line2D` objects, connects them to the same transforms and axis clip rectangle, and leaves scale calculation to the original explicit limits. It also reuses the original circular marker path and caches its exact Bézier extent by affine matrix. The version, style and alias-period checks restrict the trial to the stock fixed-view, shared-pixel template.

The installed Agg renderer still paints the full axis furniture, titles, legends, gray points, colored points and orbit curves. Visibility and alias gaps, alpha, joins and caps, clipping, and artist order are unchanged. Each band still pays its installed single shared background, both overlays, and both original libdeflate encodes. This work is separate from sharing a background per band or skipping the first redundant restore. [Prototype](fixed_orbit_artists.py) · [Existing Agg reuse and ceiling](ordinary-orbit-reuse.md)

## Measured render scope

| Scene | Complete orbit CPU, ordinary → fixed | Complete orbit wall, ordinary → fixed | Artist construction CPU | Two base draws CPU | Four encodes CPU |
|---|---:|---:|---:|---:|---:|
| DS30-0402 | 1.095 → 0.965 s | 1.095 → 0.965 s | 0.421 → 0.297 s | 0.266 → 0.294 s | 0.228 → 0.226 s |
| DS30-0008 | 1.169 → 1.025 s | 1.183 → 1.030 s | 0.308 → 0.190 s | 0.393 → 0.371 s | 0.292 → 0.313 s |
| DS30-0016 | 0.667 → 0.739 s | 0.685 → 0.739 s | 0.253 → 0.225 s | 0.161 → 0.157 s | 0.128 → 0.188 s |

Each cell is the median of two observations, one in each order. The paired complete-orbit CPU differences were **116 and 143 ms** saved on 0402, **193 and 95 ms** saved on 0008, and **99 and 45 ms** added on 0016. The weak case draws 32 curves and 19 collections, versus 384 curves and 128 collections on 0402 and 432 curves and 124 collections on 0008. Its identical RGBA buffers passed through the same unchanged encoder, whose observed CPU varied by up to 69 ms between arms. These two weak pairs establish no improvement in complete rendering. Bundle CPU, including the four unchanged companion figures, was **2.604 → 2.442 s** on 0402 and **1.428 → 1.497 s** on 0016. No solver or process-through-publication timing was measured.

The remaining candidate long-scene cost includes **294–371 ms** of two complete Agg base draws and **226–313 ms** of four PNG encodes. Those intervals still include required paint and encoding. Canvas copy and restore together account for only **30–35 ms**. The results support reusing cheaper artist construction as a measured increment, without evidence that eliminating more copies would reach the acceptance gate.

## Output verification

All 64 registered layers per scene achieved **100%** gray and color pixel support in both directions at the existing two-pixel gate. The two previously failing RX1 CH2 gray layers on 0402 pass at **100%**, and the independent 0008 RX2 CH4 case passes at **100%**. RGBA hashes, PNG byte hashes and DPI/Software metadata matched the archives. The four 0402 and 0008 orbit sheets remained 2400 × 3172 pixels, and the four 0016 sheets remained 2400 × 3022. The complete 0402 and 0016 replay also reproduced all four ancillary PNGs. The live paired witness confirms equal panel bounds, limits, labels, titles, and ordered legend. The dense input retained only the four calibrated orbit sheets for replay. [Earlier gray-layer failures](orbit-gray-layout.md) · [Dense scene provenance](direct-orbit-figures.md)

The initial replay used the wrong ordinary layout for the independently stored dense PNGs. Its two fresh dense arms agreed, but their archive comparison failed and no timing from that attempt was retained. The corrected comparison uses the archived explicit orbit layout in **both** dense arms. Both other scenes use their ordinary shared Agg layout in both arms. The final run used commit `eed6f5d61` with CPU 2, one thread, nice 15, I/O priority 7, and the shared Gauss lock. It read no waveform or backing archive and invoked no solver. The uncompressed JSON SHA-256 is `fa6775c954f67215de47424e10857d10aabda9318d74246db43133514ef6dc65`. Three component tests passed. [Driver](fixed_orbit_artists_trial.py) · [Tests](../../../tests/pipeline_eval/test_fixed_orbit_artists.py)

Run under an account with access to the locally preserved scenes. Use a fresh tmpfs receipt path.

```sh
release=/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c
flock -x /tmp/leo-algo08v2-2x-bench/gauss.lock ionice -c2 -n7 nice -n15 taskset -c 2 \
  env PYTHONPATH="$PWD/reports/ALGO08/v3" OMP_NUM_THREADS=1 OMP_THREAD_LIMIT=1 \
  OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 BLIS_NUM_THREADS=1 NUMEXPR_NUM_THREADS=1 \
  "$release/venv/bin/python" -B reports/ALGO08/v3/fixed_orbit_artists_trial.py "$fresh_receipt"
```
