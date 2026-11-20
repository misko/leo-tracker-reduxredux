# Where the fast receiver loses position accuracy

Across eight roof recordings the original detector found 2,375 positive probes that the fast wide detector marked negative. Only three contained a matching pilot time **and** frequency anywhere in the saved wide candidates. On sixteen selected misses, putting the known pilot time back into the search recovered fourteen at the original GLRT gate. A search that estimated the time from three repeating frames of raw samples recovered zero on those same sixteen targets. The known-time result measures the opportunity available to a better timing estimator. [Candidate census](bracketed-peaks/README.md) · [Known-timing experiment](oracle-start/README.md) · [Raw-frame estimator](frame-coherence/README.md)

The focused gallery contains 43 images. Eighteen measured position comparisons have a chart for each calibration setting, and seven experiments have detector or track-stage figures. The download includes the individual images and the 618 rows behind the position charts. [Browse the charts](index.html) · [Offline chart pack](modification-charts.zip) · [Original ten changes on 135 recordings](../../2026_11_19_position_atlas/original-ten.html)

## How the complete receiver compares with original v5

Twelve distinct roof recordings had eligible runs from saved raw I/Q through the 21-bin, four-start wide GLRT and the installed compact solver. One stock attempt per recording was selected by a fixed study order. All twelve returned fixes in both calibration settings. Selecting the earliest launch instead gives eleven fixes because an earlier DS29-0082 service timed out. Of 78,770 timed dual-receiver visits, 36,002 met the 20 ms detector deadline (45.7%). Median whole-service time for a five-minute recording was 191.4 s on the host under a 512 MiB cap with zero swap. These are retrospective tests at one physical site. [Recording roster, input hashes and timing](wide-roster/README.md) · [Individual attempts](wide-roster/sensitivity.csv)

| Twelve paired raw-I/Q recordings | Wide + compact median / P95 | Original no-repair v5 median / P95 | Within 5% of original error or better | Within 10% or better |
| --- | ---: | ---: | ---: | ---: |
| Zero calibration | 0.774 / 1.849 km | 0.607 / 2.263 km | 4/12 | 5/12 |
| Fitted calibration | 0.781 / 1.791 km | 0.623 / 2.334 km | 5/12 | 5/12 |

The compact position solver using the **original** detector inputs had previously returned all 135 common roof recordings. Its fitted median/P95 was 0.989/2.817 km against 0.988/2.819 km for original no-repair v5, and 131/135 were within 10% of original error or better in each calibration setting. The twelve raw-I/Q cases above evaluate a different change and use a different roster. Four same-factor comparisons isolate it directly. Replacing compact with the original numerical solver on identical wide detections moved the endpoints by at most 16 m in each calibration arm. [Full-roof solver results](../secant-full/README.md) · [Original and compact on identical wide detections](../receiver-core/README.md)

## Testing a different location and a missing region

At a newly drawn, blinded simulated site near southwest India, 1,200 synthetic dual-receiver I/Q windows went through the unmodified native detector and compact solver. Of 528 individual receiver probes containing a planted pilot, 494 produced the right winning peak and 527 had a matching gated candidate. The detector also reported a positive on 196/1,872 probes without a planted emitter. The estimator received only the earlier orbit catalogue. These location errors use the simulator’s sealed coordinates as ground truth. Original-v5 comparisons are available on the recorded roof data. [Waveform, detector and position measurements](waveform-site/README.md)

| Offer to the receiver | Ordinary compact, zero / fitted error | Installed 20 m boundary rule on the same offers |
| --- | ---: | --- |
| Correct region present | 1.017 / 0.751 km | Kept both fixes |
| Correct region missing by 1.5 km | 1.580 / 1.534 km, both incorrectly published | Withheld both, retaining the same forced coordinates for diagnosis |

The first run was blind. The established boundary rule was replayed after unblinding. The omitted estimates landed on the offered face, while both valid estimates were more than 4 km inside. In the earlier measured roof trial, the same rule withheld one of its two valid offers. Independent physical multi-satellite location data and throughput on the intended embedded board remain open. [Installed boundary-rule replay](charts/fitted_c/waveform-site-interior.png) · [Real-roof boundary decisions](../receiver-core/measured-boundary-policy/README.md) · [Board replay status](../receiver-core/board-replay/README.md)

## From recorded samples to a position

| Change | What happened on the measured inputs |
| --- | --- |
| Batch adjacent samples in fractional GLRT | On two previously unused whole-I/Q recordings the replacement produced identical native candidates and identical positions over 13,547 scheduled visits, including 33 invalid visits. Complete host service time went from 210.10 to 203.40 s on DS26 and 210.96 to 209.69 s on DS29. Both recordings exceeded the 10% error allowance against original v5 in both calibration settings. [Two complete recordings](exact-wide-iq/README.md) · [Detector-only timing](wide-kernel/README.md) |
| Recover weak measured peaks between two strong pilots | The rule promoted twelve actual peaks on eight recordings. Two matched the original detector. Seven promotions fell on the four position-test recordings, where the largest improvement was 6.60 m. The 10% counts held at 1/4 with zero calibration and 2/4 with fitted calibration. [Stage](bracketed-peaks/README.md) · [Positions](bracketed-position/README.md) |
| Build tracks using pilot time and Doppler together | On two paired track builds, CPU fell 64–68%. The method preserved far fewer long curves and lost the fix on DS29-0082. All three other positions got worse even as their conditional Doppler residuals fell. In one fragmented 44 s track, two pieces favored the original satellite in a held-fragment check, but both causal frequency errors exceeded the 450 Hz diagnostic scale. [Track and position comparison](epoch-tracks/README.md) · [Satellite identity audit](fragment-identity/README.md) |
| Combine two passes in the compact orbit search | All 20 numerical outputs agreed across 19.84 million satellite-observation pairs. The local calculation used 32–43% less CPU. Each of the three complete solves took longer, with identical positions and conditional RF results. [Matched timings and position distributions](fit-basis/README.md) |
| Estimate location from turns in the Doppler curve | Zero measurable reversals appeared in 432 real and simulated arcs. A separate method using the time of steepest slope found events but withheld all four real positions. Its two forced guesses when the region contained the receiver missed by 17.14 and 16.47 km. The offered centre was 8.19 km away on each. [Direction reversals](doppler-turns/README.md) · [Steepest-slope timing](doppler-inflection/README.md) |

Both native wide detector variants now build from an 89,020-byte standalone builder and source bundle using Python, GCC and FFTW. An isolated build reproduced the exact libraries and short-window executables measured above. The adjacent-sample optimization preserves every measured output and had small, inconsistent effects on the 20 ms deadline across the two complete recordings. [Source, build instructions and checksums](wide-release/README.md) · [Per-visit timings](exact-wide-iq/README.md)

On DS29-0082, changing which probes were positive closed 25% of the fitted error gap to the original detector. The table follows subsequent changes to the winning peak on the same positive probes. The experiment uses saved measurements from both detectors to identify replacements. An operating receiver has to discover the right peaks itself. The conditional frequency-fit statistics, including cases where a lower residual gave a worse position, are in the two source reports. [Positive-probe comparison](support-cross/README.md) · [Winning-peak comparison](shared-winners/README.md)

| Fitted error on the same roof recording | Stock wide | Original positive roster, wide shared winners | Select matching available wide alternatives | Use original measurements for all discordant shared winners | Stock capture-era detector |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS29-0082 | 2.346 km | 1.884 km | 1.787 km | 1.264 km | 0.516 km |
| DS26-0237 | 0.323 km | 0.339 km | 0.311 km | 0.149 km | 0.262 km |

## How to read the figures

Each roof position chart uses the original v5 settings available on those exact recording IDs. The curves count every scheduled recording. Dots and diamonds describe the returned positions and their median. The two calibration settings use the same data, search budget and region. Raw-detector experiments without an attempted position have their own stage measurements. DS26 and DS29 share a physical roof. [Figure inventory](chart-inventory.csv) · [Per-recording values](positions.csv) · [Full roof comparisons](../README.md)
