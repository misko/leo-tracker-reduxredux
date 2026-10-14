# Original native-clock winners: branch responsibility and residual audit

A zero-fit, reference-free audit of DS22-001's original-prior matched full/low/high training winners found that the full fit assigns similar fractions of both bands to signal. Each half-only winner fits its own band more tightly. The combined winner does not collapse onto one satellite, and these diagnostics do not establish a likelihood normalization bug.

All three states were evaluated on every training observation using the same original common-clock prior, bank, native observation times, branch inventory and calibration frame. The half-only winners' own masked objectives were replayed before scoring their full observations. Six objective evaluations and three posterior reconstructions completed in 33.82 seconds, with zero optimizer calls and no reference or held reads.

| Fitted view / scored band | Windows | Signal mass | Clutter mass | Weighted absolute residual median (Hz) | p95 (Hz) | Weighted RMS (Hz) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Full / low | 1811 | 1227.964 | 583.036 | 49.801 | 258.864 | 112.049 |
| Full / high | 1418 | 965.490 | 452.510 | 65.114 | 268.398 | 127.397 |
| Low / low | 1811 | 1361.834 | 449.166 | 45.604 | 217.531 | 98.214 |
| Low / high | 1418 | 98.504 | 1319.496 | 189.567 | 402.965 | 235.467 |
| High / low | 1811 | 135.525 | 1675.475 | 204.504 | 432.484 | 238.115 |
| High / high | 1418 | 979.920 | 438.080 | 55.158 | 251.937 | 110.648 |

Residual quantiles use the joint posterior weight of each native satellite/branch residual, wrapped at the 2.5 MHz sample rate. They are not quantiles of posterior-averaged residuals. The likelihood's fixed Gaussian sigma is 125 Hz. At the full winner, 573 low and 448 high windows have clutter posterior above 0.5. Median clutter probabilities are 0.003946 and 0.004481, while each band's 90th percentile is 1: the distribution separates strongly assigned signal from rejected observations.

The candidate bank contains 46 satellites and five padded branch slots. Available native branch counts are fixed across states: low has 1061/663/87 windows with one/two/three branches; high has 961/419/38. No branch has measured waveform evidence. Full-winner effective satellite counts, computed as inverse squared occupancy fractions, are 10.845 low and 13.694 high. The largest satellite signal fractions are 19.094% and 13.358%; satellite 66616 is largest in both bands. These summaries describe assignment concentration, not assignment correctness.

Opposite-band signal mass drops sharply at half-only endpoints. Their receiver/group calibration is constrained only by the scored band, so extrapolating that calibration to the excluded band is not a controlled test of physical cross-band consistency. The finding should motivate a matched calibration/assignment diagnostic, not an unsupported claim that the halves identify different physical signals. Own-band improvements can reflect additional fitting freedom and do not prove improved geography.

The native likelihood and B's likelihood represent different observation models. For an unmeasured, singleton, visible matching branch, the source-derived signal/clutter odds ratio involves the sample-rate/alias-period factor and the available-branch count. This motivates checking assignment calibration, but this audit does not estimate the true clutter rate or justify changing a normalization constant. The previous temporal-association trial was negative; singleton families here are the intentional established baseline, not an accidentally omitted option.

The first diagnostic namespace failed its strict posterior closure check and was preserved without a report. Its diagnostic prediction arithmetic grouped group offsets differently from the actual evaluator. New source `ec8fd9be4` retains the evaluator's exact operation order; all three actual states replay NLL, satellite posterior and clutter posterior with exactly zero difference, and total probability closes within 2.22e-16. A large-offset component regression covers this arithmetic. No model, fit, acceptance threshold or frozen source changed. The corrected metadata explicitly counts measured branch entries.

Evidence: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/ds22-native-responsibility-audit-v2/report.json`, SHA-256 `afc61fef95d49b01a021840f68b4703d58a21071219dc4fe13f2da060219f747`. The original failed diagnostic is retained at the neighboring `ds22-native-responsibility-audit-v1` namespace. Original selected states remain bound to `local/ds22-native-view-pilot-v2`; no reference ranking selected the audited states.
