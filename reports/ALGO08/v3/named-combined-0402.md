# Combined named solver and rendering on DS30-0402

Starting from the original named 20 ms detections, graph and forecast reuse plus direct rendering reduced a fresh fitted-first process from **55.752 to 53.403 s**. Both kept the original 4,821 ordered observations and satellite assignments per calibration arm, both positions and RF residuals, and the complete scientific grid and path. The original two-pixel orbit image comparison flagged two gray layers. Use the ordinary renderer when that visual tolerance is required. [Frozen pair](named-combined-0402-protocol.md) · [Complete numerical and visual receipt](measurements/named-combined-0402.json.gz)

| Saved process | Elapsed s | CPU s | Graph CPU s | Numerical CPU s including graph | Eight figures CPU s |
|---|---:|---:|---:|---:|---:|
| Prepared gates, fitted calibration checked first | 55.752 | 55.725 | 1.179 | 51.581 | 2.684 |
| Same gates with graph and phase reuse and direct rendering | 53.403 | 53.386 | 0.613 | 50.474 | 1.431 |

The combined child ran first. Each child ran in a fresh process on Gauss CPU 2, nice 15 and best-effort I/O priority 7, under the shared lock. Both used the same sealed detector, causal archive, geographic offer and warmed font cache. Process input blocks were 16 and zero for the combined and ordinary children respectively. They both completed the original five fitted-calibration constrained rounds in 58 visits and rejected the same proposal. All 80,988 ordered graph edges were produced, 1,548 of 2,322 polynomial calls reused a fit and one causal forecast used 6,006 cached Julian splits. This measures the joint saving. Subtracting individual kernel clocks from other recordings would mix workloads. [Earlier stock 73.351 s and gate comparisons](paired-veto-0402.md)

| Calibration | Same horizontal error | Same RF RMS | Ordered owners retained |
|---|---:|---:|---:|
| Fixed zero | 863.651 m | 100.672203 Hz | 4,821 / 4,821 |
| Fitted | 860.302 m | 100.576460 Hz | 4,821 / 4,821 |

Both standard publications contained eight decodable, content-addressed PNGs with the reference dimensions. The sidecars bound their respective position PNGs and agreed on the full 179-point grid and path after removing only elapsed time and the image reference. All four direct orbit sheets retained their 24 satellite legend entries, with at least 26 pixels of separation. In all 32 registered orbit panels, colored pixels had at least **99.893%** support in both directions within two pixels. For the gray marks on RX1 CH2, **96.00%** of Cairo pixels matched stock on the all-observations sheet and **95.76%** on the unassociated-only sheet. Both fall below the pre-existing **98%** cutoff. Stock-to-Cairo coverage was **99.72% and 99.75%** on these same two layers. The scorer first stopped on this failure, then recorded all 64 layer comparisons on the stored files without rerunning either solve. The pass flag in the receipt is false. [Weak visual comparison](named-weak-exact.md) · [Reproduction and scoring](named_combined_0402.py)

Use the generic named research command with `--constrained fitted-first --optimized-publication` to exercise this combination. The ordinary named renderer remains the default. From the repository’s v3 report directory the saved replay uses `named_combined_0402.py launch NEW_TMPFS_ROOT` followed by `named_combined_0402.py verify NEW_TMPFS_ROOT --receipt NEW_RECEIPT`. The recorded source for both timed CLI calls was commit `376ae21db`. The normalized post-exit receipt SHA-256 is `8369dc43b26c6b71ffe3858c4e34794c00267d196710c278fd7d0dc48ac80852` over the uncompressed file.

An independent read of the sealed files traced 11 of 15 and 12 of 18 unmatched gray pixels to panel cropping or antialiasing. The remaining groups aligned in time with actual unassociated measurements. Their frequency coordinates could not be independently recovered from these files. The original visual gate remains open. [Pixel and observation audit](orbit-registration-0402.md)
