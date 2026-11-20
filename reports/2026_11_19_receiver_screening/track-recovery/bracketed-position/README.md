# Bracketed weak peaks through the installed position receiver

Seven existing weak factors were promoted across three recordings. The installed solver used seven more observations and returned the same number of tracks. The largest change in geographic error was a **6.60 m improvement** on DS29-0082 with `c = 0`. Both methods published all four recordings and met the same 5% and 10% criteria against original no-repair v5. [All recordings, c = 0](charts/c0/bracketed-position-all.png) · [All recordings, fitted c](charts/fitted_c/bracketed-position-all.png) · [Held pair, c = 0](charts/c0/bracketed-position-held.png) · [Held pair, fitted c](charts/fitted_c/bracketed-position-held.png)

| Recording | Role | Promotions | Wide control error, zero / fitted | Bracketed error, zero / fitted | Error change, zero / fitted |
| --- | --- | ---: | ---: | ---: | ---: |
| DS26-0036 | Diagnostic | 0 | 1.003 / 0.935 km | 1.003 / 0.935 km | 0 / 0 m |
| DS26-0162 | Held | 1 | 0.682 / 0.670 km | 0.682 / 0.670 km | +0.0017 / +0.0019 m |
| DS29-0082 | Diagnostic | 2 | 2.489 / 2.346 km | 2.483 / 2.345 km | −6.60 / −0.80 m |
| DS29-0519 | Held | 4 | 0.334 / 0.324 km | 0.330 / 0.321 km | −3.94 / −2.66 m |

Positions on the edited recordings moved by 0.016–14.91 m. One of four recordings was within 5% and 10% of original v5 with `c = 0`. Two of four were within both thresholds with fitted `c`. The corresponding counts on the held pair were zero of two and one of two. Both methods had these same counts. All recordings come from one roof. [Per-arm scores, support and all four original v5 references](scores.csv)

Conditional Doppler RMS moved by at most 0.085 Hz between methods. The frequency objective rose when the support gained observations, and it measures a different set of residuals after the edits. Within the bracketed method, fitting `c` reduced geographic error on all four. It lowered conditional RMS on DS29-0082 and raised it on the other three. [Per-arm geographic and Doppler measurements](scores.csv)

The solver received the same exact installed `phase-release` package, causal TLEs, original project TrackConfig, tile and screen in both methods. Each edit changed only one gate flag in a previously all-failing probe. Reversing the edits recovered the original bytes. The source retains original detector and capture lineage. The derived files have their own checksums and an authenticated list of the actual changed rows in the candidate lock. The DS26-0036 candidate had zero changes, so its result is labeled exact archived reuse. All four fresh stock fits independently reproduced both archived positions, Doppler fit and all numerical metrics other than timings. [Input lock](source-lock.json) · [Derived-input lock](candidate-lock.json) · [Prediction seal](prediction-lock.json)

| Recording | Fresh stock position wall | Edited position wall | Edited position CPU | Edited charged peak |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 71.63 s | Exact reuse | | |
| DS26-0162 | 100.73 s | 118.38 s | 114.16 s | 473.93 MiB |
| DS29-0082 | 39.45 s | 41.42 s | 38.24 s | 361.18 MiB |
| DS29-0519 | 70.78 s | 81.98 s | 81.46 s | 437.97 MiB |

Every measured fit finished within 210 s and 512 MiB with zero swap. These are single factor-to-position services on the same CPU per recording. The selector itself used 0.030–0.062 CPU-seconds per complete native input in the earlier selection measurement. Parsing, encoding the changed JSON, and checking the reverse edit used 0.332–0.498 CPU-seconds for each edited input. These measurements cover stored factors. [Filter timing and support](selection.csv) · [Service resources](resources.json) · [Prospective protocol](PROTOCOL.md)
