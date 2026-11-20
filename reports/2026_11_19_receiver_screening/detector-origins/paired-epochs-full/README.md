# Two receivers proposing pilot start times

Both wideband detectors returned positions on both reserve recordings. Sharing proposed pilot start times between simultaneous receivers improved DS26-0122 and worsened DS29-0247. Neither shared-proposal fix met the 10% v5 target. Each detector still scored each receiver's own complex samples. The comparison changed only which candidate start times it searched. [Fitted distributions](../charts/fitted_c/paired-epochs-full.png) · [Zero calibration](../charts/c0/paired-epochs-full.png) · [Protocol](PROTOCOL.md)

| Recording | Original v5, km | Own proposals, km | Shared proposals, km | Own / shared whole wall, s |
| --- | ---: | ---: | ---: | ---: |
| DS26-0122 | 0.751 / 0.747 | 1.320 / 1.318 | 1.114 / 1.112 | 198.1 / 208.3 |
| DS29-0247 | 1.320 / 1.458 | 1.326 / 1.338 | 1.833 / 1.809 | 136.2 / 146.0 |

Position cells show zero calibration followed by fitted calibration. Fitted conditional RF RMS increased from 85.51 to 88.77 Hz on DS26-0122 and from 65.36 to 67.05 Hz on DS29-0247. Whole service CPU rose on both, from 290.46 to 309.13 s and from 185.35 to 209.98 s. These are two complete recordings of the same physical roof with one measured service per branch. [Paired scores](scores.csv) · [Raw and service timings](resources.json) · [Prediction seal](prediction-lock.json)

In the short detector study, sharing proposals recovered the same 43 of 47 capture-era positives and cost about 9.8% more CPU per dual visit. The full recording test shows the downstream variation those sampled peak counts did not capture. [Detector experiment and raw evidence](../paired-epochs/README.md)
