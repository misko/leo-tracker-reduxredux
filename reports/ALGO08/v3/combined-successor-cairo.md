# Six Cairo sheets on the guarded original-file successor

The original DS30-0016 worker with six Cairo sheets exited in **7.447 s wall / 7.408 s CPU**, versus the previously measured guarded worker's **7.862 / 7.860 s** and installed ALGO08v3's **10.745 / 10.742 s**. The full worker saved **0.415 s wall** and reached **1.443×** against installed v3 on this positive case. Both calibration results and the complete scientific publication matched the guarded worker. All eight PNGs matched independently qualified Cairo output byte for byte. [Frozen protocol](combined-successor-cairo-protocol.md) · [Complete receipt](measurements/combined-successor-cairo.json.gz)

| Measured scope | Guarded with four ordinary orbit sheets wall / CPU | Guarded with six Cairo sheets wall / CPU |
|---|---:|---:|
| Authenticated original acquisition | 3.015 / 3.014 s | 3.006 / 3.004 s |
| Numerical solve including the standard grid | 2.179 / 2.179 s | 2.145 / 2.120 s |
| Eight-image render and encode | 0.895 / 0.894 s | 0.535 / 0.526 s |
| Decision and standard publication | 4.220 / 4.218 s | 3.820 / 3.784 s |
| Worker start through verification and exit | **7.862 / 7.860 s** | **7.447 / 7.408 s** |

The stronger attribution is the **0.360 s wall / 0.368 s CPU** difference inside rendering. The four ordinary orbit sheets previously took **0.684 s CPU**. Four native orbit sheets took **0.280 s CPU**, including **0.134 s** for the lossless encoder. Both full renderers already use two Cairo residual sheets and explicit position/track layout. The older **0.977 s** saved-publication result includes those existing portions and overlaps this change. The non-render clocks here come from two independently launched workers. The Cairo child charged 5,944 process-wide input blocks and 34 major faults, versus 104 and zero in the guarded worker. Original and causal inputs were already resident. [Current control](combined-successor-original.md) · [Earlier six-sheet measurement](history-risk-cairo-physical.md)

## Complete physical and visual evidence

The reader still authenticated 991,734,597 compressed bytes and all 13 complete decoded members of the read-only original. It retained the same 808 issued and 713 admitted visits, signed native detector packet, causal cutoff, portable orbit index and original 25 km offer. All 242,675 input pages were resident before and after. The ordinary one-member lookahead again submitted and hit 11 buffers covering 834,805,982 bytes, with zero fallback. The same guarded solver used its ordinary weak-case rank fallback, one live orbit scope without additional knots, and the full native grid. The latter executed 708 projections, 356 selections and 356 design fills with zero reported native fallback.

Both arms kept their positions, geographic decision, all 115 ordered observation/satellite/role rows, exact scientific grid and path hashes, and the published position-image bindings. The offer contained both fixes, so the geographic guard used no exterior scoring.

| Calibration | Horizontal error | Conditional RF RMS | All-owned RF RMS |
|---|---:|---:|---:|
| Fixed zero | 490.071 m | 134.021487 Hz | 135.546968 Hz |
| Fitted | 980.010 m | 133.739967 Hz | 136.859291 Hz |

The actual renderer recorded four Cairo orbit sheets, two Cairo residual sheets and one explicit layout each for the position and track figures. All eight files were verified and reused without fallback. The recording title was `fast8-auto-20261113-112146-b04f5461-1-lower`. Independent decoding verified the same image dimensions, mode, DPI and PNG metadata. Each orbit sheet was **2400 × 3022**. Their pixel changes from the guarded Agg render were **12.40–12.67%**, with at least **98.785% gray** and **99.991% color** support in every direction under the unchanged registered two-pixel test. The other four PNGs are byte-identical to the guarded control. The exact match to the separately audited Cairo PNGs also preserves its verified axis labels, title, bounds, ticks, legend and original plotted series. The output grew from 2,743,359 to 2,913,411 encoded bytes. This physical comparison is specific to DS30-0016. [Validated artist and media evidence](history-risk-cairo-physical.md) · [Separate long-scene gray-layer results](orbit-gray-layout.md)

## Two-recording timing screen

The frozen original DS30-0107 worker withholds after verifying the full receiver input and its empty-curvature proof. Its sealed route has no solver source, scientific imports or active renderer, and the shared bootstrap only invokes the active renderer through the positive publisher. The Cairo entry still changes lightweight startup flag checking and wrapper installation. The following model uses the archived **0.601460 wall / 0.576044 CPU s** as its timing input, including startup.

| Modeled cohort scope | Installed | Cairo candidate with archived 0107 | Summed speedup | Paired-median speedup |
|---|---:|---:|---:|---:|
| Wall | 12.241696 s | **8.048314 s** | **1.521×** | **1.827×** |
| CPU | 12.238062 s | **7.984428 s** | **1.533×** | **1.861×** |

The modeled median clears 1.6×. The summed wall time misses 1.6× by **0.397 s** and 2× by **1.927 s**. Both modeled 2× gates fail. The predeclared screen kept 0107 out of this launch. Even removing the entire earlier **0.685 s wall** orbit interval with every other time fixed would have left the previous guarded pair at about **7.779 s**, above the **7.651 s** 1.6× limit.

## Reproduction and accounting

The supported `--cairo-six-sheets` choice now passes the existing original-file title-checking handoff when the dedicated research entry explicitly enables it. The ordinary call keeps its existing renderer guard, parser, acquisition and publication. Three source-pinned renderer adapters in this checkout add the residual-only branch for ordinary use. The six-sheet drawing primitives match the previous independent qualification and every new official Cairo image reproduced that qualification's hash. No trial scene export entered the timed child.

Use the same private read-only mount and installed interpreter as the guarded original-file trial. Run `combined_successor_cairo_trial.py launch FRESH_TMPFS_ROOT DS30-0016` under the single Gauss CPU 2 lock, nice 15, I/O priority 7 and one numerical thread. Run the read-only `score` action using the research storage-port sources. Recorded controller admission was **1.079 wall s** after the static reference checks, and the waveform-denied scanner, lookahead, solver and Cairo-library startup probe cost **1.285 wall s** separately. The installed child repaid its normal in-process setup. It was the sole original acquisition and used no backing waveform reads, conditioning or new RF.

The measured child used `ec5bcc7aa`. The first offline score compared live image-size tuples directly with archived JSON lists. The corrected scorer compares the integer dimensions and reused the same sealed outputs. The first score is retained in the receipt. The prediction seal was `c01543b56510d1435e25c7fa1ac403710e02af0264a1d76021866b10942010f5`. The uncompressed combined receipt SHA-256 is `ab222fbb9fec094e54e7c74f15b61a60c727a69aa741f2adca2f7668b7af3ec1`. Thirty-four component and adjacent tests passed. [Entry](combined_successor_cairo_entry.py) · [Trial and gates](combined_successor_cairo_trial.py) · [Tests](../../../tests/pipeline_eval/test_combined_successor_cairo.py)
