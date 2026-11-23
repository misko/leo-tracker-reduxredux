# Matched short measurements drive the fitted error change on DS30-0016

On the original weak fix, replacing matched signed tuples with their mixed-aperture measurements increased fitted horizontal error by **675 m** on named membership. Removing unmatched named factors added **90 m**. Adding the unmatched mixed factors recovered **732 m**, leaving the observed **33 m** fitted regression. Restoring the named measurements on final mixed membership improved fitted error from **1.694 to 1.459 km** while retaining all **116 ordered owners** in both calibration arms. These substitutions identify a measurement-quality opportunity on retained short hypotheses. Deleting added lanes would remove evidence that helped this fix. [Frozen protocol](full-short-factor-contrast-protocol.md) · [Replays, score and signed owner audit](measurements/full-short-factor-contrast.json.gz)

## Signed changes at the detector boundary

The two archived packets are from the latest matched warm raw pair and contain 440 named and 475 mixed selected factors. Each maintains the same 808 issued visits, 713 admitted stereo visits and 95 exclusions, with the same ordered physical lane keys, raw authority, original 25 km offered square and causal TLE archive. The earlier 12→8 ms crossover addresses a different aperture change. The earlier full-short crossover established exact installed-solver scientific endpoints on these same input packet digests. Both references were reused, leaving three new saved solves. [Earlier aperture-factor experiment](eight-ms-crossover.md) · [Installed finish controls](full-short-crossover.md)

At each shared receiver, counter, RF, edge and channel, measurements agree for this comparison when wrapped fractional time differs by at most two native samples and signed CFO by at most 250 Hz. When both sources have incompatible selected factors on the same lane, the path drops the original and adds the alternate in separate steps. This keeps one selected factor per probe. Matched replacements use complete measured tuples, preserving the exact score, rolled control, fractional margin and rank together with signed timing and frequency. The experiment therefore identifies the effect of the whole measurement. It cannot separate the individual effects of CFO, epoch, rank and score.

| Radio and scheduled aperture | Matched | Changed tuple within match | Stock-only | Mixed-only | Both present with incompatible signature |
|---|---:|---:|---:|---:|---:|
| RX0 anchor | 37 | 0 | 0 | 9 | 1 |
| RX0 short | 207 | 207 | 18 | 38 | 27 |
| RX1 anchor | 20 | 0 | 0 | 7 | 0 |
| RX1 short | 99 | 99 | 21 | 20 | 10 |
| Total | 363 | 306 | 39 | 74 | 38 |

The 57 close anchor pairs are byte-identical. Seventeen anchor lane selections differ in the original packets, where named continuation and mixed strongest-margin selection use different rules even on full acquisitions. Preserve those differences in the membership contrasts. On the 306 close short pairs, the median absolute CFO changes are **58.19 / 73.56 Hz** on RX0/RX1, and the median wrapped timing changes are **0.290 / 0.228 samples**. The maxima are **243.52 / 229.82 Hz** and **1.076 / 0.781 samples**. A signature match is a measured similarity, without an independent satellite label.

## Both calibration arms through the installed finish

| Signed packet | Selected factors | Error fixed / fitted (km) | RF RMS fixed / fitted (Hz) | Final owners per arm |
|---|---:|---:|---:|---:|
| Archived named | 440 | 1.644 / 1.661 | 109.375 / 109.479 | 109 |
| Replace matched tuples | 440 | 2.299 / 2.336 | 101.350 / 101.315 | 108 |
| Also remove unmatched named | 363 | 2.409 / 2.426 | 103.011 / 102.986 | 105 |
| Archived mixed after adding unmatched mixed | 475 | 1.311 / 1.694 | 121.526 / 120.291 | 116 |
| Mixed membership with named matched tuples | 475 | 1.160 / 1.459 | 121.025 / 120.518 | 116 |

Replacing matches on named membership worsened fixed/fitted error by **656 / 675 m**, although it decreased RF RMS by **8.02 / 8.16 Hz**. Dropping the 77 unmatched named factors increased error by **109 / 90 m**. The step removes three final owners, each from an incompatible same-lane carrier signature. Adding the 112 unmatched mixed factors improved error by **1,098 / 732 m** while increasing RF RMS by **18.52 / 17.31 Hz**. Nine genuinely mixed-only owners and one incompatible same-lane replacement then enter the fit. The graph also recruits one already present matched observation. All 105 prior assignments retain their NORAD and role. The three path contributions are conditional on this order and sample.

With full mixed membership fixed, restoring the named measurements on the close pairs preserves the exact ordered rows, satellite IDs and owner roles for all 116 owners per arm. The fixed and fitted errors improve by **151 and 235 m**. The fitted RF RMS rises by **0.227 Hz**. Prepared graph points still change from 354 to 368, so this is equality of final ownership. It directly tests the value of improving the retained measurements even when final owner stability provides no warning. An independent within-short-aperture CFO or phase consistency estimate could identify where a full-length recheck is worth paying for. The observable would need independent calibration and comparison with equal-budget uniform checks. The archived pairing used for this diagnostic requires both measurements and supplies no live routing rule or throughput result. [Prior margin-only weighting](short-margin-variance.md)

## Verification and reproduction

Each new private packet has its own diagnostic detector and analysis digests, preserves every original opportunity and runs through the installed solver without the alternate graph or inference bundle. All three complete both c arms, evaluate all 179 numerical grid points with zero objective replay difference, preserve ordered owner rows bound to the published owner maps, and publish all eight SHA- and decode-verified PNGs with valid position-grid and position-path pointers. Solve CPU was **3.353 / 3.220 / 3.222 s** in the listed new-cell order. Saved processes exited successfully in **6.349 / 6.076 / 6.192 s**. No raw data was read. The first attempts failed reader-root and terminal-status enrollment checks, then the first worker stopped before solving at the lazy loader. After all three successful scientific publications sealed, the installed tools path lacked a local scorer import. The separate score command used the local scorer on the sealed outputs without repeating any solve.

Use `full_short_factor_contrast.py run NEW_TMPFS_ROOT` under the shared exclusive Gauss lock, CPU 2, nice 15, best-effort I/O priority 7, one numerical thread and the installed v3 payload first for receiver and solver imports. Then run `score` and `ownership` on the completed root with the research tree and `src` in the Python path. The input, numerical seal, geographic score and owner audit raw SHA-256 values are respectively `1f3ba13ff9f701faf10a46e7706c9a875c057b31aff5eeec931cd9f5f7299038`, `2e1017bc72b18843bec41e304134f5a53637d1a98e6420558e115d5617791f87`, `ca032171a4994ceaca13639476db9f40f651d2c86839bc562ecabbf9ebf6b9b4` and `5526927737375a150a8efd72df634c26ce08a111dc60add62d36983c596772d8`. Three component tests passed. [Driver](full_short_factor_contrast.py) · [Tests](../../../tests/pipeline_eval/test_full_short_factor_contrast.py)
