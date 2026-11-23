# Later detection stops lose position accuracy

Both the half and three-quarter stops failed the 250 m error allowance on dense DS30-0008 and on the northern containing offer. All four passed the existing publication gates and returned complete numerical evidence and eight verified PNGs. On dense, stopping at three quarters still increased the two horizontal errors by **1.080 / 1.018 km** versus the full same-build route and **0.360 / 0.363 km** versus named ALGO08v3. The saved solver fell from **26.105 to 18.262 CPU s**, with another estimated **4.327 native CPU s** available from omitted short and full detector work. Keep all-visit detection on this evidence. [Frozen comparison](late-prefix-stop-protocol.md) · [Scored receipt](measurements/late-prefix-stop-summary.json)

## Same capture, different stopping time

The two cutoffs retained the exact genuine 20/12 ms candidates for the first `floor(N/2)` or `floor(3N/4)` issued visits. Later visits kept their ordered stereo opportunity rows with empty candidate lists. All recorded clocks, excludes, sample counters, raw authority, capture duration, original region and causal catalogue remained bound. The derived analysis digest and terminal identify each truncated packet. Both calibration arms within an outcome used the same support, priors and budgets. The two archived controls use their own full receiver outputs from the same capture. Evaluation coordinates joined only after the four outputs sealed. [Mask, runner and evidence checks](late_prefix_stop.py) · [Complete comparative receipts](measurements/late-prefix-stop.json.gz)

| Capture and input | Horizon, issued visits | Horizontal error km, zero / fitted | RF RMS Hz, zero / fitted | Result against both controls |
| --- | ---: | ---: | ---: | --- |
| DS30-0008, named v3 | 6,772 | 1.639 / 1.512 | 129.703 / 129.663 | Control |
| DS30-0008, full short | 6,772 | 0.919 / 0.857 | 140.961 / 140.950 | Control |
| DS30-0008, half | 3,386 | 2.911 / 2.648 | 139.626 / 139.606 | Fails both arms |
| DS30-0008, three quarters | 5,079 | 1.999 / 1.875 | 141.442 / 141.386 | Fails both arms |
| North containing, named v3 | 1,200 | 0.106 / 0.141 | 5.406 / 5.167 | Control |
| North containing, full short | 1,200 | 0.390 / 0.121 | 69.401 / 70.860 | Control |
| North containing, half | 600 | 0.563 / 0.609 | 6.967 / 6.932 | Fails both arms |
| North containing, three quarters | 900 | 1.521 / 0.124 | 7.896 / 6.991 | Fails fixed-zero arm |

Dense half reduced RF RMS slightly relative to the full short receiver while increasing both position errors by more than 1.79 km. In the north both cutoffs reduced RF RMS substantially on their smaller accepted supports. At three quarters the fitted arm matched the full short result to about 3 m, while fixed-zero error increased by 1.13 km. The full short northern fixed-zero result was already 0.284 km worse than named v3. The northern cases use a public containing offer with the reference just 100 m inside its face. This run adds no displaced-offer evidence. [Named and same-build northern controls](measurements/north-combined.json) · [Dense controls](regional-dense-pair.md)

## Measured Graph and solver cost

| Capture and stop | Retained factors / full | Graph points / full | Tracks / full | Graph preparation CPU s | Whole solve CPU / elapsed s | Owners per arm / full |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS30-0008, half | 3,720 / 7,336 | 3,285 / 6,461 | 109 / 208 | 0.846 | 11.701 / 11.703 | 2,254 / 4,367 |
| DS30-0008, three quarters | 5,498 / 7,336 | 4,797 / 6,461 | 168 / 208 | 1.209 | 18.262 / 18.277 | 3,032 / 4,367 |
| North containing, half | 553 / 1,078 | 246 / 485 | 20 / 32 | 0.091 | 2.956 / 2.956 | 88 / 347 |
| North containing, three quarters | 805 / 1,078 | 372 / 485 | 28 / 32 | 0.128 | 3.131 / 3.131 | 214 / 347 |

The full same-build saved solves took 26.105 CPU s on dense and 3.656 s on north. Dense solve cost fell by 55.2% and 30.0%. The corresponding northern reductions were 19.1% and 14.4%. Dense cold search fell from 5.724 s to 2.941 and 4.313 s. Numerical evidence fell from 6.022 s to 1.989 and 3.533 s. All four kept the original native regional check and completed the signed route without fallback. Dense published 179 grid evaluations and north published 137 for each stop. The archived full controls expose the narrower native path pack and search clocks. These fell from 23.77 ms to 9.95 and 17.52 ms on dense, and from 2.45 ms to 1.79 and 2.13 ms on north. The archived controls provide no direct full-Graph preparation clock at the broader boundary shown above. [Per-case stage clocks](measurements/late-prefix-stop.json.gz)

## Acquisition still pays for the full recording

| Capture and stop | Omitted native 20 ms / 12 ms calls | Estimated native CPU avoided s | Acquisition CPU held outside native calls s | Modeled acquisition plus measured solve CPU s | Compressed GB in members crossing or following cutoff |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0008, half | 848 / 5,918 | 8.676 | 15.053 | 35.427 | 4.158 |
| DS30-0008, three quarters | 418 / 2,964 | 4.327 | 15.053 | 46.338 | 2.071 |
| North containing, half | 144 / 1,056 | 1.411 | 2.977 | 7.359 | 0.821 |
| North containing, three quarters | 72 / 528 | 0.706 | 2.977 | 8.238 | 0.400 |

Only the call counts are exact. Those counts rebuild the original per-channel, exact-RF and edge schedule across the admitted visits. CPU uses each recording's measured full-run average per aperture. All **8.182 GB compressed / 10.835 GB decoded** for dense and **1.579 / 1.920 GB** for north still require authentication. This includes whole members that straddle either cutoff, and the original index and per-window checks. Modeled acquisition plus saved solve excludes startup, figures, any proposed stop rule and its retries. The same boundaries for the full receiver and archived same-build solve account for 58.508 CPU s on dense and 9.470 s on north. This is a stage model with no fresh raw throughput measurement. [Signed raw source and timing budgets](measurements/late-prefix-stop-summary.json) · [Dense raw acquisition](dense-full-short-raw.md)

## Which observations could support an adaptive stop?

Passing the existing fit, signed and regional checks was insufficient on all four outputs. Dense half and three quarters lay over 4.69 km inside the offer and had arm separations of only 0.265 and 0.124 km. All 2,243 and 3,000 shared observations per arm kept the full run's satellite. Interior endpoints, close calibration arms, high retained volume and stable owners can therefore coexist with a large location error. From half to three quarters, the two dense estimates moved 0.971 km with fixed-zero calibration and 0.826 km with fitted calibration. The northern half arms were only 46 m apart, both on the face, and both missed the position-quality gate. A face test would also affect the valid named northern fix. [Owner overlap and geometric readouts](measurements/late-prefix-stop-summary.json)

Support from independently timed and geometrically distinct arcs is a plausible truth-free stopping feature, in combination with stable positions across nested prefixes. These observations provide no decision threshold. Both dense checkpoints exceed the accuracy gate, and testing both by complete provisional solves would spend 29.962 CPU s before any necessary continuation and final full solve. The analogous northern provisional cost is 6.087 s. A future stop would need cheaper checks with independent evidence of spatial leverage and a priced continuation path. The two tested later cutoffs offer no passing oracle stop on either recording.

## Reproduce

`429ff6e1b` froze all four runs. Run `late_prefix_stop.py run OUTPUT` using the installed Gauss release interpreter and payload, one numeric thread, CPU 2, nice 15, I/O priority 7 and the shared Gauss lock. Use tmpfs for `OUTPUT` and `TMPDIR`. The worker verifies the released detector recipe and both native scorer libraries, and it reads the original manifests and saved detections. After complete receipts, run `late_prefix_stop_score.py OUTPUT SCORE_JSON` with this checkout's `src` and tool packages first so the independent scorer is available. Installed successful terminal records use `ok`; the scorer maps that status to a complete publication only after checking the grid and all figures. The scorer correction required no replays. Forty-three focused and adjacent tests passed. [Runner](late_prefix_stop.py) · [Scorer](late_prefix_stop_score.py) · [Tests](../../../tests/pipeline_eval/test_late_prefix_stop.py)
