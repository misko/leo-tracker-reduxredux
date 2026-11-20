# Reuse the fixed observation-time projection in constrained v5

The exact phase-release package repeatedly rebuilds a three-column time design and solves its quadratic fit for each gate evaluation. This optional overlay factors that design once per held row set in a cavity hypothesis. Both calibration arms and all five phase refits then project each new residual onto the same orthonormal basis. Final gate replays still use the original least-squares calculation. Rank-ambiguous designs and provisional scores near the BIC comparisons inside the optimizer use the original calculation as well.

The direct DS29-0247 reserve pair spent 77.97 s in the full cavity stage with the phase-release receiver and 62.36 s with the prepared projection. This stage also includes family nomination. The whole matched service took 135.17 s with stock and 138.03 s with the overlay. Differences in earlier stages offset the cavity reduction.

## Matched release runs

| Saved narrow capture | Package | Wall (s) | Cgroup CPU (s) | Cavity wall (s) | Charged peak (MiB) | Cavity offered |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| DS29-0247 | Phase-release stock | 135.17 | 128.72 | 77.97 | 322.64 | Yes |
| DS29-0247 | Prepared projection | 138.03 | 130.67 | 62.36 | 319.07 | Yes |
| DS29-0174 | Phase-release stock | 50.44 | 49.96 | 6.75 | 281.57 | No |
| DS29-0174 | Prepared projection | 52.06 | 50.70 | 7.98 | 294.40 | No |
| DS26-0237 | Phase-release stock | 70.48 | 69.73 | 10.83 | 318.48 | No |
| DS26-0237 | Prepared projection | 80.22 | 75.31 | 10.51 | 314.29 | No |

Each pair uses the same complete saved narrow factors, original truth-free request, initial tile, causal catalogue and physical 512 MiB, zero-swap service cap. Each case uses one numerical thread and the same core for both methods. The phase-release memory diagnostic used a separate observer and records, so its elapsed times are outside this comparison.

Both methods returned both arms on all three captures. Both held controls followed the path without a cavity offer and exactly matched every published field other than timing. On the reserve, the candidate c = 0 latitude differs by about 0.46 μm and conditional RF RMS by \(7.15\times10^{-11}\) Hz. Fitted c differs only in the last displayed longitude digit and has identical RF RMS and frequency objective. The c = 0 objective differs by about \(5.09\times 10^{-9}\). Projection and observation counts, branch count, and cavity offer agree. The position errors remain 0.711 km for c = 0 and 0.980 km for fitted c. [Position and RF scores](scores.csv) · [Parity](parity.json)

## Work inside the solver

The original DS29-0247 Python call profile recorded 30 constrained phase fits across three hypotheses. Constrained refinement occupied 50.27 s of the 141.07 s profile. Its gate screens made 126,636 calls to the noise diagnostics, which spent 17.93 s with those calls. The native bound ran 2,036 times across the full inference and spent 13.78 s. Native posterior inversion supplies condition checks and robust precision updates, so this overlay keeps it.

| Matched lightweight reserve probes | Phase-release stock | Prepared projection |
| --- | ---: | ---: |
| Constrained hypotheses | 3 | 3 |
| Constrained phase fits | 30 | 30 |
| Gate evaluations | 686 | 681 |
| Native likelihood bounds | 689 | 682 |
| Original noise screens | 126,636 | 2,196 |
| Time-only bases prepared | 0 | 348 |
| Prepared noise screens | 0 | 123,525 |
| Constrained process CPU (s) | 42.02 | 38.45 |

The lightweight probes match each corresponding direct release result. They show an 8.5% reduction in constrained CPU and count 98.0% fewer decompositions in the selected stage. The 2,196 original calls include final gate replay and fallback. The linearly equivalent projection changes rounding inside the continuous finite-difference objective and constraint evaluations. Visit counts therefore differ slightly even though the 30 fits, geometry and publication are preserved. The broader matched stage timings above are from the uninstrumented direct releases. A first candidate cProfile diagnostic hit a host XFS startup lock and consumed 0.126 s CPU before its deadline. The separate lightweight pair reached inference. [Branch-probe evidence](diagnostics/receipt.json)

At fixed observation times, both solvers fit the span of \([1, t, t^2]\). The original repeatedly calls least squares, while the overlay forms \(Q\) once and computes \((rQ)Q^{\mathsf{T}}\) for each residual. The shifted and scaled time coordinates are identical. The release also reuses the time-only quantities in the other unchanged noise statistics. The equivalent projection uses a different floating-point operation order. Both observed coordinate deltas are reported above. Tests cover varying time bases, multiple residual rows, deficient rank and all three BIC comparison boundaries.

The installed package shares the original compiled libraries. It adds the projection module and a constrained-solver call site, with the native manifest relocated to the installed path. [Study protocol](PROTOCOL.md) · [Installed source and binary lock](candidate-lock.json) · [Measured resources](resources.csv) · [Position chart manifest](figures.json)

## Independent constrained-branch witness

The separate same-core DS29-0357 pair used the sealed capture-era factors. Its prior compact receiver recorded a cavity offer before this study. A stock probe verified one actual constrained hypothesis before the candidate ran. DS26-0122, DS26-0036, and DS26-0052 were also examined from archived offers. Each stock probe returned a position with zero constrained calls, so those screening diagnostics have no candidate leg.

| DS29-0357 monitored branch | Phase-release stock | Prepared projection |
| --- | ---: | ---: |
| Constrained phase fits | 10 | 10 |
| Gate visits | 216 | 209 |
| Native bounds | 218 | 210 |
| Original noise screens | 41,856 | 768 |
| Time-only bases prepared | 0 | 120 |
| Prepared noise screens | 0 | 39,744 |
| Constrained CPU (s) | 12.12 | 8.99 |
| Monitored service wall (s) | 71.36 | 63.12 |
| Charged peak (MiB) | 325.6 | 314.5 |

Both arms exactly match the original coordinates, conditional RF RMS, frequency objectives, and published decisions and counts. Geographic errors were 0.436 km at c = 0 and 0.434 km at fitted c. The decrease in constrained CPU was 25.8%. Both services shared the same 512 MiB, zero-swap limit and lightweight monitor. [Held position chart manifest](diagnostics/DS29-0357/figures.json) · [Both-arm scores](diagnostics/DS29-0357/scores.csv) · [All supplemental diagnostics](diagnostics/receipt.json)
