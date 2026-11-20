# Scalar Doppler noise filter

The scalar filter and the dense covariance produced the same decision and withholding reason on 12 measured roof recordings and three omitted-region queries. Both published eight roof fixes and withheld every omitted query. Across the 30 paired calibration results, the largest difference between forced positions was 9.5 micrometres. The largest conditional Doppler RMS difference was 0.0000000121 Hz. [Per-recording errors and the four original v5 options](scores.csv) · [Sealed prediction files](prediction-lock.json)

The dense calculation stores a triangular whitening operator for each track. The scalar version carries one correlated frequency error forward between successive observations. Its gain accounts for the elapsed time and for independent measurement noise. This gives the same whitening transformation for uneven sampling, repeated channel visits and long gaps. Both methods received complete stored GLRT factors, rebuilt the same tracks and causal orbits, and ran the same position and publication rules. [Implementation](../../../../tools/pipeline_eval/variants/innovation_noise.py) · [Prespecified trial](PROTOCOL.md)

| Host measurement on 12 roof recordings | Dense covariance | Scalar filter |
| --- | ---: | ---: |
| Median stored noise-operator bytes per recording | 1,103,884 | 144,244 |
| Median complete receiver CPU, seconds | 4.443 | 4.936 |
| Median position-fit time, seconds | 0.501 | 0.702 |

Median paired CPU increased by 68 ms for the whole worker and median peak resident memory increased by 1,174 KiB. The 7.65-fold reduction applies to the stored per-track matrices. The larger process still includes the detector factors, tracks and orbital bank. The dense controls reproduced their archived outputs exactly. Fitting calibration lowered conditional RF RMS on all 12 roof recordings and reduced geographic error on five of eight published fixes. [Paired timing and memory](resources.csv) · [Calibration effects](summary.json)

[Fitted-calibration roof chart](../charts/fitted_c/innovation_noise-roof.png) · [Zero-calibration roof chart](../charts/c0/innovation_noise-roof.png) · [Omitted-region chart](../charts/fitted_c/innovation_noise-omitted.png)
