# Why three native-joint fixes were withheld

All three cases passed the 6 km posterior-radius limit in both calibration arms. The independent training-to-pooled comparison rejected all three at its 4 km limit. These radii summarize local geometry conditional on the fitted associations. A small radius does not constrain how much a new fit can move when it changes the track sample and satellite ownership. [Frozen gate values](geometry-gates.json)

| Recording | Training-to-pool shift | Posterior radius, `c = 0` / fitted `c` | Detailed replay |
| --- | ---: | ---: | --- |
| DS26-0197 | 4.249 km | 1.437 / 1.447 km | Archived gate only |
| DS26-0223 | 9.782 km | 1.842 / 1.844 km | Graph 121, 62 points over 42.20 s |
| DS29-0316 | 5.065 km | 1.530 / 1.548 km | Graph 53, 71 points over 60.23 s |

The two instrumented replays reproduced the frozen decision, positions, every scientific metric, and the Graph digest. The original no-repair v5 result came from the matching capture-era scientific evidence package. The original c0 owner table joined to 3,311 of 4,862 gated native points in DS26-0223 and 2,874 of 4,148 in DS29-0316. Target selection used the longest disputed curved track by distinct native points, with duration as the tiebreaker. [Protocol](PROTOCOL.md) · [Run receipt](run_manifest.json)

## DS26-0223 · Graph 121 · RX2 channel 7

Native joint trained on NORAD 60028 and dropped the component in the pooled fit. The published v5 result associated all 62 points with 67315 in both arms and retained five components from that family. The native shortlist already contained 67315. The causal fixed-site diagnostic used the joint c0 position and a shared phase search over ±7.5 seconds. Within this budget, its c0 training leaders 67054 and 60028 had held RF RMS of 6.36 and 6.67 kHz. The first retrospective 67315 element reached 227 Hz using the independently fitted lane correction, and 96 Hz with an extra satellite-specific frequency rate. The extra rate is a sensitivity check whose improvement supplies no independent orbit evidence.

The original v5 owner used the **same causal element bytes as native joint**. The original 48-hour nominal bank selected 67315 at index 1277 and the archived c0 component had 55.09 Hz conditional RF RMS. Its phase was −9.721 s, beyond the initial diagnostic search. The fitted-c phase was −9.724 s. The 72-hour new-family policy admitted zero candidates and the final reassociation selected no recovery. The exact hashes below distinguish the role of orbit phase from access to a more recent catalogue. [Instrumented replay](DS26-0223-native-trace.json.gz) · [Model fits](DS26-0223-candidate-fits.json) · [Figure](DS26-0223-association.png)

| NORAD 67315 TLE | Element epoch (UTC ns) | Two-line SHA-256 |
| --- | ---: | --- |
| Original v5 nominal and native joint current | 1793102274167040000 | `4a4a6230f5c0fe2b1c028bf7864fefe754dac4c51a2048de0a809484dbc5c7e4` |
| Latest genuinely previous causal version | 1793074028535648000 | `ae7d65ff1fd0755091464096cde99ba72cca38c468b2ae1ee8703ccc8ea72cf5` |
| First post-end diagnostic | 1793217601999872000 | `865410371e5aae76a87bbfb34ebbc7a0a104ea34eece818479a4fe20fb7d5c59` |

An authenticated replay of the original regional selector recovered index 1277 of 1,476 with the same two lines. The separate 72-hour newest-causal selector also returned that pair. At each saved v5 position, with the saved hardware and original additive alias `+1` fixed, the phase-only projection of the current element fell from 39,628 to 129 Hz RMS for c0 and from 39,688 to 170 Hz for fitted c. The projections below use the original one-second state grid, Earth-rotation-compensated phase shift, actual RF and all 62 component observations. The published conditional gate includes the remaining v5 orbit and curve terms. Its point support trained the original parameters, so splitting these fixed archived predictions into blocks gives a sensitivity check and does not establish new held-out predictive performance. [Matched projection receipt](DS26-0223-v5-phase.json) · [Phase figure](DS26-0223-v5-phase.png)

| Component model | `c = 0` RMS | Fitted `c` RMS |
| --- | ---: | ---: |
| Causal current element, phase zero | 39,628 Hz | 39,688 Hz |
| Causal current element, saved v5 phase | 129 Hz | 170 Hz |
| Previous causal element, saved v5 phase | 18,143 Hz | 18,190 Hz |
| First later diagnostic element, phase zero | 572 Hz | 511 Hz |
| Original full conditional gate as archived | 55.09 Hz | 54.85 Hz |

## DS29-0316 · Graph 53 · RX2 channel 3

Native joint trained on 66642 and changed the target track to 59384 in the pooled fit. Both satellites were on its initial shortlist. Published v5 assigned all 71 points to 59384 in both arms. Its 59384 family contained eight Graph components. Native joint pooled six as 59384 and two others as 66642. With the causal elements, the grouped held c0 RF RMS favored 59384 over 66642 by 208 versus 573 Hz. The matched fitted-c check gave 242 versus 579 Hz. In the later catalogue the preferred identity changed as satellite rate freedom was added, indicating that later-epoch agreement depends on the nuisance model. The final lane correction excludes all target families. Removing two same-family DS29 references raised the 59384 held RMS from 206 to 208 Hz and preserved the ranking. [Instrumented replay](DS29-0316-native-trace.json.gz) · [Model fits](DS29-0316-candidate-fits.json) · [Figure](DS29-0316-association.png)

## Observability and held-block controls

DS26-0223 training-to-pool ownership kept 110 of 111 training tracks, changed six of the shared IDs, and added 21 previously held tracks. Its EN shift was (+9.63, −1.74) km. DS29-0316 kept 97 of 99, changed five of the shared IDs, and added 32 previously held tracks. Its EN shift was (−4.13, −2.93) km. The shifts measure the combined refit. Two component audits cannot assign them to one satellite or one clock term.

The full catalogue screen used the same TLE provider for current and first observed post-end versions. The DS26 panel screened 11,120 causal and 11,110 retrospective elements, with 513 and 510 satisfying its horizon support. DS29 screened 11,093 and 11,186 elements, with 469 and 474 satisfying its support. This comparison has one provider and no independent satellite telemetry. The predeclared grouped split retained 16 training and 24 held points for DS26 and 22 training and 27 held for DS29. Buffer points adjacent to a held block were excluded from training. A degree-two DS26 polynomial chosen on training reached 5.14 kHz held RMS. Degree three reached 2.26 kHz. The DS29 training-selected degree-three polynomial reached 195 Hz. A polynomial can follow the arc and cannot identify a satellite or constrain site geometry by itself.

The whitened position Jacobian was projected off constant CFO, linear frequency drift and local phase on each fixed-site finalist. For the DS29 causal 59384 component, the singular values were 0.04730 and 0.02369 km⁻¹ and the weak east/north direction was (−0.541, −0.841). Phase derivative versus raw drift correlation was 0.405. For the DS26 later 67315 component, the singular values were 0.00766 and 0.0000654 km⁻¹, the weak direction (−0.401, −0.916), and the phase/drift correlation 0.771. These are local arc diagnostics. The strong RF fit and small second singular value can coexist. [Native-joint trial](../../inference/native-joint/) · [Tabular finalist data](association_summary.csv) · [Artifact hashes](artifact-lock.json)
