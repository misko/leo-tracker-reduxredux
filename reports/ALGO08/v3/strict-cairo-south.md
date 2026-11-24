# South simulation with strict packed 20/8 ms, history-risk and Cairo

The frozen physical finalist reproduced the earlier South 20/8 ms positions, RF residuals and ordered owners using the same authenticated detector packet. It took **9.643 s** with a prepared archive, including readiness checks, versus **15.699 s** for the reusable fresh installed ALGO08v3 control. Charging conversion and full readback raised first use to **19.087 s**. This is one replay of a geographically different simulation and is separate from the physical cohort.

| Boundary | Wall, s | CPU, s | Speedup vs fresh named v3 |
| --- | ---: | ---: | ---: |
| Installed named v3, reused fresh original-input clock | 15.699 | 15.694 | 1.000× |
| Strict finalist through complete verified exit | 9.620 | 9.616 | 1.632× |
| Strict replay plus candidate-ready checks | 9.643 | 9.640 | 1.628× |
| Prepared replay with common custody checks also charged | 9.702 | 9.689 | 1.618× |
| First use with prior measured conversion and full readback | 19.087 | 19.013 | 0.822× |
| First use with common custody checks also charged | 19.146 | 19.062 | 0.820× |

The older independently verified installed clock was **14.370 s**, which gives **1.490×** prepared. Installed positions, official owner maps, numerical sidecars and all eight PNGs agreed between the two named controls. The previous South strict adaptive child took **9.507 s** using a portable index, different inference and a 79-point adaptive grid. This replay deliberately used the physical finalist's cold orbit index, history-risk inference and full grid. The history-risk gate selected its lean branch after healthy earlier-orbit samples. The held receiver selector picked history on both radios. Authenticated acquisition took 3.980 s and decision through publication took 5.041 s. Inside the latter, the exact solve took 3.256 s and rendering took 0.684 s. Regional preparation accounted for 1.736 s, with 86 verified reads of 23 bodies totaling 153,735,589 bytes.

| Calibration | Named horizontal error | Strict horizontal error | Named conditional RF RMS | Strict conditional RF RMS |
| --- | ---: | ---: | ---: | ---: |
| Fixed `c = 0` | 816.789 m | 325.347 m | 6.502 Hz | 10.213 Hz |
| Fitted `c` | 1101.409 m | 362.672 m | 6.392 Hz | 10.108 Hz |

The held reference lies 100 m inside the offered 25 km square. Both runs completed. Each used the same signed 1,200 visits and 2,400 ordered acquisition opportunities, the same offer and the same causal cutoff. Each detector emitted 456 factors. The strict route retained all 266 named owners per arm with the same assignments and roles and added 38. Fitting `c` reduced conditional RF RMS in both runs and increased the location error in both runs. Both publications retained the full 137-point matched-calibration grid and complete fit path, with position PNG digests verified by both sidecars. All eight candidate PNGs decoded independently at the named dimensions. Their raster digests differed from named v3. The live counters recorded four Cairo orbit sheets, two Cairo residual sheets and one position and track sheet each, with eight verified PNG reads and zero fallback reads.

The original recording and causal catalogue were already in tmpfs. The separate prepared derivative remained fully resident. The strict run authenticated all 2,400 encoded blocks in 19 signed members, totaling 1,580,884,800 bytes. It decoded and verified 913,920,000 bytes, making 304 full-aperture and 2,096 short-aperture lane calls, with zero original-window fallbacks. The original compressed payload was 1,574,298,988 bytes. The entire derivative occupied 1,582,266,491 bytes with sidecars. Its earlier measured construction and independent full decoded readback took 9.444 wall / 9.373 CPU s. Trusted ready checks took 0.023 s on this replay and common setup took another 0.059 s. The one-core replay exited zero with zero major faults and 24 process input blocks. No waveform was read from the backing recording store.

The previous near-omitted South controls remain a counterexample. With the reference 100 m outside the supplied offer, the saved exact named and installed named routes both falsely fixed in both arms. The exact 20/8 ms control used this replay's identical signed detector packet and reported errors of 325.334 and 362.940 m. Its final exterior gate did not engage because both optimized positions were inside the offered square. The new strict replay covered the containing offer only. [South near-omitted control](exact-named-south-omitted.md)

Run the [frozen one-child driver](strict_cairo_south.py) on the approved tmpfs roots under the shared Gauss lock with CPU 2, nice 15, I/O priority 7, and one numerical thread. The [offline verifier](strict_cairo_south_score.py) reopens the two complete publications and scores the sealed outputs with the held simulation reference. The launch was frozen at `8267e3f2b`, with the same runtime sources and native libraries as the physical result `1892fb9bd`. The [machine receipt](measurements/strict-cairo-south.json.gz) has uncompressed SHA-256 `e0ac0972934671d6536daed5ba64de4cf21f2d695bc51893c0720a08a7fef903`. The immutable prediction seal is `ecb437f6bbdfc26efff9fd3a9453e4f946ab581228ed60aff73d9baf2d680540`.

[Frozen protocol](strict-cairo-south-protocol.md) · [Earlier South strict adaptive result](south-strict-transfer.md) · [Separate physical cohort](history-risk-physical-cohort.md)
