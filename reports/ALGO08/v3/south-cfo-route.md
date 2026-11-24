# Held-anchor selection before fixed-epoch CFO on public South

The combined route improved both South containing positions relative to installed named v3. It still published a false fix when truth was 100 m outside the offer. The signal-only held selector chose history from the original unrefined probes, with gains of **+12.5096 and +12.5208 nats** on the two radios. Its 456 selected opportunities exactly matched all 456 named-positive opportunities in a post-publication join. The runtime selector used no named lane answers, geography labels or fitted owners. [Frozen protocol](south-cfo-route-protocol.md) · [Sealed publications](measurements/south-cfo-route.json.gz)

| Original offer and method | Decision | Horizontal error, fixed / fitted `c` (m) | RF RMS, fixed / fitted `c` (Hz) | Owners per arm |
|---|---|---:|---:|---:|
| Containing, installed named v3 | Fix | 816.789 / 1,101.409 | 6.502299 / 6.391940 | 266 |
| Containing, selected refined raw | Fix | 558.143 / 810.906 | 6.061236 / 5.968386 | 294 |
| 100 m outside, installed named v3 | False fix | 817.172 / 1,102.143 | 6.502345 / 6.392003 | 266 |
| 100 m outside, selected refined saved | False fix | 557.732 / 810.879 | 6.061069 / 5.968380 | 294 |

The candidate improved the containing errors by 258.6 / 290.5 m. The fitted branch reduced RF RMS by 0.093 Hz and worsened position error by about 253 m relative to fixed `c` on each offer. Both offers and both arms used exactly the same ordered roster of 285 conditional and nine predictive owners. Of those 294 observations, 256 had an applied CFO edit. Both named signed fits ran and were accepted. No isolated-family repair or inference fallback ran. The certified curvature early exit stayed inactive on a maximum retained lane span of 286 s, above its 20 s threshold. The regional scan visited 24 probes on each offer and stopped at `eligible_exterior_separation`. The downstream exterior test did not evaluate either bound.

The two containing endpoints were 527.040 / 461.440 m inside the offered east face, with truth 100 m inside. The omitted endpoints stayed 327.208 / 261.446 m inside the same face after translation, with truth 100 m outside. A simple clamp check cannot detect this false fix. The result is one South simulation and two offers on its single original acquisition. [Named mirror comparison](named-south-transfer.md)

## Signal work and process cost

The genuine mixed receiver admitted all 1,200 visits across 19 signed staged tmpfs members. It executed 304 full-aperture and 2,096 short-aperture antenna calls. On both radios together it measured 703 selected factors before the route decision, including 70 full anchors and 633 short positives. It paid all 633 short refinement attempts and produced 460 CFO edits. The unchanged held history retained 456 factors and all 396 retained short positives had their CFO refined, 198 per antenna. The 60 retained anchors stayed byte-identical. Thus 64 edits paid for by the receiver were subsequently discarded by the route. The original restored probe bytes matched the authenticated unrefined probe digest exactly. On the retained support the candidate changed no epoch, signed opportunity, margin, score or other factor field. The new recipe is `sha256:33596ef446a53ad9a274e65f4dcef4b135cd25d2ecd6e3b058dd8823a1ccd8e4` and native output is `sha256:b0926955297126a160679dc4d1be549726739bf1fc399a53ce97a8e0e932b2d8`.

| Measurement boundary | CPU (s) | Elapsed (s) |
|---|---:|---:|
| First raw child, paid through selector import failure | 6.359 | 6.364 |
| Corrected containing raw child through full publication | 11.612 | 11.614 |
| Corrected containing authenticated acquisition | 5.693 | 5.693 |
| Fixed-epoch refinement within acquisition | 0.463 | 0.463 |
| Held route and authenticated selected handoff preparation | 0.039 | 0.039 |
| Corrected containing solve | 3.637 | 3.637 |
| Omitted saved child through full publication | 6.603 | 6.674 |
| Omitted saved solve | 3.470 | 3.537 |
| Historical named containing raw child | 14.179 | 14.370 |
| Historical named omitted solve | 4.487 | 4.549 |

The corrected raw publication was about **1.24×** faster than the historical named raw publication on the same waveform and region. This is a noninterleaved comparison with different initial residency evidence. The corrected attempt started and ended with all 384,361 payload and 188 index pages resident and reported zero filesystem input blocks. The first launch started with 92 nonresident payload pages and paid 632 blocks before its import failure. Its clock remains separate. Including the failed child, the experiment paid 17.978 s of raw process elapsed time. There was no conditioning pass, change to the staged files or read from an original physical recording archive. [Initial passive eligibility](measurements/south-cfo-route-eligibility.json)

The first child completed acquisition, then a late import tried to subclass a detector factory that the real wrapper had temporarily replaced with a callable. It emitted no packet. The generic fix removed the unused late imports, and a saved smoke test under the same callable replacement verified routing and a synthetic single retained CFO change before the one authorized correction. The corrected containing and saved mirror both exited zero. They published complete 144- and 137-node matched grids and eight decoded and digest-verified PNGs each. Each grid and path binds its own verified position PNG. The mirror used the corrected raw result byte-for-byte through one authenticated handoff with waveform access denied.

The corrected execution source is `df79f8618` with the generic selector fix from `8280df546`. The uncompressed result SHA-256 is `cee62c62dddca08dc2e256791c28febd76da38d27a300e36c07e34a836a0c25f`. Its bindings retain the prior failed clock, saved smoke proof, actual raw recipe and both complete publications. Twelve component tests passed across the selector, South transfer and named finish suites.
