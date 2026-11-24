# DS30-0049 publication forensics

The successor finished 5.079 s sooner on the campaign's raw-to-verified-publication clock. Fitted position error rose from 1.420 to 4.040 km. The two builds selected the same satellite pair, but the successor lost 27 associated points on receiver 2 and then moved its fixed-support solution another 1.370 km during the accepted signed phase finish. The published artifacts show where the differences appeared. They do not isolate the effect of the new receiver from the different association and inference path. [Digest-bound readout](measurements/ds30-0049-publication-forensic.json.gz)

## Identical acquisition admissions, different measured factors

Both second attempts bind the same signed raw authority, inventory, 25 km offer and causal catalogue cutoff. They report 986 issued visits and identical sets of 932 processed and 54 invalid visits, including identical probe metadata, both stereo slots, and all delivery and sample clocks. Both reported 27 catalogue reads and 282,922 parsed TLE records without parser fallback. The successor ran 242 full-20 ms antenna calls on 121 stereo anchors and 1,622 short-8 ms calls on 811 stereo visits. It retained the unfiltered packet after negative held log-score gains on both radios, −8.850 and −4.513. It made zero fixed-epoch full-20 ms refinements.

| Detector comparison by original antenna slot | Positive in both | Installed only | Successor only | Neither |
| --- | ---: | ---: | ---: | ---: |
| All 1,864 slots | 427 | 104 | 173 | 1,160 |
| Full anchors | 71 | 0 | 12 | 159 |
| Short visits | 356 | 104 | 161 | 1,001 |

All 71 common positive anchors have identical published factor values. The 12 gained anchors show that the final factor set can differ even on full calls. Their origin cannot be attributed to aperture from these post-continuation packets. Of the 356 common positives on short visits, 284 agree within the existing 250 Hz signed CFO and two-sample wrapped-epoch comparison screen. The absolute signed CFO delta has a 102 Hz median and 75.7 kHz 95th percentile. Folding at the native alias period leaves the same 284 joint matches. Differences show selection or measurement disagreement, and the 20 ms factors are a comparison here. [Receiver and per-lane joins](measurements/ds30-0049-publication-forensic.json.gz)

## Selected curves and receiver balance

The installed fitted residual and track-RMS PNG labels independently account for all 320 installed owners on nine polynomial fragments. The successor publishes 268 owners on seven fragments, all conditional, with identical owner rows in both calibration arms. The original installed per-observation owner rows are absent from these publications. The figure labels and stable visit/receiver joins support exact lane totals and several direct bounds without assuming unknown row identities.

| Published lane and owner family | Installed owner points | Successor owner points |
| --- | ---: | ---: |
| RX1 CH1, CH2, CH5 · NORAD 69163 | 47 / 47 / 57 | 44 / 40 / 49 |
| RX1 CH6, CH7, CH8 · NORAD 67117 | 55 / 41 / 33 | 56 / 37 / 29 |
| RX2 CH6, CH7, CH8 · NORAD 67117 | 21 / 9 / 10 | 13 / 0 / 0 |

RX2 positives increased from 157 to 170 while RX2 associated points fell from 40 to 13. On RX2 CH6 all 21 installed positives were owned. Nine lost their positive factor, one stayed positive without an owner, and 11 remained owned. Two new successor-only factors made up the other two owners. On RX2 CH7 and CH8, the detector losses necessarily include at least six and two original owners respectively, from the installed positive fractions and exact shared-slot counts. Overall, 254 of the 268 successor owners have a positive installed factor at the same slot and 222 meet the 250 Hz/two-sample comparison. The successor's Graph trace has 399 assigned observations across 15 fragments before the final seven-fragment fit. Its rank first found two distinct assignments and used the existing ordinary-rank retry. Its recorded cold winner had a 44.51 score lead over the next finalist, so the eventual regression did not present as a near tie in that race. [Track counts, joined support and route](measurements/ds30-0049-publication-forensic.json.gz)

## Signed phase finish and final position

| Published metric | Installed `c = 0` / fitted `c` | Successor `c = 0` / fitted `c` |
| --- | ---: | ---: |
| Horizontal error | 1.826 / 1.420 km | 4.472 / 4.040 km |
| Terminal RF RMS | 129.663 / 129.671 Hz | 168.634 / 168.814 Hz |
| Standard manifest all-owner RMS | 145.914 / 141.298 Hz | 168.634 / 168.814 Hz |

Fitting `c` improved position error in both builds by 0.405 and 0.432 km, respectively. The terminal RF RMS increased by 0.008 and 0.180 Hz. The manifest RMS covers the full published owner set and is a distinct statistic. The location regression is already present in the matched `c = 0` arm.

Within the successor, the ordinary finish had errors of 3.249 and 2.758 km on the eventual fixed 268-point curved support. The accepted signed phase correction retained that support, ranking, and receiver packet. It changed family phase-prior means from zero to −0.825 and −0.166 s and moved the two endpoints 1.377 and 1.370 km west-northwest. The fixed-support change increased geographic errors by 1.223 and 1.282 km. Reported objectives across the two phase models changed by only −0.089 and −0.099, and RF RMS by +0.002 and +0.005 Hz. The final path shows the westward position in the first accepted phase round in both arms. Both builds' 179-point grids bind their own published positions. Every arm's final endpoint minimizes its own grid. The shared coarse minimum is [3.125, −6.25] km for installed and [0, −6.25] km for successor. These are conditional fixed-owner, fixed-linearization grids. The raw values from different publications use different factor sets. [Fit traces and conditional grids](measurements/ds30-0049-publication-forensic.json.gz)

## Diagnostics with broader use

- Measure the conversion of receiver positives into distinct owned receiver/channel support by family. Track whether apparent factor gains leave an owner family supported by fewer independent lanes, shorter arcs, or larger time gaps. Here the strongest measurable loss was RX2 on NORAD 67117 despite higher RX2 detection yield. Compare anchor and short slots separately, and preserve pre- and post-continuation evidence if a future controlled receiver comparison is authorized.
- Audit matched-support displacement when a phase-prior update is accepted. Compare the size of the shift to the local grid curvature and look for genuinely held receiver, time, or family support for the new location. In this case a 1.37 km shift narrowly changed the recorded objective and barely changed RF RMS, even though earlier catalogue-transition validation passed. A later preregistered test should use the causal data alone to define the signal and reserve site coordinates for evaluation.
- To separate receiver and solver effects, the two sealed detector packets admit a future receiver-by-solver crossover under the same offer, catalogue, masks, and budgets. Report the fixed-zero and fitted arms separately and capture the exact owner roster and ordinary-to-signed path for both builds. This investigation read the two materialized attempts, their bound figures, and the sealed evaluation authority. It launched no receiver, solver, waveform, or catalogue work and did not change the campaign.
