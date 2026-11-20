# A wider timing window around each proposed pilot start

Increasing the integer search radius from one sample to two improved the returned position on DS29-0127 and worsened it on DS26-0014, in both calibration arms. Both detectors returned two fixes. Both beat original v5 on DS26 and exceeded the 10% error allowance on DS29. The two recordings come from the same roof. [Fitted calibration](charts/fitted_c/scout-radius-all.png) · [Zero calibration](charts/c0/scout-radius-all.png)

| Recording | v5 error, zero / fitted (km) | Radius one, zero / fitted (km) | Radius two, zero / fitted (km) | Full elapsed, one / two (s) | Full CPU, one / two (s) |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS26-0014 | 3.415 / 3.405 | 0.472 / 0.755 | 0.552 / 0.904 | 172.18 / 165.47 | 216.64 / 207.78 |
| DS29-0127 | 0.621 / 0.567 | 0.756 / 0.721 | 0.698 / 0.670 | 161.50 / 152.78 | 190.55 / 201.44 |

All four whole-waveform replays finished under 512 MiB with zero swap. The radius-two detector met the 20 ms elapsed target on 6,887 of 13,175 valid dual-receiver calls, versus 8,048 for radius one. Conditional Doppler RMS fell on DS26 (97.39 to 95.35 Hz at zero calibration and 97.57 to 95.38 Hz with fitted calibration) even as position error increased. The median detector costs on this host and timings by stage are in the receipts. [All scores](scores.csv) · [Resource measurements](resources.json)

The detector-only comparison on a separate held set of 23 usable dual-receiver visits found the same 33 of 36 archived positives in both versions. Three signals moved onto their exact integer seeds. The narrower detector had already recovered them through fractional refinement. On the two complete waveforms the wider window produced fewer positive candidates on each recording, so matching the same 33 signals in the shorter trial did not guarantee the same position. The four proposed start times, frequency grid, eight output slots, complete I/Q, orbit inputs and position program were paired. The recording IDs were chosen before their first full replay. This follow-up used those same IDs. [Detector-only measurements](../scout-radius/README.md) · [Predeclared protocol](PROTOCOL.md) · [Prediction seal](prediction-lock.json)
