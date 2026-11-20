# One fifth-center search per dual visit

The staggered detector ran the ordinary four-region GLRT on both receivers and enabled the independent fifth timing proposal on one. It used **28.37 ms median summed CPU**, down from **31.60 ms** for fifth proposals on both antennas. Median wall time moved from **18.99 to 17.84 ms**. On every held visit, the chosen physical receiver reproduced the five-region output and the other reproduced the four-region output. [Stage chart](stage.png) · [PDF](stage.pdf) · [Per-call clocks](stage.csv)

## Receiver policy and exact outputs

Each recording has an independent counter per exact integer RF center. The first hardware-valid visit to a center chooses receiver 0, and successive hardware-valid visits alternate. Hardware-invalid visits leave the count unchanged. The replay reserves the lane from acquisition metadata, before examining IQ or running any detector. A policy that later drops a valid visit still reserves its lane in acquisition order.

The stage sampled the first 24 chronological windows in each of segments 5 and 10 of DS26-0197 and DS29-0316. These blocks are distinct from the parent timing studies. All 96 scheduled files were usable. The held subsets each started local counters at zero and covered eight RF centers. Each center selected each receiver three times. Both selected and unselected lanes matched their fixed native branches exactly, including candidates, hints and stock peak support. Both signed pilots, seeded noise and zero signals exercised both choices on both edges. The original absent-hint control returned the stock rows. [Frozen input roster](source-lock.json) · [Per-lane parity](branch-parity.csv) · [Control and timing receipts](measurements.json.gz)

## Complete same-core calls

Each role ran 288 warmed calls, counterbalanced on caller CPU20 and helper CPU21. Wall clocks start with loaded dual CI16 and end after decoding both physical receiver rows. CPU sums both active threads inside that boundary. Each valid mixed invocation runs one scout and regional union. The other lane directly executes the four-region port. The existing fractional reuse, per-lane detector context and dual join support both modes.

| Complete measured boundary | Four on both | Five on both | Staggered fifth |
| --- | ---: | ---: | ---: |
| CPU p50 / p95, ms | 24.82 / 30.96 | 31.60 / 39.97 | 28.37 / 34.22 |
| Wall p50 / p95, ms | 15.62 / 38.24 | 18.99 / 61.92 | 17.84 / 46.85 |
| Wall at or below 20 ms | 225 / 288 | 171 / 288 | 202 / 288 |
| Ordered candidates over 96 visits | 1,535 | 1,536 | 1,535 |
| Gated candidates over 96 visits | 236 | 253 | 246 |

The median paired CPU saving against five on both was **3.73 ms**. The paired wall saving was **0.70 ms** median, with large variation. For example, DS29's two-fifth wall p95 was 152.39 ms on this bounded pass, compared with 37.70 ms mixed. The reported tails retain those samples. Gate counts describe emitted detector records. Tracking, localization, capture pace and physical board behavior are outside this stage. [Per-capture timing distributions](summary.json) · [Result seal](result-lock.json)

## Native entry

The new `leo_dual_lane_analyze_staggered_v1` takes physical lane 0 or 1 and uses the existing result and trace layout. The code adds one symbol to the persistent join. The exact fractional core stays byte-identical. The local build under `/var/tmp/leo-staggered-native-20261119/build` provides `libleo-staggered-native.so` and sibling `libleo-adaptive-detector.so.1`. Both file identities and the compile command are recorded in the build receipt. [ABI and source closure](build.json)

```python
from tools.pipeline_eval.variants.staggered_native import RfStagger, StaggeredLane

select = RfStagger()
with StaggeredLane(library, edge, helper_cpu=21) as detector:
    lane = select.reserve(rf_center_hz, valid=hardware_valid)
    if lane is not None:
        result, profile = detector.mixed(dual_ci16, lane, trace=True)
```

Keep one `RfStagger` per recording and reserve each hardware-valid visit in acquisition order. Use `window.target["rf_center_hz"]` for the recorded integer RF center. The existing `analyze(..., "stock")`, `analyze(..., "fifth")`, and `analyze(..., "absent")` interfaces are available for fixed controls.
