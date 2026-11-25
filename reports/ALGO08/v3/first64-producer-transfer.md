# Pricing the complete DS30-0016 input-boundary result on the first 64 pairs

The new physical result raises the plausible credit for input-buffer reuse. Even if the entire observed DS30-0016 improvement transfers, it leaves **72.30–86.91 s** above half the installed wall-time sum on the frozen first 64 pairs. The modeled paired median clears 2× in that scenario. Crediting only the observed producer CPU, with the optimistic assumption that each removed CPU second saves a wall second, leaves **64.31–78.73 s** and needs another **5.9–7.2%** of measured native callback time or **7.6–9.4%** of measured non-grid solver time. Historical independent input evidence allows a much larger deficit. [Per-case models and exact input pins](measurements/first64-producer-transfer.json.gz)

## Measured boundaries

| DS30-0016 charted-first comparison | Charted (s) | Combined (s) | Observed difference (s) |
| --- | ---: | ---: | ---: |
| Producer thread CPU | 1.772764 | 0.644943 | 1.127821 |
| Complete authenticated acquisition wall | 4.985657 | 3.800658 | 1.184999 |
| Native callback wall within acquisition | 2.309416 | 1.767353 | 0.542063 |
| Acquisition wall excluding those callback clocks | 2.676241 | 2.033305 | 0.642936 |
| Numerical worker CPU through exit | 9.904803 | 8.923039 | 0.981764 |
| Raw launch through exit wall | 10.398624 | 9.287252 | 1.111372 |
| Independent verifier wall | 0.390637 | 0.392330 | −0.001693 |
| Paid wall through independent verification | 10.789262 | 9.679582 | 1.109680 |

Both runs processed all 808 signed opportunities and the same ordered original members and native packet. Eleven successful lookahead hits supplied **834,805,982 bytes** in both arms. Seven destination reuses actually occurred in the combined arm. These are same-original, different-intervention clocks in one launch order. The charted arm began with 126,976 bytes of nonresident source allocation and the trial with all enrolled source pages resident. The processes recorded 138,344 versus 90,720 input blocks and 487 versus 146 major faults. Native callback wall fell by 0.542 s even though the native packet was identical. Together with the simultaneous changes to CFO processing and grid export, these measurements preclude assigning the observed wall delta to one port. The grid equivalence gate failed. This recording previously informed the design. [Sealed original comparison](measurements/combined-small-panel-0016-natural-pair.json.gz) · [Trial scope and scientific result](combined-small-panel.md)

## Frozen field sensitivity

Installed and delivered successors spent **6,311.327 and 3,764.932 s** through their sealed verification boundaries. The target is **3,155.663 s**, with 609.268 s outstanding. Those successors paid 2,397.007 s of acquisition, including 1,093.307 s of native callback wall, and 1,034.281 s of solving, including the 193.524 s standardized grids. Their 5,178 signed lookahead hits supplied **403.959 GB** of 465.672 GB of original encoded payload and cost **655.907 producer CPU s**. The 146.263 s of exposed demand waiting is already inside acquisition. The three zero-hit recordings receive zero credit. The 64 records end at DS30-0282 and include the signed DS30-0452 relocation. [Frozen first-64 identities and clocks](ds30-routing-first64.md)

| One transfer credit at a time | Modeled saving, hits to bytes (s) | Remaining above half, bytes to hits (s) | Summed speedup | Paired median speedup |
| --- | ---: | ---: | ---: | ---: |
| Producer CPU on the CPU clocks | 530.54–544.96 CPU | 170.70–185.12 CPU | 1.874–1.883× | 1.946–1.954× |
| Producer CPU translated entirely to wall | 530.54–544.96 | 64.31–78.73 | 1.951–1.960× | 2.017–2.024× |
| Observed complete acquisition wall | 557.81–573.42 | 35.85–51.46 | 1.968–1.978× | 2.032–2.042× |
| Observed acquisition wall excluding native callbacks | 302.65–311.11 | 298.15–306.62 | 1.823–1.827× | 1.888–1.892× |
| Observed paid wall through verification | 522.36–536.97 | 72.30–86.91 | 1.946–1.955× | 2.012–2.018× |

Each hypothetical saving scales only with measured authenticated lookahead bytes or hit count. Individual CPU credit cannot exceed paid worker CPU or the measured non-native acquisition CPU envelope. The CPU-to-wall model also caps credit at paid acquisition wall outside native callbacks. Complete acquisition and paid wall are separate transfers capped at those whole field boundaries. The former contains the observed native change, and the latter also contains verification and numerical work. Neither combines with an added receiver or grid saving. Durations used here include process contention under the corresponding instrumentation. The arithmetic offers no cold-storage or population guarantee. [Reproducer and clock caps](first64_producer_transfer.py)

## What to budget for the next change

The earlier same-recording slot-only receiver donor cut producer CPU by **0.797–1.007 s** in opposite orders at identical lookahead extent. Transferring those producer deltas by bytes would leave **122.07–223.43 s** at the summed wall gate. A historical full same-recording publication comparison with an unmatched ordinary clock saw a smaller **0.598 s producer CPU** and **0.449 s acquisition wall** difference. Its incomplete matched timing scope prevents a full verified wall transfer. The independent DS30-0049 slot-only original prefix provided **0.077–0.477 s** producer CPU differences over 390.492 MB, and its reuse-first order increased raw prefix exit wall by 0.032 s. Its reuse-first producer result represents just **79.97 s** of modeled field wall credit, leaving **529.30 s** absent another change. [Original slot-only crossover](prefetch-snapshot-accounting.md) · [Historical full publication](prefetch-snapshot-publication.md) · [Independent physical prefix](prefetch-prefix-0049.md)

For an explicit disjoint engineering scenario, grant **1.5× faster native callbacks** and the separate DS30-0138 map-stage elapsed ratio of **0.836894** across the full grid. That leaves **213.27 s** with no input change, equivalent to at least **0.528 wall s per eligible GB** before applying case-level caps. Input transport alone would need **1.508 wall s per eligible GB** on the same basis. Transferring the new donor's **non-native acquisition residual only** would move the combined scenario to **2.058–2.064× summed**. Both the receiver acceleration and the broad map transfer are assumptions. Under the independent 0049 reuse-first producer estimate, that same combined design still misses the sum by **133.30 s**. It would need a further **18.3%** cut in the remaining native wall or **15.9%** of measured non-grid solver wall. Source-boundary improvements deserve priority, alongside an independently effective receiver or solver improvement. These are costs with previously measured outcomes held fixed. The first-64 accuracy constraints remain a separate requirement. [Separate map experiment](profiled-grid-export-0138-pair.md) · [Both timing gates and tested alternatives](measurements/first64-producer-transfer.json.gz)

The reducer used the frozen export `139b02f8…`, seal `224a79f8…`, matched selected attempts and the new donor gzip `bb6942d2…`. It decoded export rows only for the preassigned first 64 and opened no waveforms, original archive or later scores. Three component tests pass, including rejection of nested timing credits. [Component tests](../../../tests/pipeline_eval/test_first64_producer_transfer.py)

```sh
sudo -n -u leo env PYTHONPATH="$PWD" taskset -c 3 nice -n 15 ionice -c 3 python3 -B \
  -m reports.ALGO08.v3.first64_producer_transfer \
  /tmp/leo-routing64-139b02f8 /srv/postgres-nvme/leo-ds30-evaluation-20261124 \
  /tmp/leo-v3-combined-small-panel/reports/ALGO08/v3/measurements/combined-small-panel-0016-natural-pair.json.gz \
  /tmp/new-first64-producer-transfer.json.gz
```
