# Clock and track-offset transfer across six simulated sites

The combined smooth-clock and per-track-offset receiver published fixes on **2 of 6** original containing offers and **2 of 6** near-edge containing offers in each calibration arm. The same two sites supplied both sets of fixes. Every frozen model withheld all 12 omitted offers and the time shuffle in both arms. The combined fit improved prediction of held Doppler against most paired controls. On the two originally published locations held in common, its geographic error was lower than the offset-only fit in both arms, mixed against the diagonal fit, and higher than the clock-only fit with `c` fitted.

These are geographically disjoint simulated receivers with authentic orbit and measurement inputs. The closest separation to any of the 24 previously scored simulated sites was 1,176 km. Each of the six sites used a different causal catalogue, with scan dates on November 15 and 17. Workers received the earlier TLE and native GLRT candidate records, selected peaks and constructed anonymous Graph tracks from scratch using the same frozen implementation. The simulator used actual TLE revisions received 2–6 hours later as trajectory proxies. Evaluated over the 72 planted active emitter windows at the known locations, earlier-versus-later orbital predictions had a median Doppler RMS difference of 0 Hz, with a 95th percentile of 5.81 kHz and a maximum of 50.58 kHz. The strong tail is part of this draw. These differences measure divergence between archived fitted orbits. The physical positions of the satellites are unobserved.

The controller chose 144 windows from six measured and authenticated donor captures, retaining 6,544 of the 32,017 candidate visits before applying Graph selection. Median lane span was 38.4 s, median maximum within-lane gap was 2.11 s, and median residual RMS and adjacent-sample correlation were 100 Hz and 0.57. Residuals were centered within each donor window. The controller replayed their temporal structure independently into each simulated lane. It generated the GLRT time, CFO, frame-epoch and sparse false-candidate fields and reused the existing simulated receiver clock and LO drift. This experiment exercised the native factor reader, peak selection, Graph and four position models. Cross-lane hardware disturbances and raw IQ acquisition are outside its scope. [Protocol](PROTOCOL.md) · [Donor receipts](donor-receipt.json) · [Draws](draws.json)

## Position

Cells giving two values follow `c = 0` / fitted `c`. The four publication count columns are out of six per arm. Every publication in a containing tile was within 5 km. The shuffle withheld in all eight model-arm combinations and has no geographic truth. Forced coordinates stayed diagnostic, including for withheld cases.

| Model | Original published | Original median / max error, km by arm | Near inside published | Near inside median / max error, km by arm | Near outside published | Far outside published |
|---|---:|---|---:|---|---:|---:|
| Clock + offsets, OU | 2 / 2 | 1.07 / 1.80 · 1.13 / 1.79 | 2 / 2 | 1.07 / 1.80 · 1.13 / 1.79 | 0 / 0 | 0 / 0 |
| Clock + offsets, diagonal | 3 / 3 | 1.80 / 3.00 · 1.74 / 2.71 | 2 / 2 | 1.52 / 1.80 · 1.46 / 1.74 | 0 / 0 | 0 / 0 |
| Clock only, OU | 3 / 3 | 1.24 / 3.27 · 1.21 / 2.35 | 1 / 1 | 0.64 / 0.64 · 0.29 / 0.29 | 0 / 0 | 0 / 0 |
| Offsets only, OU | 2 / 2 | 1.35 / 2.33 · 1.43 / 2.32 | 1 / 1 | 0.36 / 0.36 · 0.54 / 0.54 | 0 / 0 | 0 / 0 |

All 24 non-shuffled offers had diagnostic coordinates for all four models in both arms. For the combined OU model, forced median errors for original, near inside, near outside and far outside tiles were 2.39, 2.39, 2.96 and 51.20 km at `c = 0`, and 2.11, 2.11, 2.78 and 51.10 km with fitted `c`. In the original stratum the combined OU withheld two sites on held-track support and two on position geometry. The six sites and fixed edge offsets provide a small matched test of wrong-tile rejection and fix coverage. [Complete position and RF distributions](scores.json) · [Position figures, zero calibration](figures/c0/transfer.pdf) · [Position figures, fitted calibration](figures/fitted_c/transfer.pdf)

## RF prediction on the same support

The original six offers retained 81–120 held suffix points each. All four models and both calibration arms matched the training, held-prefix and final owner and alias receipts. The worker used the same position search and gate, with per-model geometry and boundary decisions after the conditional fit. Lower conditional deviance and RMS measure held CFO prediction.

| Model | Median fitted RF RMS, Hz | Median held RF RMS, Hz | Median held deviance per point |
|---|---:|---:|---:|
| Clock + offsets, OU | 94 / 94 | 785 / 768 | 14.36 / 14.29 |
| Clock + offsets, diagonal | 83 / 83 | 850 / 844 | 34.00 / 33.71 |
| Clock only, OU | 111 / 104 | 1,925 / 1,775 | 26.63 / 28.36 |
| Offsets only, OU | 111 / 110 | 804 / 793 | 14.44 / 14.39 |

The combined OU held RMS was lower on 5/6 original offers versus diagonal, 6/6 versus clock only and 4/6 versus offsets only in **each** calibration arm. With fitted `c`, the two combined-versus-clock-only published position pairs became 0.19 and 0.58 km worse despite the held RF improvements. This separation matters when interpreting the four model fits. [Position-level data](scores.json) · [Raw worker results](predictions.jsonl.gz)

## Reproduction

Defined protocol, numerical sources, donor receipts and catalogue inventory were hashed before draw or inference. The seed and generated coordinates were held separately by the controller while the worker received the three bound inputs consisting of native archive, causal TLE and track configuration. The prediction lock was written before the scorer opened the targets. All 25 requests finished under the 512 MiB address-space limit. Median/max wall time per request for all four models was 2.53/3.70 s, median/max peak RSS was 138.71/138.93 MiB, and the two-worker batch took 32.19 s.

The frozen [protocol](PROTOCOL.md), [source lock](source-lock.json), [input lock](input-lock.json), [prediction lock](prediction-lock.json), [catalogue inventory](catalogue-inventory.json), [public requests](requests.json), [released seed](seed.hex) and [figure seal](figure-lock.json) provide independent checks. `clock_transfer_inputs.generate` regenerates the precise archived bytes with the released seed, frozen inventory, measured donor pool and archive Graph configuration. `clock_transfer` provides `prepare`, `predict` and `score`. `clock_transfer_figures` regenerates the four position cards and both calibration books from the sealed predictions and targets.

Replaying generation reproduced all 15 public and three private file digests. The shared physical-study results module gained roof-only chart code after the first score. Its exact pre-change source is archived here. A second scorer run using that source reproduced `scores.json` byte for byte, and both module versions produced identical normalized records for all four methods. [Frozen scorer dependency](frozen-clock-offset-results.py.txt)
