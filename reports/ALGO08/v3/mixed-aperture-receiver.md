# Mixed 20 ms and 12 ms stereo receiver

The scheduled 12 ms signed primary took **1.073 ms CPU per paid antenna** on the dense panel and **1.735 ms** on the weak panel. Each stereo visit ran both antenna searches independently, costing 2.147 ms and 3.470 ms respectively. The dense panel spent 37.4% of the installed native search CPU on the proposed call schedule. A separate full-aperture availability proxy failed the prespecified geographic gate, so there was no raw localization run of the short receiver.

## Frozen receiver and evidence

The [protocol](mixed-aperture-receiver-protocol.md) was committed at `cf633c581` before measurement. Each chronological stream with the same channel, actual RF and pilot edge pays for installed 20 ms two-scan stereo at index zero modulo eight, shortened 12 ms primary-only stereo at indexes one, three, five and seven, and no native search at the other three indexes. The rule applies to the final incomplete group. A paid antenna uses its own signed I/Q and the original fractional gate. The callback keeps the largest verified margin, with lower native rank breaking an exact tie. Empty visits keep both original probe rows and counters.

The earlier qualified short two-scan binary was first relinked byte for byte. This study reused its shortened timing, refinement, cancellation and verifier objects with the stock signed wrapper and a new primary-only entry. The shorter entry's disassembly calls the locally bound timing scout, verifier load and verifier. It has no dependency on the installed receiver DSO. The unchanged two-scan entry remained available in both shortened libraries.

| Authenticated inputs | Antenna lanes | Installed full factors | Original short full factors | Short rank-zero factors | Short rank-one-only lanes |
| --- | ---: | ---: | ---: | ---: | ---: |
| Weak archived, 18 stereo | 36 | 58 | 55 | 34 | 0 |
| Dense physical, first 48 stereo | 96 | 80 | 65 | 45 | 0 |

The relinked short two-scan entry reproduced the original short factors byte for byte on all 132 lanes. The new primary matched the presence and bytes of short full rank zero on all those lanes, including empty outputs. Replacing both antennas' samples from 120,000 onward with saturated values changed no primary. The mixed callback reproduced the expected selection and original antenna, visit and sample counters on every timed repeat.

The full native entry can emit rank one alone. Initial scout confirmation starts the residual search, and the fractional verifier can still reject rank zero independently. The primary-only entry returns an empty lane in that case. The full verifier also has a two-factor margin-order retry that the one-candidate path cannot trigger. The sample establishes observed rank-zero parity and leaves these differences in the full-path contract intact.

## Single-core CPU price

Five resident repeats interleaved the four paths on the same authenticated stereo buffers and reversed the order between successive visits and repeats. The compact receipt includes all repeats, native calls, factor selections and input hashes. Native clock boundaries enclose the receiver call itself. The mixed callback clock also includes Python validation, scheduling, selection and construction of both probe rows.

| Panel | Full / short / quiet stereo visits | Installed native, all lanes (ms) | Short two-scan native, all lanes (ms) | Short primary native, all lanes (ms) | Scheduled mixed callback (ms) |
| --- | ---: | ---: | ---: | ---: | ---: |
| Weak | 17 / 1 / 0 | 138.402 | 84.664 | 45.697 | 135.843 |
| Dense | 8 / 24 / 16 | 265.126 | 155.137 | 102.949 | 99.738 |

| Panel | Full native per paid lane / stereo (ms) | Short native per paid lane / stereo (ms) | Scheduled native share of installed | Steady whole-group native share |
| --- | ---: | ---: | ---: | ---: |
| Weak | 3.854 / 7.707 | 1.735 / 3.470 | 96.1% | 29.0% |
| Dense | 2.944 / 5.887 | 1.073 / 2.147 | 37.4% | 31.9% |

Per-paid-lane numbers divide each repeat's CPU by its mode-specific lane count and take the median. Each paid stereo visit has two lane calls. The weak short price represents a single scheduled stereo visit, with 1.269 ms per lane across all 36 standalone short-primary lanes as broader context. The dense standalone short-primary price was 1.072 ms per lane across all 96 lanes. The steady column weights the all-lane stock price by one eighth and the all-lane short-primary price by one half. The observed columns reflect the incomplete streams, including the weak panel's 17 full anchors. The weak callback selected 34 full and two short factors, and the dense callback selected nine full and 19 short factors.

Context creation was measured separately using both actual detector callbacks and pinned pilots, with no waveforms. The median repeated setup cost per edge was 1.088 ms installed and 2.564 ms mixed on the lower edge, and 1.057 ms installed and 2.417 ms mixed on the upper edge. First setup in the same already-running process took 2.150 / 2.905 ms on the lower edge and 1.367 / 2.510 ms on the upper edge, in installed / mixed order. Repeated teardown cost 0.041–0.042 ms installed and 0.088–0.095 ms mixed. These scope-entry clocks include pilot loading, artifact pin checks where used, library binding, workspace creation and FFT plan setup. Python process startup and authenticated waveform I/O are outside the clocks.

The native allocator accounts for 10,880,424 bytes per installed edge context and 9,852,904 bytes per shortened edge context. The mixed callback holds both, for 20,733,328 accounted bytes per active edge, excluding opaque FFT plan and interpreter/library allocations. The research ingress still authenticates the original 20 ms stereo buffer on every visit, including skipped visits. This experiment measured native receiver cost and context setup.

## Reuse

Instantiate `MixedApertureDetector(short_binary, short_sha256)` once per recording and pass its bound `detector` as `detector_override` in the research runner. Its `receipt()` gives stereo visits, native calls, selected factors, clocks and last sample counters. The [build and benchmark](mixed_aperture_trial.py) records the archived recipe, object checksums and disassembly. The [receipt](measurements/mixed-aperture-receiver.json) contains the physical and no-waveform measurements. The short binary SHA-256 is `06570a53032c770d99cc9678b8660e1bb502b71f30fc47c8b1a4a8e31bc19ba9` and the [callback](mixed_aperture_receiver.py) SHA-256 is `a2136b0a228413cfd7604176830074e78012d1bca3dc505771c396e14c6ece0e`.
