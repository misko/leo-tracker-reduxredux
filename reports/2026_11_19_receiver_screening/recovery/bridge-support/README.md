# Whole-track support recovery for the compact v5 bridge

The revised bridge returned both calibration arms on all nine archived recordings. All six new salted controls passed the geographic gate against original v5 in both arms. The two diagnosed recordings improved against the prior bridge but remained outside the original-v5 accuracy gate. Full stored-GLRT-to-position wall time was 44.54–99.08 seconds. The reclassification itself took 0.22–2.70 seconds. [Position charts](charts/index.html) · [Scores](scores.csv)

| Cohort | Arm | Original v5 median / P95 (km) | Prior bridge median / P95 (km) | Reclassified bridge median / P95 (km) | Within 10% of original |
|---|---|---:|---:|---:|---|
| Six new controls | c0 | 0.648 / 1.060 | 0.627 / 1.075 | 0.623 / 0.980 | Yes |
| Six new controls | Fitted c | 0.656 / 1.101 | 0.634 / 1.111 | 0.634 / 1.018 | Yes |
| Two diagnosed | c0 | 0.905 / 1.210 | 2.138 / 2.775 | 1.906 / 2.505 | No |
| Two diagnosed | Fitted c | 0.867 / 1.183 | 2.163 / 2.724 | 1.909 / 2.460 | No |

## Reclassification and retained support

The original detrended bridge provides the provisional receiver coordinate and a paired seed. Each curved track is then scored against the same causal catalogue and provisional geometry. When an admitted component challenges its owner, its observations are excluded from its shared receiver posterior solve. A previously omitted component already contributes no calibration rows. The frozen phase-and-bias profile ranks the visible catalogue, and up to four nominees plus the incumbent get evaluated with actual phase-shifted geometry and the ordinary Doppler, noise and alias gates. An admitted component changes identity only on a strictly better held score. A passing omitted component can return as a complete track. The new assignments and phase seeds feed the existing two-arm exclusion, family, signed and cavity stages.

The score holds the component out of the shared calibration at the provisional coordinate. That coordinate may have used the component. Candidate-local phase and constant terms are profiled on the held track. Across nine recordings, the new pass proposed 13 whole-track readmissions and five identity switches. The published archive keeps proposed changes and final accepted curved identities separately, with predictive-point counts per arm. [Protocol](PROTOCOL.md) · [Endpoint and identity archives](receipt.json)

- **DS29-0082.** The pass chose 67037 over 62556 on a 14-point track and 58445 over 59934 on a 28-point track. Both survived in both arms. The prior bridge had already corrected the 28-point track at the cavity stage and dropped the 14-point track. The revised bridge kept both, increased curved support from 794 to 808 points and raised predictive support from 174 to 202 points per arm. The revised cavity made no positive offer. c0 error fell from 1.430 to 1.240 km and fitted-c error from 1.539 to 1.296 km. Original v5 gave 0.567 and 0.517 km.
- **DS26-0066.** Three whole tracks totaling 95 points were nominated for readmission. The original gates kept 51 of those points across two tracks, increasing final curved support from 2,036 to 2,087 points. The pass made no identity switch. c0 error fell from 2.846 to 2.571 km and fitted-c error from 2.786 to 2.521 km. Original full v5 gave 1.244 and 1.218 km after a separate post-cavity reassociation.
- **DS26-0036.** One 12-point curve changed owner and total curved support held at 1,974 points. c0 error fell from 0.892 to 0.852 km and fitted-c error from 0.752 to 0.738 km. The six new controls are charted separately from all three previously seen recordings. [Diagnosed chart](diagnosed/figures.json) · [Comparison chart](comparison/figures.json) · [Confirmation chart](confirmation/figures.json)

## Timing and RF

| Recording | CPU | Compact stock wall (s) | Prior bridge wall (s) | Reclassified bridge wall (s) | Reclassification (s) |
|---|---:|---:|---:|---:|---:|
| DS26-0036 | 22 | 134.54 | 69.67 | 70.51 | 1.21 |
| DS29-0082 | 21 | 76.61 | 54.86 | 53.71 | 0.22 |

Fresh bridge pairs ran on the same pinned core, with order set before inference. Their median wall times were 73.46 seconds for the prior bridge and 72.73 seconds for reclassification. Median worker CPU was 54.18 and 54.20 seconds. The reclassified bridge spent 19.95–41.58 seconds in native preparation after reading the stored document. The sum of the logged inference stages was 19.90–52.00 seconds. Complete wall includes binding and building the projector library. Historical compact endpoint times are excluded from speed comparisons. The whole archived pipeline still exceeds the earlier 10–30 second target. The last worker completed 593.4 seconds after the first lock, within the shared 900-second cap. [Timing and endpoint table](scores.csv) · [Sealed schedule](source-lock.json)

| Recording | c0 conditional RMS, prior → reclassified (Hz) | Fitted-c conditional RMS, prior → reclassified (Hz) |
|---|---:|---:|
| DS29-0082 | 98.537 → 97.879 | 98.149 → 97.718 |
| DS26-0066 | 64.935 → 64.973 | 65.001 → 65.052 |
| DS26-0036 | 74.648 → 74.550 | 74.648 → 74.530 |

Conditional RMS is measured on each method’s retained evidence. DS26-0066 gained support and geographic accuracy while its RMS increased slightly. DS29-0082 gained both support and geographic accuracy against the prior bridge, and still trails the compact control geographically. The full score table includes all four original v5 options and both calibration arms for every recording. The frozen input boundary accepts the original supplied roof tile. There are no alternate offers in this study.

The first source lock exposed an output serialization error. Four candidate attempts failed to publish positions. The corrected replay used the same scientific roster, source dependencies and shared deadline. All 20 corrected jobs returned genuine positions. The three applicable fresh prior-bridge results reproduced the previously published latitudes, longitudes and RMS exactly. [Initial attempt ledger](initial-serializer/README.md) · [Matched replay receipt](receipt.json)
