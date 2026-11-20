# The 20 m publication guard on six recorded roof offers

The guard suppressed all four publications from tiles that omitted the surveyed receiver. It retained one of the two containing offers and withheld the other. Without the guard, all six offers published both arms. With the guard, one offer published both arms and five withheld both. All six services completed. [Chart, c = 0](charts/c0/measured-boundary-policy.png) · [Chart, fitted c](charts/fitted_c/measured-boundary-policy.png) · [Per-arm scores](scores.csv)

| Recording | Offered tile | Surveyed site to face | Guard-off error, zero / fitted | Guard-on decision |
| --- | --- | ---: | ---: | --- |
| DS26-0070 | Near inside | 1.687 km inside | 2.165 / 2.148 km | Withheld |
| DS26-0070 | Near omission | 1.663 km outside | 2.958 / 2.937 km | Withheld |
| DS26-0070 | 6 km omission | 5.982 km outside | 7.161 / 7.139 km | Withheld |
| DS26-0102 | Near inside | 1.900 km inside | 0.872 / 0.850 km | Published |
| DS26-0102 | Near omission | 1.874 km outside | 2.038 / 2.023 km | Withheld |
| DS26-0102 | 6 km omission | 5.980 km outside | 5.978 / 5.982 km | Withheld |

All five withheld fits landed at a tile face to numerical precision. DS26-0070 reached the face even though the site was 1.687 km inside its offered tile. DS26-0102's two retained endpoints had more than 2 km of fitted clearance. Each withheld decision kept the original endpoints as forced diagnostics, with the same Doppler RMS and frequency fit. The two recordings come from one roof. [Exact clearances, errors and frequency results](scores.csv)

Each offer used one invocation of the byte-checked installed `phase-release` receiver. The guard-off CLI returned the installed output byte for byte on all six offers. Guard-on used the historical `STOP_KM = 0.020` rule and preserved each numerical endpoint. The solver used the exact 25 km offered center for both the fit and sky screen. The complete archived native GLRTs, causal TLE history and project TrackConfig were bound before running. The numerical child received neither survey coordinates nor the offer-condition labels. [Protocol](PROTOCOL.md) · [Input and executable lock](source-lock.json) · [Prediction seal](prediction-lock.json)

The installed solves took 48.76–89.41 s wall and 48.07–88.22 cgroup CPU-seconds. Each ran on its assigned core under a 210 s deadline, 512 MiB cap and zero swap. Charged peaks were 287.18–344.15 MiB. Guard-on CLI elapsed time, including Python startup, was 0.120–0.209 s. Guard-off CLI elapsed time was 0.133–0.194 s. Both decision modes ran inside the same service after the numerical solve. [Per-offer resource receipts](resources.json)
