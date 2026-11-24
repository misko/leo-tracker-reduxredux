# Late pilot coherence after a short-receiver miss

The frozen nominal-period suffix contrast did not distinguish short misses that the wider receiver could recover. At the same retry budget outside DS30-0049 it restored 12 installed-matching factors. The off-period feature restored 24, evenly spaced selection 16, and sample-blind hash selection 17. Genuine two-scan retries gave 12, 24, 16, and 18 matches respectively. On DS30-0049 the nominal contrast restored zero of the seven installed owner lanes eligible in the prefix. No position solve was run.

## What was measured

Only nonanchor lanes with an empty result from the actual 8 ms primary ABI could be nominated. The prototype ranked a fixed signed difference between later and earlier normalized complex coherence at exact three-frame spacing. It compared against the same calculation at an off-period lag, evenly spaced chronological selection, and deterministic hash selection. Each method nominated one quarter of eligible lanes, rounded down per scope, from the same signed roster. Every eighth admitted visit per RF stream kept its full two-scan anchors. All four captures sealed the exact nomination IDs before joining the measured 20 ms factors and independently bound installed labels. Both 0049 and 0016 short paths matched their published strongest-margin packets exactly. Installed chronological replays matched every control lane in all four scopes. Factor matches use signed 250 Hz and two wrapped fractional samples.

The prior occupancy feature measures repetition in the first 8 ms and ranks activity before receiver search. The prior repeat-negative and three-origin tests screen before an expensive call, and the coherence timing surface searches over epochs across an aperture. The present assay compares equal computational effort before and after the short window and starts after the paid short receiver misses. A synthetic phase-repeated late burst ranked above its early-only counterpart, a stationary tone produced negligible difference, and an off-period lag suppressed the synthetic burst response. [Frozen protocol](late-pilot-rescue-protocol.md) · [Earlier occupancy](occupancy-protocol.md) · [Exact-period negative screen](repeat-negative-protocol.md) · [Three-origin screen](three-origin-negative-protocol.md)

## Recoverable factors and the matched retry budget

| Recording scope | Issued / admitted visits | Short misses | Any 20 ms primary positive among misses | Installed-matching ceiling, primary / two-scan | Retries per selector | On-period | Off-period | Evenly spaced | Hash |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| DS30-0049, six members | 384 / 362 | 424 | 55 | 33 / 34 | 106 | 4 | 10 | 7 | 10 |
| DS30-0016, complete | 808 / 713 | 808 | 138 | 78 / 79 | 202 | 11 | 24 | 16 | 16 |
| DS30-0008, first member | 64 / 64 | 51 | 14 | 2 / 2 | 12 | 0 | 0 | 0 | 1 |
| DS30-0169, first member | 64 / 51 | 41 | 8 | 2 / 2 | 10 | 1 | 0 | 0 | 0 |

The four rightmost columns count installed matches at the matched budget with genuine 20 ms primary retries. At the same rate, 20 ms two-scan retries recovered one additional match for evenly spaced on DS30-0049 and one for hash on DS30-0016. The preselector two-scan alternatives reached the same installed-matching ceiling as strongest two-scan in each enrolled scope. The two independent first-member holdouts had two available installed matches each, so their one-lane differences carry little weight.

Among the seven genuine DS30-0049 owners that went empty in the prefix, a full retry could restore six with primary and seven with two-scan. The on-period feature selected none. Off-period restored four with either detector, even restored one or two, and hash restored two with either detector. Across all 424 prefix misses, the 55 full-primary positives included 21 with no installed selected factor. The 30 on-period 20 ms primary positives on DS30-0016 included 19 such additions. These are measured alternate factors. Their geographic usefulness is unresolved. None of the 808 short misses on DS30-0016 was an installed-owned lane.

The empty-only policy leaves existing 8 ms positives untouched. Applying the same ranking to a separate counterfactual quarter of 0016 short positives would replace 108 lanes with 20 ms primary, drop 21 to empty, strongly displace 17 more, and lose 11 strong short factors by the 0.10 native-margin criterion. No installed-matching short factor would be lost in that particular counterfactual; 17 would become installed-matching. The actual tested nomination made zero such replacements.

## Receiver cost

| Recording scope | Short-only native CPU | Feature CPU on eligible misses | Receiver CPU with primary retries | Receiver CPU with two-scan retries | Full diagnostic process wall / CPU |
|---|---:|---:|---:|---:|---:|
| DS30-0049, six members | 719.3 ms | 12.3 ms | 874.4 ms | 886.5 ms | 5.91 / 5.40 s |
| DS30-0016, complete | 1,489.4 ms | 24.3 ms | 1,805.5 ms | 1,854.8 ms | 10.31 / 10.28 s |
| DS30-0008, first member | 148.0 ms | 1.5 ms | 167.6 ms | 171.6 ms | 1.95 / 1.93 s |
| DS30-0169, first member | 131.5 ms | 1.2 ms | 148.3 ms | 152.8 ms | 2.41 / 1.83 s |

Retry projections add measured per-lane retry CPU, feature dispatch and nomination ordering to the unchanged short-only callback sum. Ordering took 0.270 ms on 0049 and 0.612 ms on 0016. The primary retry projection adds 21.6% and 21.2% receiver CPU on those cases. The measurement process intentionally ran the diagnostic alternatives and both feature lags as well as signed decode. It used only already resident tmpfs recordings under the one-core lease. The ranked quota uses all admitted misses in a scope, so the CPU projection excludes buffering or replay work an online route would need to implement that quota.

The first DS30-0008 launch stopped at a local user quota error during native helper linking, before opening any waveform. The replacement worker read the same pre-enrolled resident original under the same lease. Its first read-only score picked a historical mixed-aperture document and rejected 67 mismatching lanes. The corrected scorer verified the installed receiver digest and matched all 128 lanes against the exact first-member control. Neither recovery changed the enrolled calculation or nomination seal. [Sealed nominations, alternatives, scores and clocks](measurements/late-pilot-rescue.json.gz)
