# Public South transfer of whole-stereo thinning

The frozen two-of-three short schedule improved the South containing fix by 224/658 m relative to named ALGO08v3. It still published a false fix in both calibration arms when the original 25 km square excluded the receiver by 100 m. The two masked estimates moved only 0.21/0.10 m between the containing and omitted offers. Named v3 and complete mixed coverage also falsely fixed on the omission. [Frozen transfer](whole-stereo-blocks-south-protocol.md) · [Full numerical evidence](measurements/whole-stereo-blocks-south.json.gz)

Both candidates consumed the exact same derived packet from the original 1,200-visit public simulation. Each retained 304 full two-scan anchor calls and 1,408 of 2,096 short calls. The 344 omitted stereo visits leave their original two empty hardware-clock slots. The verified unfiltered 20/12 ms packet went from 703 to 501 factors, with 353 to 247 on the first radio and 350 to 254 on the second. That packet supplied neither new waveforms nor a continuation decision. For comparison, a separate audit of the released continuation dropped 136 selections on omitted slots and 92 more on later paid slots, leaving 228 of 456 selected factors. The saved position runs used the unfiltered proposals.

| Offer and receiver | Terminal | Error, km | RF RMS, Hz |
| --- | --- | ---: | ---: |
| Containing, named v3 | Fix | 0.817 / 1.101 | 6.502 / 6.392 |
| Containing, full mixed | Fix | 0.454 / 0.515 | 8.312 / 8.188 |
| Containing, masked mixed | Fix | 0.593 / 0.444 | 8.010 / 7.894 |
| 100 m omitted, named v3 | False fix | 0.817 / 1.102 | 6.502 / 6.392 |
| 100 m omitted, full mixed | False fix | 0.454 / 0.515 | 8.312 / 8.188 |
| 100 m omitted, masked mixed | False fix | 0.593 / 0.444 | 8.010 / 7.894 |

Each pair orders `c = 0` then fitted `c`. Against unthinned mixed, the containing fixed-arm error rose 139 m while the fitted-arm error fell 71 m. RF RMS fell 0.302/0.294 Hz relative to unthinned mixed and rose 1.508/1.502 Hz relative to named v3. On the omitted offer the estimated position remained 486/343 m inside the east face. Both masked geographic checks stopped at `inside_score`, after 25 probes, as in the archived mixed controls.

The mask reduced the association graph from 504 to 372 points and from 26 to 24 tracks, with all 1,618 entries in the cold catalogue pool retained. The solver completed two exact cold finalists versus three under full coverage and recorded `not_three_finalists` for the three-way routing test. Each completed finalist still had 11 phase labels. The signed fit retained 11 phase means and the same 5,579 training, 1,925 future and 372 disjoint future correction rows as the full controls. Both masked offers selected the same ordered 342 owners in each arm. Against complete mixed coverage, 298 owners remained with identical roles and satellites, 170 were dropped and 44 were added per arm. The two published grids had 151/137 evaluated cells and each carried a verified path and eight decoded, digest-checked PNGs.

The measured saved processes exited 0 in 7.511/6.925 elapsed and 7.450/6.866 CPU seconds. Numerical solve clocks were 4.055/3.669 CPU seconds against the historical full mixed 4.343/3.931. Historical full mixed used the installed graph and earlier regional/publication kernels. The process clocks recorded 208/9,352 input blocks independently of the saved-only waveform guards. Those counters are process-wide. Both solves ran with the exact original authority, archive, cutoff, hardware metadata and offers, and read zero original waveform bytes. The whole native acquisition budget for this schedule remains a separate measurement. The preflight caught and corrected a transcribed request digest before either numerical child started.
