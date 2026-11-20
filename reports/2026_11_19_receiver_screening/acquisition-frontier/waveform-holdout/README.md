# A second blind Qin waveform site under structured interference

At one new simulated site, the installed phase release produced **0.650 km zero-`c` and 1.093 km fitted-`c` fixes** from the containing 25 km region. Original v5 reached 0.642 km and 1.086 km on the same detected factors. The prospectively run 20 m profile retained both containing fixes and suppressed all four publications from the near and far omitted offers. The omitted fits reached a tile face under all three solvers. This qualifies one simulated site and the supplied region challenges.

## Matched position and frequency results

| Offered region | Receiver | Zero-`c` error | Fitted-`c` error | Conditional RF RMS, zero / fitted | Direct wall |
| --- | --- | ---: | ---: | ---: | ---: |
| Containing | Phase release | 0.650 km | 1.093 km | 17.213 / 17.199 Hz | 20.94 s |
| Containing | 20 m interior | 0.650 km | 1.093 km | 17.213 / 17.199 Hz | 20.32 s |
| Containing | Original v5 | 0.642 km | 1.086 km | 17.213 / 17.199 Hz | 77.44 s |
| Near omitted | Phase release | 1.728 km, false fix | 1.668 km, false fix | 17.317 / 17.345 Hz | 20.15 s |
| Near omitted | 20 m interior | Withheld, 1.728 km forced | Withheld, 1.668 km forced | 17.317 / 17.345 Hz | 20.61 s |
| Near omitted | Original v5 | 1.718 km, false fix | 1.658 km, false fix | 17.319 / 17.348 Hz | 153.97 s |
| Far omitted | Phase release | 44.255 km, false fix | 44.255 km, false fix | 44.078 / 43.773 Hz | 21.85 s |
| Far omitted | 20 m interior | Withheld, 44.255 km forced | Withheld, 44.255 km forced | 44.078 / 43.773 Hz | 22.70 s |
| Far omitted | Original v5 | 44.255 km, false fix | 44.255 km, false fix | 40.794 / 40.329 Hz | 133.38 s |

Each profile has two legitimate publications within 5 km out of two containing arms. Phase release and original v5 issued all four possible false publications. The interior profile issued zero false publications and reproduced phase-release coordinates, conditional RF and other scientific metrics exactly across all three independent executions. Both compact profiles prepared 594 observations and 26 tracks per offer. Their cavity stage ran without an eligible cavity choice in this scene. Fitting `c` on the correct offer lowered compact conditional RF RMS by 0.014 Hz and increased geographic error by 0.442 km. The exact containing fits remained 4.997 km and 4.743 km from the nearest face. Truth sat 1.5 km and 42.5 km beyond the nearest faces of the excluded regions. [Both-arm scores and parity](scores.json) · [Score lock](score-lock.json) · [Independent original prediction lock](../waveform-v5/holdout/prediction-lock.json)

| Standard position charts | Zero `c` | Fitted `c` |
| --- | --- | --- |
| Phase release and matched original v5 | [Chart](charts/c0/waveform-holdout-phase-release.png) | [Chart](charts/fitted_c/waveform-holdout-phase-release.png) |
| Prospective interior profile and matched phase release | [Chart](charts/c0/waveform-holdout-interior.png) | [Chart](charts/fitted_c/waveform-holdout-interior.png) |

## Signal and receiver boundary

One 300 s simulated session comprises 150 complete eight-channel sweeps. Every scheduled visit produced a 20 ms dual-CI16 array at 10 MS/s, for 1,200 visits, 2,400 receiver probes and 1.92 GB of generated samples. The actual compiled stock wide GLRT consumed each visit. Its exported native probe counts and candidate scores are archived, including rejected proposals and empty probes. The underlying IQ is reproducible from the seed and source while the per-visit SHA-256 is retained for verification. [Waveform design](PROTOCOL.md) · [Visit ledger](visit-ledger.jsonl.gz) · [Complete detected native document](native.json.gz)

This scene used a location 15,746 km from the preceding waveform site and at least 4,776 km from eleven prior simulation sites audited across four panels. The opaque numerical input comprised the detected factors, TrackConfig, received-by-cutoff archive, receiver clock, and offered region. The simulator clock opened at 2026-11-14 07:39:20 UTC, after the final 05:37 UTC causal collection. The generator used the independently held 11:37 UTC revision. The revised elements changed projected Doppler for all twelve emitters, with 1.720 kHz median absolute mismatch and 3.268 kHz at the 95th percentile. [Unblinded site, seed and generator authority](truth-after-lock.json.gz) · [Site separation and earlier comparison](cross-site.json) · [Blinding commitments](input-lock.json) · [Model, stock detector and both installed executables](source-lock.json) · [Causal archive](causal-authority.json) · [Public requests](requests.json)

| Detector evidence | Earlier Qin waveform | Stressed holdout |
| --- | ---: | ---: |
| Planted probes with a matching gated candidate | 527 / 528 | 473 / 480 |
| Planted probes with a matching observation winner | 494 / 528 | 435 / 480 |
| Wrong winner on an illuminated probe | 34 / 528 | 41 / 480 |
| Illuminated probes with no gate winner | 0 / 528 | 4 / 480 |
| Dark probes with a gate winner | 196 / 1,872 | 118 / 1,920 |
| Median absolute causal-to-truth projected Doppler mismatch | 177.9 Hz | 1,719.7 Hz |

In the holdout, 48 receiver probes occurred in explicit foreground gaps, 122 had a faded pilot, and 1,218 had the QPSK interferer. All four illuminated gate misses fell in faded probes. Dark gate winners occurred in 26/1,010 OFDM-busy probes and 92/910 probes without OFDM. Among matching winners, median wrapped CFO error was 15.75 Hz and median epoch error 0.941 ADC samples. The two sites also differ in geometry and emitters, so this comparison is descriptive. [Per-visit planted audit](planted-hit-ledger.jsonl.gz) · [Earlier waveform report](../../track-recovery/waveform-site/README.md)

The detector replay and native packing took 97.87 s wall across two CPU lanes under shared-host load. Waveform generation used 66.53 CPU s and actual GLRT calls 27.68 CPU s, with a 23.19 ms median and 30.43 ms p95 per dual visit. The installed position jobs each used 19.52–21.95 CPU s and 245.8–254.6 MiB process peak RSS under a verified 512 MiB cgroup ceiling and zero swap. The original-v5 3 GiB, zero-swap reference used 73.07–146.55 CPU s and 1.02–1.03 GiB cgroup charged peak. Process RSS and charged cgroup peak record different memory boundaries. Generator/detector and post-GLRT wall times were measured separately. [Detector lock](detector-lock.json) · [Installed prediction seal](prediction-lock.json) · [Installed runtime receipts](resource-receipts.json) · [Original reference protocol and runtime allowance](../waveform-v5/HOLDOUT.md)

## Reproduce

Run `python -m tools.pipeline_eval.qualification.waveform_holdout_trial` with `prepare`, `detect` and `position` using a fresh ext4 work directory and an unused evidence directory containing `PROTOCOL.md`. The program checks the installed phase-release and interior profiles and the compiled stock GLRT against their as-run receipts. With the seed disclosed after terminal prediction, `prepare --seed-hex` regenerates the same private truth and samples. The independent reference handles original-v5 invocation and publishes its own checksums. `python -m tools.pipeline_eval.qualification.waveform_holdout_results` requires the terminal reference prediction lock covering the same three opaque requests before reading the custodian data. The accepted input hashes cover the native document, causal catalogue and exact tile request in all three methods.
