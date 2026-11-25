# Reuse the integer phase table in the sparse 8 ms verifier

The guarded shortcut reduced the complete sparse8 callback CPU by **8.27%** on 36 signed DS30-0163 short lanes and **12.77%** on six DS30-0419 short lanes. All 14 detections and 28 empty results were preserved. Pricing the larger donor at DS30-0016's measured positive and empty rates estimates **0.089 seconds** less native CPU, or **5.16%** of the combined full and short native work. The target was 15–20%. This is a component candidate with a different numerical identity. The experiment leaves the full 20 ms two-scan anchors untouched.

## Executed change

The active sparse8 DSO `c5b57b0602e81a6a85c14caf648eb12341f098d09915b4d3f705094ed309574c` calls `portable_verifier_factor` with frame-relative phase disabled. The integer stencil already prepares exactly 2,816 signed carrier tap rotations. The fractional verifier prepares up to 14,080 absolute tap rotations again across five frames. The new overlay reuses the integer table to precombine each original pilot and its rolled control once. When the absolute frame origin and fractional vertex offset contribute a shared phase within a frame, that phase cancels from the squared per-frame spectrum and its normalization. Absolute rounded tap positions, Lanczos coefficients, sample values, timing scout, integer stencil, fractional vertex and signed residual conversion retain the original operations.

Earlier frame-relative work still generated one new 2,816-tap rotation table. Periodic `sincos` anchors approximate the absolute rotation itself, and the separately qualified full-anchor replacement touches the 20 ms path. Coarse shared preparation and sparse carrier ranking act earlier. The earlier short-prefix reuse saves a different optional CFO readback, which this receiver does not call. The active sparse8 timing object stays byte-identical in this experiment. [Fractional phase study](../single-core-2x/receiver-fractional-phase.md), [Periodic anchors](anchored-phase.md), [Full-anchor transfer](guarded-full-anchor-sparse8.md), [Shared preparation](short-shared-prep.md), [Sparse ranking](short-rank.md), [CFO readback](short-prefix-correlations.md), [Disjoint sparse8 timing](sparse8-native-profile.md).

The experimental branch requires the same cached signed CFO and round-to-nearest. It doubles the phase rounding allowance in the existing L1 perturbation enclosure, checks both competing spectral-bin gaps and the 0.025 acceptance and 0.1 strong-margin boundaries, and routes invalid or inconclusive values to the original absolute scorer. A successful shortcut invalidates the integer cache as stock does. This is a floating-point rearrangement. The guard bounds the original tested decision surfaces, and measured parity applies to the admitted lanes. Later cross-visit selection and geographic publication were outside this callback trial.

## Matched signed callbacks

Frozen at `b554bbf69180952e54106f9bc918824c68a46b6d`. The source pins and exact compile/relink commands are in the [receipt](measurements/short-shared-integer-phase.json). Build manifest `66864c1e316a4386968709601ede2c64d27eccdb7743207f54438aa13760aee1`, audited exact DSO `3810e063339381b8d9ff46ce82f625c44d5c91e7cc5b41f7df2878e6cbab3885`, audited shared DSO `f8760023d4646a1f6e2ec5528a6e105bb518b5fff2910e5a7af31378c3456e57`. A pristine relink matched the original c5b57b SHA and its factor bytes matched the instrumented exact arm at every lane and round.

The replay used authenticated complete CI16 windows already held in two incomplete original archive prefixes. Original 20/8 schedule admitted 18 short visits in the first 29 issued DS30-0163 visits and three in the first 15 DS30-0419 visits, both radios per visit. The source receipts bind original per-visit SHA-256, aperture and order. The controls share whole native callback timing around `cancellation_primary_factors`, including identical verifier event recording and excluding audit extraction, fixture authentication and context initialization. Six rounds alternate AB and BA for each lane in independent chronological contexts. The process completed in 1.517 s with 1.313 s user and 0.081 s system on CPU2 at nice 19, idle I/O and one numerical thread after a DS30-0212 official deferral. There was one shared lease and no backing waveform reads, catalogue reads or solves.

| Signed prefix | Short lanes, positive / empty | Exact CPU µs/lane | Shared CPU µs/lane | Paired CPU saving µs/lane, median (range) | Paired elapsed saving µs/lane, median (range) |
| --- | ---: | ---: | ---: | ---: | ---: |
| DS30-0163 | 36, 10 / 26 | 785.706 | 720.562 | 64.939 (56.737–73.541) | 64.972 (56.824–154.764) |
| DS30-0419 | 6, 4 / 2 | 848.917 | 730.502 | 108.447 (88.633–128.323) | 108.395 (88.565–128.257) |

Each round's mean includes all applicable lanes. The table reports the median arm means and the median of the six paired mean differences. One DS30-0163 elapsed round had a much larger difference than its CPU time, so use CPU for transfer pricing.

Twenty-five lanes reached the verifier. Twenty-two entered and passed the shortcut, including all 14 emitted detections and eight of the rejected lanes. Three paths used the exact scorer without a shortcut attempt. No real shortcut attempt required an exact rerun in this sample. All 17 native scout empties stayed empty. Across six rounds, all ordered ranks, integer and fractional timing, signed CFO, flags and fractional residuals matched bit for bit, including rejected verifier events. The largest absolute changes were `2.45e-14` in the exact score and `2.69e-14` in the rolled score. Every non-shortcut result matched the exact arm's score bits. A CPU3 preflight with 32 synthetic lanes across both pilot edges exercised 29 successful verifier paths and separate native guard checks for bin ties, the two score boundaries and unusable inputs. Largest synthetic score change was `4.83e-14`.

## Field cost

The natural DS30-0016 run paid 1.147221 s of short native CPU for 432 positive and 808 empty lanes, plus 0.580942 s for the 186 full lanes. The positive and empty donor means give these transfer estimates. There is no raw-to-exit timing credit in this extrapolation.

| Donor | Median paired CPU saved per positive µs | Per empty µs | Estimated 0016 native CPU reduction | Share of all paid 0016 native CPU |
| --- | ---: | ---: | ---: | ---: |
| DS30-0163 | 140.021 | 35.572 | 0.089231 s | 5.16% |
| DS30-0419 | 129.614 | 64.496 | 0.108106 s | 6.26% |

DS30-0419 has only two empty lanes and is a sensitivity check. Before the trial, deleting the entire disjoint verifier stage at the observed 0016 lane mix would save at most 0.225 s under the 0163 timing donor, about 13.00% of combined native CPU. The six-lane 0419 donor prices that ceiling at 0.266 s or 15.37%. Any combination should count additional wins only at disjoint paid boundaries and recheck the complete normal detector, including downstream uses of the changed score bits. [Natural 0016 comparison](measurements/combined-small-panel-0016-natural-pair.json.gz), [Frozen protocol](short-shared-integer-phase-protocol.md).
