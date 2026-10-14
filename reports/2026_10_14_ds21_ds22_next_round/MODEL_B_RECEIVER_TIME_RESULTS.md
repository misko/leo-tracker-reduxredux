# Fixed receiver-time and frequency grids do not repair B053/B059

Both source-frozen v2 slices completed:0539.751s and05912.365s,3 original objective replays each, **6 objectives and zero fits** total. There were54 additional orbital predictions,114 whole likelihood and456 receiver/band group likelihood evaluations. Two workers stayed within independent120/135/140-second bounds. All six source states passed zero objective/NLL/posterior oracles and the original.001Hz/s stable/source-cell derivative gates. Failedv1 and the measured FD postmortem remain immutable.

At **every one of the six prescribed states**, both grids have minimum at zero. All nonzero time points and all nonzero frequency points worsen the original fixed-state NLL. This supplies no positive fixed-grid evidence for a receiver-time parameter or additive-frequency restart.

| Case/state | Time NLL loss at−.0625s | At+.0625s | Frequency loss at−125Hz | At+125Hz |
|---|---:|---:|---:|---:|
| 053 incumbent | 579.512202 | 599.860398 | 340.239884 | 347.704848 |
| 053 fitted A donor | 511.498027 | 499.819014 | 305.060803 | 311.824529 |
| 053 original start3, rejected | 499.241880 | 525.041792 | 303.134184 | 311.455698 |
| 059 incumbent | 1132.127889 | 1108.577567 | 491.350039 | 492.011735 |
| 059 fitted A donor | 1067.359468 | 1049.469543 | 440.307381 | 440.820019 |
| 059 original start3 | 857.447333 | 838.131228 | 391.541214 | 399.931567 |

Time contrast applies+delta to RX0 and−delta to RX1, so relative receiver difference is2delta. The full time grid is±.25/.125/.0625/0 seconds; frequency grid±1000/500/250/125/0Hz uses the same signs. The time bound is an empirical host-bracket-sized sensitivity, not a measured relative-clock uncertainty. Frozen calibration functions and source priors remain at original recorded times. No parameter is fitted and no geography is selected by these profiles.

All42 time-grid points were evaluated without clipping or support exclusion. Minimum effective original20-second timing slack over the grid was.212170s (053 rejected start3), and ephemeris support remained positive. Larger time steps changed visibility in up to18 windows for053 and12 for059; these changes are retained in the profiles. They do not yield a better score. Frequency profiles keep visibility fixed.

The source tangent is not exactly stationary for a newly introduced receiver-time contrast:

| Case/state | Time NLL derivative, objective/s | Frequency contrast derivative, objective/Hz |
|---|---:|---:|
| 053 incumbent | +342.880302 | −2.819e-8 |
| 053 donor | +147.676504 | −2.476e-8 |
| 053 rejected start3 | +344.226117 | +.000131548 |
| 059 incumbent | +84.671941 | −9.638e-8 |
| 059 donor | −277.582944 | −2.819e-8 |
| 059 original start3 | −331.511012 | −6.482e-8 |

Nonzero time derivatives imply smaller local descent directions may exist. The nearest nonzero time-grid point is62.5ms, so a grid minimum at zero **does not exclude millisecond-scale gains, unsampled minima, larger offsets, or gains after calibration/timing reoptimization**. It does not justify calling timestamps correct to a calibrated precision either. Such possibilities must not be confused with a demonstrated repair of the donor's324.117 objective disadvantage to the distant059 mode. The existing receiver-frequency offsets are already fitted: their near-zero contrast derivatives at accepted states provide the expected control.

At1e-5s, stable-cell prediction FD errors over all six states were≤4.0674e-5Hz/s; source-cell one-sided errors≤.000489660Hz/s, below the unchanged.001 gate. Crossed-cell central errors.054339–.134196Hz/s remain explicitly recorded as expected interpolation-cell averages. All five accepted states have unchanged visibility across the FD and their central NLL differences close to the actual central prediction tangent within the specified tolerance. The rejected053/start3 crosses a visibility boundary: its source tangent+344.226 differs from central NLL−1504.199. This is recorded as a nondifferentiable visibility event, not incorrectly certified as NLL derivative equivalence or admitted into selection.

The source metadata supplies one continuous radio stream/shared sample-counter authority and no independent receiver UTC attestation. The earlier native relative-phase experiments changed satellite phase/Earth-orientation handling, not receiver-specific recorded-time offsets. These profiles therefore discriminate an empirical time direction from additive frequency; they diagnose no hardware timing error and change no physical timestamp.

The remaining supported059 evidence is the **receiver-opposed association/residual likelihood ranking** measured in the preceding window audit: RX0 prefers the distant incumbent by1002.111 NLL while RX1 prefers the nearby donor by548.705. That conflict is distributed across many windows, especially RX0 CH6/7, with different low/high preferences at the two nearby full modes. Visibility normalization, absence of the A-derived basin, prior penalty alone, and these fixed time/frequency grids do not explain a repair. The next priority is observational/association continuity and native CFO candidate support, with measured revisit gaps and no fabricated satellite identity or arbitrary truth weighting. No further fit is launched in this report.

Source/protocolfecff5930,8 tests/Ruff passed, including an actual synthetic interpolation-knot regression and rejection of a wrong stable-cell derivative. Runtime `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-receiver-time-audit-v2`; terminal SHA256053`1cab7169edaec52159d9397c8e6d1af1fb82f65bf7878f414c0f4f8db4e10353`,059`2a16bbe6aba66324668cbb7a8d6d40facc41b72205de8b195e9f933ab4bd5ded`. Full profiles retain perreceiver/band NLL and signal/clutter masses, weighted prediction-change RMS, all support margins and derivative receipts. Original selections, histograms and accuracy claims remain unchanged.
