# Original signed South transfer of the combined raw receiver and solver

One complete South containing-offer replay finished in **10.685 s elapsed / 10.681 CPU s**. It verified the original signed input, both calibration fits, a complete 144-point matched grid, the position path and all eight PNGs. The portable index and catalogue block rank both activated. The result differs scientifically from the earlier all-paid South publication. The raw receiver already differed before Graph fitting, so this replay cannot isolate the solver changes. [Frozen protocol](combined-raw-south-protocol.md) · [Verified receipt](measurements/combined-raw-south.json.gz)

| Boundary in seconds | Earlier named-v3 publication | Earlier South all-paid receiver | Combined replay |
|---|---:|---:|---:|
| Process elapsed | 14.370 | 11.614 | 10.685 |
| Process CPU | 14.179 | 11.612 | 10.681 |
| Authenticated acquisition, elapsed | — | 5.693 | 5.136 |
| Decision and publication, elapsed | — | 5.378 | 4.968 |

The transfer used the sealed North command, changing only the original South recording, its containing offer and the output path. All 384,361 payload pages and 188 protocol index pages in the 19 signed members were resident before and after. The child reported zero input blocks and major faults. One low-priority numerical thread used the shared Gauss CPU 2 lock. The stopwatch includes original I/Q acquisition and both accelerators. Earlier named and all-paid clocks came from separate historical launches. The 0.929 s elapsed difference to the earlier all-paid run includes 0.557 s less paid acquisition. [Earlier South publication and omitted-offer caveat](continued-cfo-south.md)

The portable producer predates the South cutoff by **81,936.940 s**. It supplied metadata for **11 of 23** original verified source bodies and **123,141** record occurrences, with zero invalid bodies or compatibility/load fallbacks. The other 12 source bodies took the cold indexing route. Compatibility checking and loading cost **0.375 and 0.990 ms CPU** within charged preparation. The exact block scorer compacted all **240** curve profiles, reducing **388,320** original row profiles to **13,165** survivor profiles. It paid the original-height bias multiply and used zero ordinary ranks. The numerical solve took **3.247 CPU s**.

## Input and publication differences

The guarded selective receiver chose the same chronological history branch. It paid 396 refinements and retained the same 456 factors at the same 2,400 original stereo opportunity rows. Ordered factor bytes changed in three score or margin fields and in CFO. Across 256 changed CFO values, the largest absolute difference was **3.20 × 10⁻¹⁰ Hz**. The largest margin difference was **3.87 × 10⁻¹⁴**. The installed Graph retained 438 points versus 442 earlier. Both runs evaluated 24 regional probes with `eligible_exterior_separation` and retained the same archive snapshots, orbit counts and receiver point counts. Both new calibration arms kept the same 290 common owners and roles, with four earlier owners absent and zero new ones. The run included no controlled same-packet solver comparison.

| Containing offer | Horizontal error, `c = 0` / fitted `c` | RF RMS, `c = 0` / fitted `c` | Owners per arm |
|---|---:|---:|---:|
| Installed named v3 | 816.789 / 1,101.409 m | 6.502299 / 6.391940 Hz | 266 |
| Earlier all-paid South | 558.143 / 810.906 m | 6.061236 / 5.968386 Hz | 294 |
| Combined replay | 553.231 / 823.863 m | 6.074602 / 5.974579 Hz | 290 |

In the combined replay, fitted `c` lowered RF RMS by **0.100 Hz** while horizontal error increased by **271 m**. The complete grid and both position sidecars were verified and bind the actual position PNG. All eight PNGs passed encoded digest and decoded RGBA checks, with eight verified reads and zero fallbacks. All eight differ from the earlier all-paid raster outputs. The terminal carries the actual guarded receiver's digest. The near-omitted South offer received no new run, and the earlier false-fix result remains an independent limitation. [Named South comparator](named-south-transfer.md) · [Prior all-paid and omitted-offer score](continued-cfo-south.md)

Thirteen focused combined-route, continued-CFO and South admission tests passed. Launch source is preserved at `d856e1545`. The executing entry stayed at the sealed North runtime sources, with only verifier and documentation changes in its checkout. The post-exit verifier added the field-by-field probe and owner comparison without re-running acquisition, solve or rendering. The expanded receipt SHA-256 is `ce1d12d43bc2769fbfc53aa66c810d0a71237ffc4d4950a78e1d2210f1fd5911`. [Trial and separate verifier](combined_raw_south.py)
