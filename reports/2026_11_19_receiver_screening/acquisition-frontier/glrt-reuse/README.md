# One-pass dual-receiver preparation in the wide detector

The candidate reduced preparation CPU by **11.54% in matched calls** and preserved the complete detector output on **30/30 authentic visits**. The median paired change for the whole native call was **−0.113 ms (−0.68%)**. Wall time met the 20 ms deadline on **226/270** calls, up from **219/270**. This is a small host-side improvement. [Stage chart PNG](glrt-reuse.png) · [PDF](glrt-reuse.pdf) · [Paired measurements](timing.csv) · [Qualification](qualification.json)

## Where the work went

The stock native profile spent about 1.85 ms in CI16 preparation per dual-RX visit. Allocation and cleanup each remained near 0.002 ms because the stock implementation already retains its buffers. The preparation change sweeps the IQ once, converts both channels to the same raw binary64 and normalized binary32 values, and accumulates each channel's prefix energy in unsigned integer units. The four scout time regions, 21 coarse bins, signal/control templates and every search and refinement stage use the released stock algorithms. [Frozen protocol](PROTOCOL.md) · [Portable stock build](../../track-recovery/wide-release/README.md)

A valid CI16 energy contribution is at most 2³¹ integer units per receiver per time. Over 200,000 times each prefix is below 2⁴⁹ units, so the original ordered binary64 arithmetic is exact after scaling by 2⁻³⁰. The vector kernel recovers the same numbers after accumulating the same units as integers, including the `−32768, −32768` corner case. One visit uses 100,000 packed 16-byte input loads, 100,000 packed pair-square/add instructions and 200,000 paired receiver-prefix updates. These counts follow the fixed loop geometry. The array payload stays at 12,800,016 bytes with no added persistent storage. [Kernel source and raw input freeze](source-lock.json)

## Matched saved-IQ timing

The fixed schedule contained 22 previously held visits, eight highest-prior-CPU visits from four complete stock captures and two original invalid visits. Every valid visit ran on both physical receivers. Both libraries processed nine interleaved, counterbalanced warm calls per visit on CPU 0 of the x86 host. A separate interleaved invocation of the existing native profile ABI measured preparation. Archive reads are outside all clocks below.

| Stage and boundary | Stock p50 / p95 | Candidate p50 / p95 |
| --- | ---: | ---: |
| Preparation CPU | 1.848 / 2.298 ms | 1.631 / 2.021 ms |
| Complete native CPU | 15.603 / 20.400 ms | 15.351 / 20.253 ms |
| Complete wrapper CPU | 15.852 / 20.722 ms | 15.647 / 20.537 ms |
| Complete wrapper wall | 16.244 / 24.569 ms | 16.099 / 22.266 ms |

The median paired preparation change was −0.218 ms. Whole-call medians are computed across each separate distribution. The paired whole-call estimate uses the two samples from each repetition. The wall deadline counts were **183→184/198** on the 22 previously held visits and **36→42/72** on the selected prior CPU-tail visits. In the latter subset, the wall-time 95th percentile rose from 24.618 to 24.997 ms. The experiment establishes a preparation gain and an observed deadline-fraction gain on this host, with remaining detector latency above 20 ms. [Per-call clocks](timing.csv)

Fresh single-context C processes loaded the same saved IQ and wrote the same decoded fields. Across three repetitions per arm, lower-band peak RSS was 42,604–42,776 KiB for stock and 42,524–42,744 KiB for the candidate. Upper-band peak RSS was 42,952–43,148 KiB for stock and 43,108–43,216 KiB for the candidate. These are process RSS observations. [Memory measurement](memory.json)

## Candidate and gate parity

The stock library matched the authenticated archive. Every nonclock public field, including proposal/epoch selection, all **480** candidate records and **132** gate positives, was exact for the candidate too. Both sidebands additionally preserved the weak and signed plants, same-epoch 160 kHz pair, and separated aliased/interfering pilot controls. Both empty and both seeded Gaussian controls produced zero gate positives. All 14 control payloads were exact. The result boundary here is detector output. [Lower-band rows](DS26-0036.json.gz) · [Upper-band rows](DS29-0082.json.gz) · [Complete evidence seal](evidence-lock.json)

## Opt-in release

The ABI-1 library has the same exported symbols as stock. On x86 it selects the new preparation only for the 10 MS/s dual-RX 20 ms wide path when AVX2 is available. Other geometries and CPUs use the existing preparation. The release was built with GCC and system FFTW in an isolated ext4 workspace with the source archive and project checkout hidden. The source closure came from the authenticated portable capsule. [Build receipt](build-receipt.json) · [Release receipt](release.json)

Candidate SHA-256 `c3bd99be0512990da01bec1bc2164327d2b1fd8f634ce0125d2d5cf19c81665c`.

```sh
python -m tools.pipeline_eval.qualification.glrt_reuse_build \
  --stock /path/to/wide-runtime/stock/libleo-adaptive-detector.so \
  --work /var/tmp/leo-exact-dual-prepare
python -m tools.pipeline_eval.qualification.glrt_reuse_results \
  --out /var/tmp/leo-exact-dual-prepare-figures
```

The second command regenerates the chart and CSV from the sealed local receipts.
