# Joint slope and curvature from short Doppler triplets

A shared orbit across two adjacent CFO intervals narrowed the effective held orbit alternatives on every offer, relative to the common-slope control. **All six offers withheld in both calibration arms.** The waveform containing case forced a **1.06 km** estimate with both models, but the joint held geographic lead was only **0.008** against a required **0.04**. The curvature signal helped distinguish the time order independently of position. [Support figure](triplet-support.png) · [Six standard position charts](charts/manifest.json) · [Complete scores](scores.csv)

## Anonymous observable

Each 12 s bin uses three gated snapshots from the same receiver, channel and exactly tuned RF. Each 3.3–4.7 s interval has its own folded CFO difference, and both intervals share the middle peak. The features are the overall slope and the second slope minus the first. The difference in rates is a discrete curvature contrast in Hz/s. The receiver marginalizes all admitted candidate triples and one shared visible orbit. It does not assign an orbit to an arc or connect one triplet with another. The earlier `rate_triplets` implementation seeded three points, extended them into persistent segments and fitted selected orbit owners. This study changes the likelihood on the short observations directly and never invokes that linker or fitter. [Preregistered protocol](PROTOCOL.md) · [Source and dependency hashes](source-lock.json)

The slope and curvature model propagates covariance from equal endpoint frequency noise, including the shared midpoint and unequal sample spacing. Fixed LO and constant RF calibration cancel on exactly the same carrier. The model includes fixed 35 Hz/s slope and curvature allowance for fast receiver and model error. The common-slope branch drops the curvature term on the exact same raw triples and grid. The reversed branch flips the modeled curvature sign and keeps the overall slope. Unit-normalized orbit and endpoint alternative mixtures limit the reward from a crowded catalogue. A clutter component covers the uniform folded endpoint increments. All arms, including the experimental controls, retain their actual forced endpoints. [Paired prediction archive](positions.jsonl.gz)

## Held results

Geographic errors in the table are forced distances in km. The controls choose a site independently on training. The held orbit alternative counts are posterior effective sizes at each method's training-selected site. Every real offer had four held 24 s blocks. Each emitted-waveform offer had three.

| Offer | Triplets held / total | Joint forced km | Slope-only forced km | Reversed forced km | Tile centre km | Joint spatial lead | Joint vs reversed held lead |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DS26-0261, containing | 38 / 104 | 8.19 | 6.04 | 8.19 | 8.19 | −0.349 | 0.275 |
| DS29-0519, containing | 50 / 158 | 7.94 | 12.30 | 17.02 | 8.19 | −0.273 | 0.023 |
| DS26-0070, omitted | 52 / 155 | 41.24 | 41.76 | 41.76 | 51.23 | −0.417 | 0.123 |
| DS29-0316, omitted | 52 / 166 | 44.18 | 57.95 | 48.73 | 55.19 | −0.426 | 0.140 |
| Waveform containing | 20 / 76 | 1.06 | 1.06 | 5.11 | 8.94 | 0.008 | 0.282 |
| Waveform omitted | 20 / 76 | 6.42 | 4.03 | 4.03 | 14.03 | −0.075 | 0.179 |

Real effective orbit alternatives decreased from **2.06–3.30** with the common slope to **1.22–1.94** with the joint model. At the waveform site the respective counts were **5.00–5.12** and **4.03–4.40**. The joint model beat reversed curvature at its own selected site on every held evaluation. It exceeded the +0.075 reversal margin on five of six. The joint's separated-site lead missed +0.04 everywhere. The curvature model narrows a conditional orbital interpretation without supplying enough replicated position evidence on these offers. [Per-case mixture and posterior summaries](scores.json)

The known-orbit median rate slope change over a 25 km displacement was **22.6–23.6 Hz/s**, versus a **43.6–44.3 Hz/s** slope kernel. The corresponding curvature contrast was **1.09–1.14 Hz/s** versus a **96.9–100.5 Hz/s** kernel. These are linearized strongest-direction contrasts from matched causal orbit predictions at generic ±10 km sites. Held joint conditional slope RMS ranged **36–63 Hz/s** and curvature RMS **76–128 Hz/s**. They describe residuals inside the posterior mixture. The original v5 and installed waveform RMS values are absolute CFO in Hz, on their own selected supports. The four original v5 options appear only on the two matched real containing offers. Their no-repair c0 position errors were **1.39 and 0.25 km**. [RF and geographic scores in separate columns](scores.csv) · [Detailed original waveform provenance](../../track-recovery/waveform-site/README.md)

The earlier two-snapshot likelihood used shorter intervals, more candidate slices and a wider slope kernel. Its forced waveform containing error was 5.11 km, versus 1.06 km here with either model. The causal attribution for curvature is the same-triplet slope control. Both standalone receivers returned zero fixes. [Earlier matched input study](../../acquisition-frontier/trackless-likelihood/README.md)

All six workers completed with **5.31 s median CPU**, **8.33 s median elapsed** and **149.4 MiB peak maximum RSS**. Each modeled 1.42–4.43 million orbit-triplet predictions once for all three branches. This is a shared-worker measurement across three fits. The blind run reproduced the original emitted Qin native hashes and both exact waveform offers, without waveform reruns. Three component tests cover alias/calibration cancellation, unequal-interval covariance and a planted same-slope orbit tie. [Input seal](blind-plan.json) · [Prediction seal](prediction-lock.json) · [Scored figure seal](score-lock.json)
