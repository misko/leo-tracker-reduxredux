# Held code and carrier as separate range measurements

The positive pilot-arrival difference failed as a second geometry measurement on all four measured roof recordings. It lost to both a clock-only fit and a reflected-range fit. Signed integrated Doppler on those same endpoints easily beat the CFO shuffle. The joint receiver withheld all twelve measured offers. At the separate blinded generated site the physical code/carrier link passed, but the held spatial evidence was still below the release threshold. [Held measurement figure](code-carrier-support.png) · [Full position charts](charts/index.html) · [Per-case scores](scores.csv)

## Measurement and controls

Earlier studies forecast the next epoch for acquisition, tested absolute timing on original v5 satellite associations, or included epoch in joint pass fitting. Here a CFO-only chronological tracker joins each lifted CFO back to the exact original gated candidate. An anonymous causal satellite and orbit time correction are selected on its carrier prefix and then held fixed for every geographic hypothesis and both observables. The timing branch therefore cannot improve its own orbit labels. Its positive range-change observation comes from the last third of the same arcs as held integrated CFO. [Epoch forecasts](../../receiver-core/track-timing/README.md) · [Earlier labelled range experiment](../../receiver-core/range-epoch/README.md) · [Earlier joint-pass receiver](../../../2026_11_19_short_receiver/joint-pass/README.md)

For hardware counter (C), integer plus fractional local epoch (e), ADC sample rate (F_s), and a fixed counter origin (C_0), the arrival residue is `(((C - C0) * 750) mod Fs) / 750 + e`, reduced modulo `Fs / 750`. The difference cancels both a fixed hardware origin and a fixed track transmission phase. Increasing slant range (ho) predicts a positive increment `Fs * Δρ / 299792.458` when range is in km. Increasing range lowers signed carrier CFO, so the integrated carrier observable is `−Fs / RF * ∫CFO(t) dt`, evaluated by trapezoid between the identical visits. A fixed orbit time correction still changes the orbit trajectory and was estimated on the prefix. Geometry uses causal ECEF interpolation at nominal probe midpoints. [Frozen protocol](PROTOCOL.md)

The archived stream generation, increasing hardware counters and same-visit receiver coordinates were checked before inference. Packed payload offsets omit retune gaps. Intervals join only exact receiver, RF, channel and edge observations on a single linked arc, with at most 2.5 s between endpoints. The original hardware counter retains elapsed time through intervening retunes. A new transmitter schedule can change pilot phase across visits. The free-clock control admits a separate affine drift on each arc, and the held residual retains any schedule change it cannot predict from the prefix. The estimator receives the coarse offer center. The scorer opens the survey after prediction sealing. [Input seal](blind-plan.json) · [Prediction seal](prediction-lock.json)

## Measured roof

The four disjoint captures supplied 106 anonymous arcs, 3,215 training intervals and 1,565 held intervals. Values in the table are held RMS in ADC samples at the shared joint fit in each containing square. All comparisons use identical endpoints. The two code clock controls and both shuffles have their own train-only nuisance fits. Shuffles act on the corresponding measurement after the common track linkage and orbit shortlist are frozen.

| Recording | Positive code | Clock only | Reflected code | Epoch shuffle | Integrated CFO | CFO shuffle |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| DS26-0006 | 112.47 | 65.76 | 51.98 | 476.33 | 0.487 | 44.72 |
| DS26-0034 | 430.84 | 418.38 | 411.76 | 648.90 | 0.423 | 48.89 |
| DS29-0357 | 332.71 | 319.14 | 313.98 | 1063.12 | 0.410 | 44.65 |
| DS29-0519 | 267.14 | 249.07 | 245.25 | 1077.10 | 0.266 | 43.67 |

The free-oscillator branch likewise lost to its own clock-only control on all four and produced positive-code RMS of 96.95–431.60 samples. The signed code-minus-carrier closure at the shared fits was 112.61–430.89 samples after nuisance profiling. The fitted code branch still increased the nominal weakest training singular value from 0.18–0.31 km⁻¹ for carrier alone to 0.84–1.36 km⁻¹, conditional on fixed orbital identities and the assumed code noise. The held code failures prevent interpreting that increase as usable geometry. [Profiled rank and closure](scores.csv) · [Exact plotted measurements](code-carrier-support.csv)

The shared joint forced median was 18.779 km for containing offers, compared with 8.193 km for carrier only, 9.172 km with free clocks, and 8.193 km for the centers. The shared joint issued 0/4 publications for each of containing, near-missing and far-missing conditions. The free-clock branch had the same publication counts. Near-missing offers excluded the survey by about 2.32 km and the far controls by about 32.35 km. Each of the four roof measurements comes from one physical installation. [Matched position data](roof/queries.json) · [Published and forced counts](summary.json)

## Blinded generated site

The simulation emitted on the original frame lattice and used retarded propagation, signed Doppler, independent transmitter offsets, receiver clocks and measurement noise. At the containing shared joint fit the physical code error was 1.073 samples, compared with 40.032 clock-only, 79.753 reflected and 496.727 shuffled. Integrated carrier error was 0.126 sample versus 8.979 shuffled. Closure was 1.168 samples. With free clocks, the matched physical code, carrier and closure errors were 0.181, 0.096 and 0.165 sample. These outcomes establish the expected sign and units for this generated observation contract. [Released simulation parameters](simulation-release.json) · [Simulation plots](charts/c0/code-carrier-simulation-joint.png)

The shared joint forced error was 5.280 km, compared with 4.600 km for carrier only and for the offer center. The shared joint held spatial lead of +0.034 missed the +0.25 release threshold. Neither oscillator branch published on any of the three offers. Even the CFO-shuffled branch forced a 0.486 km point on the containing offer, while its held CFO residual was 8.975 samples. The forced distance alone would give the wrong conclusion about that control. [Simulated position and shuffled outcomes](scores.csv)

The RF-dependent `c` column is exactly a constant times interval duration within each RF track, so it belongs to the fitted per-track carrier-level span and adds no rank. Its largest projected residual norm was `4.0e-17`. All numeric positions use the `c = 0` gauge and the fitted arm is marked unavailable. All five workers completed on CPUs 20–21. Roof worker wall time was 4.68–6.59 s and the simulation took 15.30 s. Worker CPU totaled 16.43 s with 286.46 MiB peak RSS under the 512 MiB cap. [Per-arm score and runtime data](scores.csv) · [First worker outcomes](predictions.jsonl.gz)

## Reproduce

Use fresh local paths and copy the protocol to the report path. The initial input preflight treated the packed payload offset as a physical counter base. It was corrected before input or prediction sealing because packed payload offsets skip hardware retune gaps. Only the continuous original hardware counter supplies frame time. [Exact source archive](as-run-sources.tar.gz) · [Exact generated factors and seed](as-run-simulation.tar.gz)

```bash
trial=tools.pipeline_eval.qualification.code_carrier_trial
python -m "$trial" stage "$WORK" --report "$REPORT" --simulation-seed-file "$SEED"
python -m "$trial" run "$WORK" --report "$REPORT"
python -m tools.pipeline_eval.qualification.code_carrier_results "$WORK" --report "$REPORT"
```
