# Trackless position likelihood from anonymous GLRT

The synchronous model reached a regional forced estimate on all six offers and **withheld every position** in both calibration arms. All six selected sites scored better on held samples than the 73 s time shift and pooled density controls. Their held geographic advantage over a separated site was only **−0.035 to +0.001** mean log units, short of the predeclared +0.04. This detects timing information in the anonymous rate distribution and sets a limit on the position evidence it supplied. [Likelihood and geometry figure](likelihood-support.png) · [Six position charts](charts/manifest.json) · [Per-offer scores](scores.csv)

## Observable and controls

Each four-second epoch offers two snapshot times in each receiver and exactly tuned RF lane. The snapshot choices follow elapsed time and the existing detector gates. Wrapped pair differences across the two times cancel constant LO and fixed-RF `c` before normalization to 11.5 GHz. All endpoint alternatives contribute one normalized probability distribution. There is no winner linking, retained track, orbit assignment, Hough vote, or fitted per-orbit phase. A short-term receiver frequency slope remains a nuisance. [Frozen protocol](PROTOCOL.md) · [Frozen source closure](source-lock.json)

The signal component assumes at most one matched pair per slice. Every visible orbit contributes an exact two-time Doppler prediction from a shared causal SGP4 state table. The satellite mixture is normalized by total available visibility weight, so adding unrelated orbits can dilute a match rather than simply give it another opportunity to score. The complementary clutter component is uniform over the folded rate range. Multiple receiver lanes share one epoch's overall weight. The time control shifts only orbital timestamps. The second control pools the normalized visible-orbit rate densities from training epochs, preserving the observation counts and kernel but discarding each epoch's predicted distribution. The same 25 inside points and four exterior points apply to all three models at fixed WGS84 sea level. Five contiguous 20 s blocks per case stay outside location selection. [Sealed receiver and control traces](positions.jsonl.gz)

## Geography and frequency

Forced errors and the tile-centre comparator are geographic distances. The final three numeric columns are held posterior-conditional rate residuals in Hz/s, normalized to 11.5 GHz. These are residuals in the mixture and can stay low when several irrelevant orbits have similar rates. There are no absolute CFO residuals for the trackless estimator. Both calibration arms are identical.

| Offer | Synchronous forced km | Shifted forced km | Density forced km | Centre km | Sync rate RMS | Shifted rate RMS | Density rate RMS |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| DS26-0261, containing | 6.33 | 17.02 | 22.31 | 8.19 | 123 | 137 | 128 |
| DS29-0519, containing | 6.04 | 6.04 | 16.47 | 8.19 | 124 | 129 | 128 |
| DS26-0070, omitted | 46.31 | 62.33 | 61.29 | 51.23 | 131 | 130 | 127 |
| DS29-0316, omitted | 48.73 | 66.04 | 65.04 | 55.19 | 131 | 131 | 126 |
| Qin waveform, containing | 5.11 | 21.42 | 21.42 | 8.94 | 122 | 128 | 126 |
| Qin waveform, omitted | 4.03 | 26.02 | 19.67 | 14.03 | 122 | 128 | 126 |

Original no-repair v5 produced c0 fixes of 1.39 and 0.25 km on the two real containing requests. All four original options are included for those requests only, with the same authenticated native input and offer. V5 can use additional causal history and a richer RF model. The waveform replay uses the complete native GLRT emitted by the already generated dual CI16 input at the independent simulated site and its original two offers. Its installed phase release issued 1.02/0.75 km for the containing offer in c0/fitted order and issued the omitted offer at 1.58/1.53 km. The trackless run withholds both. The waveform comparison uses no new waveform generation or raw IQ reprocessing. [Measured original scores](scores.json) · [Waveform provenance and installed comparison](../../track-recovery/waveform-site/README.md)

The synchronous model beat the shifted-timing control by 0.025–0.186 held log units at its selected site and the density control by 0.003–0.108. In DS29-0519 it found the same forced coordinate as the shifted control. The rate kernel was 122–125 Hz/s. Across the matched visible-orbit geometry at five generic inside sites, the median linearized strongest-direction 25 km change was 22.3–23.5 Hz/s, and the 90th percentile was 83.9–88.9 Hz/s. The signal mass on a typical held slice with signal posterior above one half was spread over 4.6–10.4 effective competing orbits. These measurements explain why moderate time registration and close forced guesses can coexist with weak spatial discrimination. [Exact geometry and rate work counts](positions.jsonl.gz) · [Held evidence chart](likelihood-support.png)

Each paired worker processed 268–545 lane slices, 1,127–1,898 endpoint alternatives and 10.0–28.6 million modeled satellite rates across the synchronous and shifted geometry. Median paired time was 11.44 CPU seconds and 21.68 elapsed seconds. The maximum elapsed time was 33.60 seconds and peak RSS was 152 MiB under a 512 MiB address-space limit. All six attempts completed. The two hypotheses using exactly the same observed Qin document have separate offered-region geometry jobs. [Input bindings](blind-plan.json) · [Prediction and source receipts](prediction-lock.json)
