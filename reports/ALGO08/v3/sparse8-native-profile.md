# Disjoint stage clocks for the active sparse 8 ms callback

On the actual `c5b57b` 8 ms algorithm, the field-mix projection gives **35.50% of short CPU** for the complete lag and carrier stages. Replacing those two stages together with the four-hypothesis refinement bank raises the gross ceiling to **49.90%**. With the full anchors held fixed, the first-30 elapsed target would leave about **12.9 µs per short lane** in the measured donor for the whole replacement after granting every original operation in those stages. No checked exact receiver route meets that budget. [Protocol](sparse8-native-profile-protocol.md) · [Raw clocks, source pins and pricing](measurements/sparse8-native-profile.json)

## Measured 8 ms callback

The older 8 ms maxima/ranking profile used the pre-sparse `fe4ba7b7` source and covered two search reductions only. The exact sparse transfer reported whole native call clocks. The full stage decomposition used the guarded 12 ms callback. This trial pins the actual sparse timing source and template from the deployed `c5b57b0602e81a6a85c14caf648eb12341f098d09915b4d3f705094ed309574c` and relinks the full DSO byte-for-byte. The instrumented DSO changes only stage marks around the same sparse scout and primary wrapper. The original verifier and refinement objects remain linked. Recording clocks on and off uses the same instrumented DSO and separate matched contexts. [Earlier ranking-only profile and exact transfer](short-rank.md) · [Prior guarded 12 ms scope](short-primary-fusion-profile-protocol.md)

Reusing the archived PGO feedback in the modified object failed compiler coverage checks. Both failed attempts ended during compilation. The successful trace uses fresh site-free profile-guided training with the same pinned synthetic trainer. All 32 training outcomes match the archived sparse receipt. The trace recompilation required strict coverage checks. Fresh instruction layout and timestamp calls can redistribute stage time. The paired totals measure overall instrumentation and rebuild impact. The stage allocations come from the tracing DSO.

Only the detached signed visit prefixes were used. Their complete original per-window I/Q digests, exact stereo layout, signed hardware order, native validity checks and original short/full cadence all agree. They had complete local page residency and no whole-member authority. The profile issued no new acquisition or anchor callbacks. Each compared slot used the unmodified 8 ms native entry on the original zero-center sample buffer. At each visit, lane and repeat the installed control, clock-off and clock-on arms emitted identical full factor bytes, including empties.

| Original detached prefix | Issued visits | Excluded / full anchor / short visits | Short lanes / positive | Installed / clock-off / clock-on CPU, µs per lane |
|---|---:|---:|---:|---:|
| DS30-0163 | 29 | 3 / 8 / 18 | 36 / 10 | 771.58 / 762.14 / 761.77 |
| DS30-0419 | 15 | 6 / 6 / 3 | 6 / 4 | 841.29 / 823.16 / 832.03 |

Clocks are medians of six rotated, paired repeats. The 0419 prefix has only two empty and four positive lanes. Its independent scope is too small to establish a general stage rate. The process took **1.55 s wall, 1.45 s user and 0.09 s system** including launch, authentication, detector setup and all arms. CPU2, nice 15, I/O priority 7 and six one-thread settings were checked in the child. The shared lease was acquired once without waiting. The original sample operands came from tmpfs. The enclosing process reported 3,712 input blocks and 32 major faults without per-file attribution.

## Disjoint profile and field weighting

The first-30 archival ledger records **262,770 short lanes**, of which 124,512 were positive, and **37,752 full lanes**. Short calls account for **298.250 of 439.759 native CPU seconds** and **328.265 of 477.043 summed native elapsed seconds**, or **67.82% CPU and 68.81% elapsed**. The profile recomputes positive and empty per-stage lane means within each repeat, weights them by the field's 47.384% positive fraction, then takes medians. The table transfers only the stage fractions. Its donor sum, 791.55 µs, is below the first-30 paid short mean of 1,135.02 µs CPU. The absolute donor rates are not measurements of the complete field cohort. [First-30 signed ledger](first30-empty-call-roof.md)

| Exclusive stage | Field-mix donor CPU, µs per short lane |
|---|---:|
| Input mixing and conversion | 29.31 |
| FIR | 58.60 |
| Five-frame modes | 37.19 |
| Lag timing | 160.37 |
| Sparse carrier | 120.60 |
| Request setup | 0.21 |
| Full-rate refinement bank | 114.02 |
| Independent pilot confirmation | 56.90 |
| Verifier load | 37.87 |
| Verifier | 176.34 |
| Other checked glue | 0.13 |

All 14 final positives and **11 of 28 final empty lanes** reached verifier loading. The scout confirmation alone therefore does not tell which short calls ultimately return empty. The receipt keeps the positive and empty means separately for each recording, as well as every lane and repeat. The timed instrumentation groups the integer stencil, fractional verifier and residual readout at the unchanged verifier entry.

| Work granted entirely free on the short path | Short CPU ceiling | Combined native CPU projection | Combined native elapsed projection if CPU fractions transfer |
|---|---:|---:|---:|
| Lag timing and sparse carrier | 35.50% | 24.07% | 24.43% |
| Lag, carrier and full-rate refinement | 49.90% | 33.84% | 34.34% |
| Input through carrier, including FIR and modes | 51.30% | 34.79% | 35.30% |
| Pilot confirmation, verifier load and verifier | 34.25% | 23.23% | 23.57% |
| Verifier load and verifier alone | 27.06% | 18.35% | 18.62% |

These are counterfactual ceilings with full anchors unchanged. To remove one third of the combined native term by changing only the short path requires **49.15% of short CPU**, or **48.44% of short elapsed** using the separate measured elapsed weights. The separate complete-publication budget assuming a 1.4× solver needs 48.27% less short elapsed on first30, 30.91% on next16 and 41.79% on all46. Applying those elapsed requirements to the donor's CPU shares assumes the same relative stage costs and a one-for-one effect on callback elapsed. No new whole-publication timing was taken.

A concrete joint scout would have to generate the same signed timing/carrier requests and refine them while keeping the original independent confirmation and verifier. The first30 elapsed requirement, translated to the measured donor under that assumption, leaves **12.9 µs** to replace the existing **395.0 µs** lag/carrier/refine stage. The corresponding allowance for saving a third of combined native CPU is **6.0 µs**. Even granting every result in the entire input-through-carrier section, the first30 criterion would leave **24.0 µs** to replace it. The earlier four-row timing oracle granted exact timing for free and kept the paid carrier transforms. Regional masking only trims ranking and cannot omit those transforms. Earlier cheaper 8 ms cross-lag cues missed factors. The available algorithms still leave material work in those sections. No new native cut was promoted from this profile. [Earlier timing grant](timing-only-oracle.md) · [Regional carrier audit](regional-carrier-scout.md) · [8 ms lag transfer](cross-lag-eight-ms.md)

The profile command requires the already authenticated detached operands, exact archived source/build, and the one nonblocking CPU2 admission. The offline pricing command can run on the sealed receipt without these inputs.

### Sensitivity to which recording supplies the stage costs

Using DS30-0163 and DS30-0419 separately gives the following projections for the first 30 complete benchmark pairs. The calculation uses each recording's actual fraction of empty short calls, measured short-call wall time and measured solver time. It assumes the whole solver becomes 1.4× faster and the 20 ms anchors keep their original cost. The first two columns grant free replacement stages. The last column asks how much CPU an actual replacement could spend on each short lane before the summed wall gain falls below 2×. At that allowance both median speedups still exceed 2.05×. [Paired timing targets](receiver-solver-targets.md)

| Source prefix | Free lag and carrier stages, summed speedup | Also free full-rate refinement, summed speedup | Allowance for all three replacement stages |
|---|---:|---:|---:|
| DS30-0163 | 1.942× | 2.008× | 12.68 µs/lane |
| DS30-0419 | 1.939× | 2.003× | 5.56 µs/lane |

The allowance depends materially on the prefix, particularly the six measured lanes in DS30-0419. Both projections assume that a fraction of donor CPU removed saves the same fraction of original wall time and preserves every scientific result. Use `price-per-prefix` in place of `price` below to reproduce these figures.

```sh
python -B -m reports.ALGO08.v3.sparse8_native_profile price \
  reports/ALGO08/v3/measurements/sparse8-native-profile.json
```
