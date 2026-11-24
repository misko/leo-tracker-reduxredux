# Original-waveform timing on two DS30 recordings

The 20/8 ms receiver and routed solver completed the two enrolled replays in **9.443 s** versus **12.242 s** for installed ALGO08v3. That gives **1.30× by total time** and **1.62× by the reciprocal of the median candidate-to-v3 wall ratio**. The combined time misses the 1.6× release threshold. Both methods returned one position and withheld once. Only one position contributes to the accuracy comparison.

![Paired times for the two replays and horizontal errors for the single returned position](development/history-risk-physical-raw.png)

| Physical recording | Installed v3 wall / CPU | Candidate wall / CPU | Wall speedup | Both decisions |
|---|---:|---:|---:|---|
| DS30-0107 | 1.497 / 1.496 s | 0.615 / 0.611 s | 2.43× | Withheld for insufficient curvature |
| DS30-0016 | 10.745 / 10.742 s | 8.829 / 8.824 s | 1.22× | Fix with eight PNGs |

The two recordings were enrolled by known outcome before the positive replay. Each pair used the same original waveform files, input opportunities, supplied region, and causal catalogue on Gauss. The candidate ran first, then installed v3, on the same single core at low priority with numerical libraries limited to one thread. Clocks cover process entry through exit, including decoding, native detection, both fits when applicable, and publication. The files were resident. Offline admission took 0.108 s for DS30-0107 and 0.100 s for DS30-0016. The 0.616 median and 0.771 summed wall ratios exceed the 0.50 target. These two selected recordings share a roof. They cannot establish other-site performance or estimate a DS30-wide fix rate. [Enrollment and scoring code](history_risk_physical_cohort.py) · [Two-case receipt](measurements/history-risk-physical-cohort.json.gz)

### Position and frequency on the recording that fixed

| Calibration | Installed horizontal error | Candidate horizontal error | Installed conditional RF RMS | Candidate conditional RF RMS |
|---|---:|---:|---:|---:|
| Fixed `c = 0` | 1,643.7 m | 490.1 m | 109.38 Hz | 134.02 Hz |
| Fitted `c` | 1,661.4 m | 980.0 m | 109.48 Hz | 133.74 Hz |

Errors use the operator's station reference. Both calibration arms use the same observations, candidates and budgets within each pipeline. The receiver change alters the observations between pipelines. Each candidate fit retained 115 assignments versus 109 for v3, with 104 in common. Shared assignments kept their satellite family and role. Candidate errors improved in both arms while their conditional frequency residuals increased. Each build reproduced its own sealed scientific outputs and eight reference PNGs. [Positive replay and figure checks](measurements/history-risk-0016-raw.json.gz) · [Withheld replay](history-risk-0107-raw.md)

On DS30-0016 the candidate spent **3.218 s** acquiring detections from the original files and **5.045 s** deciding and publishing. Reaching 2× on that recording would require another **3.456 s** end to end. A previous estimate stitched together separately timed stages and predicted 7.511 s. The measured 8.829 s supersedes it. The first raw attempt stopped after 4.795 s because the checkout's scanner and position modules shadowed the installed pair. The corrected replay used the installed modules and retained the frozen adapter bytes. Both builds were timed afresh. [First attempt including failure](measurements/history-risk-0016-raw-failed.json.gz)

### Changing the renderer

With the Cairo option enabled on **both** recordings, the candidate took **8.217 s** versus **12.242 s** for v3. That is **1.86× at the paired median and 1.49× by total time**. Charging the candidate's separate admission checks gives **1.74× and 1.47×**, respectively. On DS30-0107 the candidate withheld both arms in **0.540 s** before entering a renderer. The 0.074 s difference between the two candidate clocks on this recording therefore cannot be attributed to drawing PNGs. [Cairo pair, controls and clocks](history-risk-0107-cairo.md)

The same candidate with Cairo rendering finished in **7.677 s wall / 7.659 s CPU**, saving **1.152 s** against the ordinary candidate and reaching **1.40×** against the same 10.745 s v3 comparator. It ran after the ordinary pair on the same original input and single core. Separate offline admission cost 0.036 s. Its decision and publication stage fell from 5.045 to 3.844 s. It still needs **0.961 s** to reach 1.6× on this fix, or **2.304 s** to reach 2×.

The renderer preserved both coordinates, frequency fits, all 115 assignments per arm and the grid and path values. Four orbit sheets and two residual sheets used Cairo. The position and track sheets used the revised layout. The eight PNGs matched the corresponding saved renderer reference. All eight differ in pixels from the ordinary layout. The saved visual check found differences in residual tick labels while preserving plotted values and axis limits. [Full raw renderer score](measurements/history-risk-0016-cairo-raw.json.gz) · [Saved visual comparison](history-risk-cairo-physical.md)

### Splitting the stored waveform

The split format lets the short receiver read only the samples it consumes. On DS30-0016 it cut acquisition from **3.188 s to 2.156 s**. The complete run, including candidate-specific setup, took **6.542 s (1.64×)** with a verified split archive ready. Starting with the ordinary recording, conversion and independent readback took another **4.985 s**, bringing first use to **11.527 s (0.93×)**. All 506 detection factors, both positions, both frequency fits, the numerical grid and path, and all eight Cairo PNGs matched the original-format candidate. At this recording's measured 1.134 s saving per ready replay over original-format Cairo, conversion pays back on the fifth analysis. [Physical storage comparison and measured costs](strict-cairo-0016.md)
