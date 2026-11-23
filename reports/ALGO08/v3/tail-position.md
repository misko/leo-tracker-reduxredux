# Trailing pilot verification fails the North position screen

The selective trailing verifier removed **326 of 996** original North short positives, kept all 82 positive 20 ms anchors and published both containing fixes. RF residuals fell from **69.40 / 70.86 Hz** to **6.91 / 6.49 Hz**. Horizontal error rose from **390 / 121 m** to **434 / 160 m**. The fixed-zero error exceeded named v3 by **328 m**, outside the 250 m development limit. This result stops the proposal after one containing solve. [Frozen protocol](tail-position-protocol.md) · [Signed replay receipt](measurements/tail-position.json.gz)

## Holds and rescues on complete native input

All 19 original North tmpfs members and their indexes were already resident. The complete signed traversal authenticated 2,400 stereo-lane opportunities over 1,200 visits, preserving hardware sample counters, actual RF, edge and each original measured signed hypothesis. It read 1,580,153,036 logical tmpfs bytes, including 1,579,423,424 compressed waveform bytes. Residency remained complete and process storage input was zero. The original 12 ms packet entered unchanged. Stock outputs and survey were opened for scoring after the candidate packet was frozen. [Replay receipt](measurements/tail-position.json.gz)

| Role | Radio 0 | Radio 1 | Both radios |
|---|---:|---:|---:|
| Short opportunities | 1,048 | 1,048 | 2,096 |
| Original short positives | 502 | 494 | 996 |
| Short positives omitted by original history | 304 | 296 | 600 |
| Omitted shorts passing trailing confirmation | 149 | 125 | 274 |
| Omitted shorts failing trailing confirmation | 155 | 171 | 326 |
| Short positives retained by both variants | 347 | 323 | 670 |
| Positive full anchors retained by both variants | 41 | 41 | 82 |

The selective rule kept every history-selected short factor and evaluated only the 600 remaining short positives at their measured epoch and signed frequency, on the same five disjoint trailing frames as the small trial. The all-positive control evaluated all 996 short positives. Every one of the 396 history-selected shorts also passed independently. The controls agreed on every lane admission and retained tuple, including every anchor and original empty opportunity. The algorithm used neither site coordinates nor full-receiver labels. The 752-factor research packet carries the original raw authority and a new detector identity. Its digest is `sha256:0bea221ff5b60bdf8b722ebeab6c23acfed779bd5e1c4972ee224f6a0445a3db`. [Disjoint sample and GLRT arithmetic](tail-confirm.md)

The prior causal-only comparison published 456 factors and kept 60 positive anchors. This experiment preserved the other 22 anchors as well as the 274 rescued shorts. The one solve measures their combined effect. The DS26 weak challenge from the first trial lost two of 32 matches to any full factor on one stereo visit. Physical recordings and broader geographic transfer remain unmeasured for this policy. [Causal-only North comparison](north-causal-transfer.md)

## Containing decision, position and RF fit

| Original containing offer | Factors | Decision | Horizontal error c=0 / fitted c | RF RMS c=0 / fitted c |
|---|---:|---|---:|---:|
| Named installed v3 | 456 | Complete | 105.690 / 140.779 m | 5.406 / 5.167 Hz |
| Unit graph on original 12 ms packet | 1,078 | Complete | 389.654 / 120.868 m | 69.401 / 70.860 Hz |
| Selective trailing verification | 752 | Complete | 434.071 / 160.380 m | 6.913 / 6.494 Hz |

The new fixed-zero location was `47.7760494811, 16.0954785447` and the fitted location was `47.7711221306, 16.0954785447`. Both arms used 302 assigned observations each, down from 347 with unit weights. The complete publication evaluated all 137 grid points and produced the position path and eight standard PNGs verified by encoded and decoded hashes. The containing offer was the originally supplied region. The existing 100 m omitted control published in prior runs. This experiment used its one-solve budget on containing, so the selective policy's omitted-region decision remains unmeasured. [Original near-omission comparison](north-causal-transfer.md)

## Measured cost

The signed audit traversal cost **4.262 CPU / 4.262 elapsed s**, including full authentication, decoder and both sets of scorer accounting. The selective scorer subtotal was **0.1263 / 0.1263 s**, versus **0.2074 / 0.2075 s** for every positive. History cost **0.0139 / 0.0137 s**. The candidate would reuse the original visit decoding instead of charging the audit traversal a second time.

| Run | CPU s | Elapsed s |
|---|---:|---:|
| Prior named v3 raw-to-exit | 18.480 | 18.514 |
| Prior original 12 ms raw-to-exit | 13.607 | 13.633 |
| Prior unit 12 ms saved publication | 6.858 | 6.860 |
| Selective saved publication | 6.751 | 6.753 |

The selective fit and numeric route used **3.578 CPU s**, compared with **3.616 s** for the sealed saved unit publication. Adding measured history and selective scorer cost and replacing the unit saved duration in the previous raw clock projects to **13.640 CPU / 13.666 elapsed s**, roughly **0.738** of the earlier named-v3 elapsed. These are separate process runs and the raw number is a stage projection. The small measured saved difference does not offset the receiver charge. [Unit 12 ms control](discovery-margin-12ms.md)

## Replay source and artifacts

The component code is in [tail_position.py](tail_position.py). The original measured packet freeze is at `3f86fb661` with script SHA-256 `9395c728b26d74f8a5a325cc7460e1a866519af496521d9d2900e26ec21bc5a7`. The first publication launch stopped at the pinned lazy-import check before fitting. The successful launch used the existing fresh-process `north_factor_swap.py worker` entry with the frozen packet and a private copy of the warm font cache. The reproduction wrapper now uses the same fresh-process route. Seven focused tests passed.

Use the Gauss command and installed interpreter from [the waveform study](tail-confirm.md). Run `-m reports.ALGO08.v3.tail_position freeze OUTPUT` with the source checkout ahead of the payload as in that study. Copy the existing warm font cache into `OUTPUT/fonts` and run `-m reports.ALGO08.v3.tail_position worker OUTPUT GEOGRAPHIC_LIBRARY REGIONAL_TRACK_LIBRARY` with the same outer environment. Both libraries are verified before the fresh installed process launches. Then run `-m reports.ALGO08.v3.tail_position score OUTPUT RECEIPT.json` against the sealed publication. The candidate packet and actual publication are in `/dev/shm/leo-tail-position-north-01/`. The artifact manifest, 137-point grid and eight PNGs are in its `containing/fast-scan-standard-v2/algo08-v2-df4c8fa0fffe769536a7c742f73f51c9/final-error-v7/` directory.
