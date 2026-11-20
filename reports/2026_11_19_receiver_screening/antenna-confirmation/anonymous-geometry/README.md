# Worldwide anonymous Doppler geometry

The receiver withheld **all six queries**, including four unshuffled native recordings and two deranged controls. On the four actual recordings, the worldwide training winners were 2,125–9,806 km from the surveyed position and lost to another sampled location on held data. A separate survey-only diagnostic recovered stronger slope-and-curvature evidence at the real position on three recordings. The blind search never received that position or an offered tile. [Prediction lock](prediction-lock.json) · [Support figure](anonymous-pass-support.png)

## Receiver and matched controls

The receiver links saved native GLRT peaks without orbit labels, measures quadratic Doppler coefficients on 15–30 s anonymous arcs and checks them on disjoint odd and even points. It expresses each profile at the equivalent 11.5 GHz carrier. A constant oscillator level and the constant RF calibration term are in the polynomial operator's null space. One bounded fractional drift from the early arcs is shared within each receiver and RF band. Every orbit gets the same slope and curvature operator on its predicted Doppler at the actual measured times. The causal orbit UTC stays fixed. The worldwide mesh and all refinement locations depend only on training data. Scoring the complete held arcs allows an orbit to explain each new profile at that fixed site and drift. The clock stays fixed, and the decision does not refit a held arc's level, phase or drift. [Frozen protocol](PROTOCOL.md) · [Source lock](source-lock.json)

Curvature-only uses the same arcs, site budget and causal catalogue and projects out each arc's slope. The deranged runs rotate complete measured shape vectors within each hardware chain and time split while leaving sample times, RF, profile uncertainty and TLE fixed. There was a positive location lead on one deranged run, but that run had only two confident held blocks where three were required. `fitted_c` is unavailable for both worldwide methods because its derivative column has norm zero. Both arms of original v5 remain visible on the same containing captures. [Numerical scores](scores.csv) · [Position figures](charts/README.md)

## Sealed position decisions

The four native recordings are separate acquisitions at the same measured rooftop. Two use the original containing offer in the evaluator and two use authentic frozen omitted queries. Omitted and containing labels do not reach inference. Neither worldwide method published on any query. All `c=0` rows produced forced coordinates, none inside the scored offer. Those coordinates are diagnostic. [Position receipts](positions.jsonl.gz)

| Recording and evaluation query | Shared-drift forced error, km | Curvature-only forced error, km | Shared-drift held score | Lead over best sampled rival |
| --- | ---: | ---: | ---: | ---: |
| DS26-0261 containing | 9,806 | 8,792 | 8.01 | −2.78 |
| DS29-0519 containing | 5,047 | 5,109 | 6.89 | −2.42 |
| DS26-0070 omitted | 4,340 | 6,496 | 7.42 | −2.32 |
| DS29-0316 omitted | 2,125 | 16,995 | 6.23 | −1.51 |
| DS26-0261 deranged | 13,664 | 13,526 | 6.62 | +0.19 |
| DS29-0519 deranged | 10,908 | 10,824 | 8.56 | −1.96 |

The two containing instances put the public tile centre about 8.19 km from the rooftop. The archived regional shared-clock control could try that region and withheld with forced errors of 2.99 and 1.48 km. All four original v5 options agreed by arm at 1.39 and 0.25 km in `c=0` and 1.36 and 0.32 km with fitted `c`. The worldwide shared-drift forced sites gave 261–355 Hz conditional held CFO RMS on matched arcs. Curvature-only gave 129–193 Hz after also removing each arc's slope from that RF diagnostic, yet its positions remained thousands of kilometres off. The regional control's held residual uses a separate likelihood and holdout boundary. [Scored controls and offer inclusion](scores.csv)

## Survey-only diagnostic after sealing

The nearest point of the original 384-cell mesh was about 394 km from the roof. After sealing the position outputs, a separate scoring job evaluated the exact survey coordinate, then eight 25 km rivals around it. Three of four recordings gave the survey site lower early and late shared-drift cost than the blind training winner and passed the local rival and distinct-family gates at that given coordinate. The curvature-only control's incorrect training winner had lower held loss than the survey site on all four recordings. This isolates useful regional information in some measured captures that the uniform worldwide proposal stage failed to reach. DS26-0070 supplied less local discrimination. The diagnostic uses the known position and adds no blind fixes. [Survey-only results](survey-diagnostic.json)

| Recording | Early loss at blind winner / survey | Held loss at blind winner / survey | Held survey lead over 25 km ring | Confident held blocks / orbit candidates at survey |
| --- | ---: | ---: | ---: | ---: |
| DS26-0261 | 3.91 / 1.32 | 8.01 / 2.20 | +1.65 | 3 / 6 |
| DS29-0519 | 4.08 / 1.48 | 6.89 / 3.48 | +0.89 | 3 / 5 |
| DS26-0070 | 3.31 / 4.99 | 7.42 / 6.56 | −1.65 | 2 / 1 |
| DS29-0316 | 3.77 / 2.37 | 6.23 / 2.51 | +1.01 | 3 / 4 |

Each joint candidate/control worker processed 14–20 training and 8–12 held profiles from catalogues with 9,803–11,191 valid causal orbits. It evaluated 632–656 locations and 2.99–5.08 million visible training orbit/profile comparisons. The six workers used 13.88–25.22 CPU seconds, 23.20–37.58 elapsed seconds and 386–506 MiB peak RSS each, on one CPU per worker. The 291-line estimator reuses the anonymous extractor and coordinate/SGP4 helpers. The separate dependency audit binds the earlier-pinned continuity linker omitted from the new top-level source list. Component tests cover the calibration null, planted orbit evidence despite unknown constant CFO, incorrect common drift and the integrity-preserving shape shuffle. [Worker evidence](scores.csv) · [Dependency audit](dependency-audit.json)
