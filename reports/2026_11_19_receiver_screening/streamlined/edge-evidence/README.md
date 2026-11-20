# Conditional Doppler evidence at a compact tile face

The blinded two-site replay made **the same decisions as the frozen terminal rule** in both calibration arms. It kept both containing-center fixes and one of the two legitimate near-edge fixes. The valid 1.193 km-inside offer and both near omissions provided weak directional evidence and stayed withheld. Both far omissions stopped at the existing initial support check. The authentic shifted roof produced exactly the previous position and frequency endpoints. [Sealed outcomes](prediction-lock.json) · [Position and RF scores](scores.json)

The earlier wide halo introduced a new assignment search outside the tile. It withheld every completed containing test, and overlapping physical arcs could receive multiple satellite votes. Separately, a covariance-circle check on measured roof offers left the known false interior fits intact and lost a valid near-edge fix. The present experiment holds assignments and aliases fixed, and asks only whether the local direction normal to one active compact face has convincing Doppler support. [Earlier halo tests](../../inference/portable-gate/halo/README.md) · [Measured boundary controls](../../refinement/boundary-roof/README.md)

At each face contact the verifier refits the original receiver and orbital nuisance design at matched points 1.5 km inside and outside the active tile face. Each orbit family holds out its middle third of unique times. The models fit on the flanking thirds in each arm independently, and use the same held points and Doppler noise normalization. A family contributes one contrast. The paired decision requires both arms' outside-minus-inside loss to exceed 1.64 across-family standard errors, with at least two-thirds of the family directions agreeing. Short support, multiple active faces, unsupported cavity changes and weak evidence retain the original withholding. Successful verification would release the original compact endpoints unchanged. The held scores are conditional on the compact fit's terminal associations, mask and face, which use the whole scan. [Frozen protocol](PROTOCOL.md) · [Source lock](source-lock.json)

## Diagnostics before the blind draw

The earlier valid offer with its site 0.593 km inside had normalized inward contrasts of 0.221/0.049 from the terminal suffix, against across-family standard errors of 0.342/0.319. Only two of seven families favored inside in each arm. Moving the holdout to the center third reduced held RF RMS at the two hypotheses from about 91–99 Hz to about 68 Hz and increased inward agreement. The centered normalized contrast of 0.038/0.024 on the legitimate offer still overlapped 0.026/0.014 from its paired known omission. Only 5/7 and 4/7 orbit families favored inside on the legitimately containing offer, and both contrasts were smaller than their standard errors. None of the archived diagnostic offers met the predeclared paired directional support rule. The centered mask and original threshold were locked without inspecting the new sites. [Suffix diagnostics](suffix-diagnostics.json) · [Centered diagnostics](centered-diagnostics.json)

## Blind independent geometry

Two private seeds drew sites at 52.38°N and 23.65°S, at least 1,416 km and 1,861 km from their nearest bound earlier site, respectively. Each used a different causal TLE payload and authentic preceding archive history. The four tile offers at each site reuse its same 300 s native candidate stream. Simulated range-rate and frame factors carry measured donor disturbance windows and visit gaps. The later trajectory proxies and physical locations stayed outside inference. [Input seal](input-lock.json) · [Causal histories](history.json) · [Released labels and seeds](released-labels.json)

Pairs in the table follow zero/fitted calibration. Error is horizontal distance in kilometres. The signed true edge margin is measured in the physical tangent plane. Both methods had the same position and RF endpoints on all eight matched offers.

| Site | Containing center error | Valid near-edge margin and result | Omitted near-edge forced error | Far omission |
|---|---:|---|---:|---|
| 52.38°N | 3.463 / 3.647 | +0.829 km, published 2.063 / 1.837 km | 1.594 / 1.739 | Early withheld at −56.372 km |
| 23.65°S | 1.390 / 2.131 | +1.193 km, withheld, forced 1.371 / 1.240 km | 1.196 / 1.191 | Early withheld at −43.211 km |

The north near-inside endpoints remained interior and did not invoke the local test. All three cases that did invoke it had a unique eligible face, with seven to ten families and 224–275 held points. Both calibration arms gave weak evidence in every tested case. The signed normalized contrast is positive when the inside hypothesis predicts the held points better. The weak north omission also had a positive mean, so the direction of the mean alone would have accepted a wrong tile.

| Face-tested offer | Held RF RMS inside / outside, zero `c`, Hz | Held RF RMS inside / outside, fitted `c`, Hz | Normalized contrast ± standard error, zero / fitted |
|---|---:|---:|---|
| North near omission | 91.921 / 92.087 | 91.820 / 91.811 | +0.00775 ± 0.01642 / +0.00189 ± 0.01552 |
| South near inside | 63.196 / 63.409 | 63.156 / 63.250 | +0.00786 ± 0.01101 / +0.00336 ± 0.00860 |
| South near omission | 64.326 / 64.182 | 64.342 / 64.247 | −0.00693 ± 0.01066 / −0.00462 ± 0.00913 |

The northern far stock worker was a complete independent numerical replay and issued errors of 73.727/74.625 km with conditional RF RMS of 80.666/80.436 Hz. It took 90.95 s, versus 41.58 s for the original majority veto on the same request. The southern far stock case was not independently run. Both early candidate abstentions had no fitted coordinate. The retained near-edge forced endpoints had stock conditional RF RMS of 77.694/77.646 Hz in the north and 55.498/55.420 and 57.426/57.377 Hz in the two southern offers. The held RF above comes from the separate local comparisons. [Independent stock control and scores](scores.json) · [Zero-calibration figures](figures/c0/transfer.pdf) · [Fitted-calibration figures](figures/fitted_c/transfer.pdf)

## Measured parity and computation

On the original measured DS26-0036 detector factors with the 7 km east-shifted containing tile, the overlay returned exactly the previous paired endpoints and conditional RMS. Its errors were 1.261/1.197 km and conditional RF 74.760/74.682 Hz. The face test did not activate on the authentic request. The ten fresh workers finished in 265.10 s with no deadlines or unsupported face decisions. The three activated local checks took 24–34 ms each. This panel establishes that the local check is cheap and that its conditional Doppler evidence does not resolve these boundary ambiguities. [Measured exact parity](measured-parity.json)
