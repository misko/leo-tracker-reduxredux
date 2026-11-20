# Native clock geometry

The physical-sign frame timing model failed on both measured roof recordings. A separate relative receiver-drift measurement qualified in the low band of both, but adding it to the same anonymous causal-orbit fit produced zero published positions across six offers. All six numerical fits retained a diagnostic forced position.

## Frame timing and clock measurement

Two signals in the same receiver, window and RF share the sampled counter. Their measured frame-epoch difference should vary as the negative integral of their differential CFO, scaled by sample rate over RF, up to an independent affine transmitter term. A fixed CFO alias also becomes part of that affine term. The worker rechecked both native gate memberships, counters, ranks and CFOs against authenticated same-lane peak-pair witnesses. It used no nearest-time interpolation or extrapolation. It fit the affine part on the first two-thirds of each contiguous piece and evaluated the final third. The frozen gate required held error at most 3 ADC samples and a 20% advantage over both reversed sign and affine alone. The planted law passed with physical RMS below 0.01 samples and rejected the shifted and sign-reversed controls. [Timing protocol](PROTOCOL.md) · [Measured trace](clock-measurements.json)

| Stream | Exact pair points across valid pieces | Pieces | Median held physical RMS, samples | Reversed | Affine only | Qualified training / held blocks |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS26-0261 | 287 | 16 | 46.92 | 6.43 | 24.48 | 0 / 0 |
| DS29-0519 | 471 | 26 | 48.27 | 7.31 | 19.02 | 0 / 0 |
| Independently emitted Qin waveform | 0 | 0 | — | — | — | 0 / 0 |

The reflected relationship was stronger in the recordings, but its origin remains unresolved. The test used paired detections with anonymous, measured peak memberships. It does not establish a firmware sign error or validate individual satellite identities. The waveform emits one intended signal per tuned lane and supplied no qualifying two-signal pieces. Frame timing contributed no site information to the fit. [Timing measurements and input lock](measurement-lock.json)

The alternate measurement uses simultaneous copies of the **same** pilot on both RXs at identical channel, RF, probe offset and counter. Independent per-channel calibration produced no usable relation. The prospectively frozen fallback fits a band-level RX1−RX0 drift with different wrapped intercepts by tuned channel. It qualifies on chronological calibration-check visits inside the position-training blocks. The position holdout has separate contiguous blocks. DS26-0261 gave −1.18 Hz/s, with 37/40 agreeing check visits across three channels and 113.51 Hz check RMS. DS29-0519 gave +1.05 Hz/s, with 46/50 across four channels and 124.16 Hz RMS. Both one-sigma floors of 1.5 Hz/s include zero. The high band and waveform supplied no qualifying drift relation. [Pooled protocol](POOLED-PROTOCOL.md) · [Support and conditioning](clock-geometry-support.png)

The fallback adds one rank-one Gaussian relation per qualified band to the previous anonymous joint-pass normal equation. A common receiver oscillator drift remains free. Tile changes leave the calibrated relation unchanged. The common anonymous arc extraction, causal SGP4 orbits, weak drift priors, starts, fit budget and held checks match the shared-clock control. The previously reported control duplicated one profile fit across both endpoints. That raw receipt is preserved. The derived comparison shows the single measured control fit in `c0` and marks `fitted_c` unavailable for both methods. At constant RF in each arc, free intercepts absorb the entire fixed `c` term, so its projected column has norm zero. Both calibration arms of the original four v5 options retain their actual results. [Position lock](prediction-lock.json) · [Control provenance and score lock](score-lock.json)

## Position and held RF

The cohort consists of two measured roof recordings, each with the original containing offer and an independently generated, geometrically verified offset offer. An independent location from a saved, emitted Qin waveform supplies one containing and one omitted offer. Six identical native/catalogue/offer requests were compared to the historical shared-clock control. Survey and emission locations were used only after prediction sealing. The simulated waveform is one independent location. The measured roof recordings do not establish geographic transfer among different receiver sites.

| Offer | Forced error, km | Shared-clock forced error, km | Tile centre error, km | Held CFO RMS, Hz | Shared-clock held RMS, Hz | Profiled radius, km |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS26-0261 containing | 2.72 | 2.99 | 8.19 | 119.94 | 117.36 | 31.83 |
| DS29-0519 containing | 1.61 | 1.48 | 8.19 | 203.69 | 203.00 | 41.02 |
| DS26-0261 offset | 46.19 | 46.20 | 57.96 | 389.27 | 398.66 | 29.21 |
| DS29-0519 offset | 47.43 | 47.48 | 59.41 | 1014.38 | 1012.25 | 16.30 |
| Emitted waveform omitted | 23.30 | 23.30 | 14.02 | 428.44 | 428.44 | 35.91 |
| Emitted waveform containing | 21.53 | 21.53 | 8.94 | 395.33 | 395.33 | 46.40 |

The candidate published 0/2 containing roofs, 0/2 omitted roofs and 0/2 waveform offers, exactly matching the shared-clock control's availability. The candidate's conditional worst-axis radii were 16.30–46.40 km, all above the 12.5 km limit. Removing the receiver clock priors increased them to 21.54–47.30 km while retaining phase regularization and the same local soft orbit weights. Only DS26-0261 containing also cleared the held site-lead gate. The waveform positions and held RF were exactly unchanged with the relation absent. The held RF and geographic errors moved in different directions on the roof offers. [Per-offer scores](scores.csv) · [Two-arm position charts](charts/README.md)

For the two exact containing roof requests, all four original v5 options agreed within each arm. Their horizontal errors were 1.39/0.25 km with `c=0` and 1.36/0.32 km with fitted `c` in recording order. Their corresponding conditional CFO RMS values were 94.62/100.75 Hz and 85.06/81.34 Hz. Conditional v5 RMS and this receiver's held-block RMS have different boundaries. For the emitted waveform, its installed receiver's same-request `c=0` errors were 1.58 km on the omitted offer and 1.02 km on the containing offer. The two generated roof omissions have no same-request original v5 reference. [Scores and original-reference columns](scores.csv)

The exact timing and independent-channel clock audit ran on three unique saved native inputs at 0.51–0.93 CPU s and 0.54–1.63 worker wall s each, up to 151 MiB RSS. For all six offers the fallback used 1.04–2.05 process CPU s and 1.48–5.24 elapsed s from reconstructing the native request to the decision, with 156–189 MiB peak RSS. Same-pilot calibration took 0.04–0.30 CPU s within that interval. Workers used one thread and a 512 MiB address-space cap. The fit considered 132–234 shortlisted arc/orbit combinations per offer. Historical control wall time came from a separate run and does not support a speed comparison. [Timing and work counts](scores.csv) · [Numerical receipts](positions.jsonl.gz)
