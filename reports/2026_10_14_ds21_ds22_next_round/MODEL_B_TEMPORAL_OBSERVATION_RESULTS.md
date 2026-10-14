# Measured revisits do not justify a persistence repair of B059

Both source-frozen slices completed under the declared120/135/140-second bounds:05313.931s and05915.992s. There were **6 original objective replays,6 explicit orbital predictions,6 standalone likelihood replays and zero fits**. Neither held observations nor references were read. All selected candidate IDs, CFOs, support-center timestamps, RFs, receiver/channel identities and margins closed exactly to the original public prepared contract. The same incumbent, fitted A-donor and original full/start3 states remain unchanged; the rejected053/start3 is diagnostic only.

The measured evidence does not support visibility turnover or widespread satellite hopping as the cause of the distant059 mode's likelihood advantage. Recorded native alternatives resolve some apparent CFO jumps, but those windows explain little of the receiver-opposed score gap. This is not evidence that all selected CFOs or inferred satellite identities are correct.

## Measured observations and revisit scope

| Training inventory | 053 | 059 |
|---|---:|---:|
| Selected windows | 1870 | 2522 |
| Original training probe opportunities | 5020 | 5804 |
| All recorded candidates, including rejected margins | 26332 | 30688 |
| Passing projected alternatives | 5409 | 6907 |
| Selected candidate has nonzero recorded rank | 464 | 662 |
| Adjacent pairs in exact RX/channel/RF lanes | 1854 | 2506 |
| Nonoverlapping pairs with positive gap≤1s | 1055 | 1415 |
| Longer gaps excluded from transition summaries | 799 | 1091 |
| Median selected revisit gap, seconds | .356005 | .356004 |
| 90th percentile gap, seconds | 1.777351 | 1.776008 |
| Maximum gap, seconds | 174.346203 | 170.071456 |

There are16 exact lanes per case, no nonpositive gaps or overlapping selected supports, and no work-cap exceedances. The original training partition uses20-second blocks and seed20261012. Missing/held blocks are not bridged into inferred families. Passing alternatives per window have median3/2 and maximum8 for053/059. The original selection is highest passing margin, not necessarily rank0; neither rank nor GLRT margin is treated here as a probability.

The source sampling circle is2.5MHz, whereas B folds residuals with227272.727273Hz. Median absolute measured CFO increments on eligible edges are1086.572Hz/1172.385Hz; 90th percentiles1733.910Hz/42541.309Hz. Native-circle wrapping changes none of these increments. B folding reduces the respective90th percentiles to1585.978Hz/22305.655Hz. Thus the two periodic conventions differ on large jumps; this audit does not change either likelihood or a receiver's physical frequency lift.

## Recorded alternatives versus discontinuities

The provisional continuity gate is15kHz/s times the actual pair gap plus5kHz. It uses measured native support centers and excludes overlapping alternative supports. This is a deliberately declared plausibility check, **not evidence that consecutive windows contain the same emitter**. The1-second cutoff is audit scope, not a persistence tau.

| Eligible-edge count | 053 | 059 |
|---|---:|---:|
| Selected pair fails provisional gate | 85 | 200 |
| Another passing native pair satisfies gate | 36 | 83 |
| RX0 failures / alternative rescues | 60 / 32 | 148 / 76 |
| RX1 failures / alternative rescues | 25 / 4 | 52 / 7 |

Alternatives rescue42.4%/41.5% of flagged pairs, or3.4%/5.9% of all eligible edges. Their median minimum paired margins are.3571/.4099 versus selected paired margins.3908/.4726. These are genuine recorded passing alternatives with retained ranks, scores, margins and own support times; the diagnostic minimum does not reselect measurements.

Join the unique endpoints of rescued pairs to the independently sealed [window NLL decomposition](MODEL_B_WINDOW_SCORE_RESULTS.md), by exact window ID. Count a window once even when two adjacent edges are rescued:

| Donor minus incumbent NLL | 053 | 059 |
|---|---:|---:|
| Unique rescue-adjacent windows | 68 | 155 |
| Their summed gap | −28.710734 | +50.877986 |
| Gap over all remaining windows | +242.756829 | +402.528721 |
| Total gap | +214.046095 | +453.406707 |

For059, the dominant adverse CH7 term has only **one** flagged edge and **zero** rescues; CH6 has16 flagged edges and5 rescues. The rescue subset's RX0 gap is+58.789187 and RX1 gap−7.911201. Even all368 unique endpoints of flagged059 pairs have a net gap of−52.623767, meaning that subset already favors the donor. This descriptive join does not alter weights, define a new likelihood, or establish a causal intervention. Smoothly selected competing emissions remain possible.

## Fitted transitions remain a separate quantity

On eligible edges, the posterior overlap is the dot product of consecutive satellite responsibilities; it is not a measured identity probability. MAP changes count only pairs for which both endpoints select a signal component. Confident pairs additionally require both maximum posteriors≥.9.

| Case/state | Both-signal pairs | Confident pairs | Confident MAP changes | Mean same-satellite overlap |
|---|---:|---:|---:|---:|
| 053 incumbent | 539 | 388 | 12 | .406442 |
| 053 fitted A donor | 496 | 348 | 12 | .375968 |
| 053 original start3, rejected | 481 | 321 | 12 | .356157 |
| 059 incumbent | 707 | 492 | 35 | .383228 |
| 059 fitted A donor | 601 | 424 | 23 | .328395 |
| 059 original start3 | 585 | 395 | 15 | .319484 |

Every signal MAP at the left endpoint remains geometrically visible at the next endpoint, including pairs ending in clutter. This rules out loss of that MAP's geometric availability on these edges, not exclusion from the original candidate bank or correctness of the orbital prediction.

For059 smooth selected-CFO pairs, the incumbent changes confident MAP13/465 times, versus donor7/399. Flagged CFO jumps account for22/27 incumbent and16/25 donor confident changes. The incumbent's mean overlap on smooth edges is.440913, higher than the donor's.369644; on jumps it falls to.032791 versus.077808. Receiver summaries retain the original conflict: incumbent/donor overlap is.433069/.298458 on RX0 and.242460/.412946 on RX1. Higher overall overlap is confounded with greater signal responsibility and is not localization evidence. A generic persistence penalty could reward a stable wrong mode; these results do not justify one. The earlier039 temporal-refresh negative experiment also remains relevant.

## Next discriminating test, not yet run

Prioritize a fixed-state **all-passing-branch compatibility audit under unchanged B physics**, before changing alias conventions or imposing emitter persistence. Evaluate each recorded passing alternative at its own native receive time/RF using the exact frozen B calibration function and original orbital/timing state. At all three sealed states, retain per-channel selected/best branch support, actual margins/ranks, and common-branch near/far log-density-ratio bounds. No margin-to-probability conversion, truth-based branch choice, geographical fit, or branch replacement should enter selection. A counterfactual best-branch bound must be labelled as such, not reported as a calibrated likelihood or improved localization.

This can distinguish censorship by a single selected peak from stable support for a competing emission, especially on smooth RX0 CH6/7. If recorded alternatives do not materially change that support, adding arbitrary temporal weights has no empirical basis here. If they do, a separately qualified normalized native-candidate likelihood becomes a concrete next model control. Native sampling-circle treatment would additionally require genuine receiver lifts and exact physical correction qualification at native times; copying B coefficients into C is insufficient. No further fit is launched or authorized by this report.

Source/protocol commit`68a6b0a32`;6 component/runner tests and Ruff passed. Runtime `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-b-temporal-observation-audit-v1` retains all recorded margins, passing support points, lane gaps, state edges, satellite occupancies, original eligibility and source bindings. Terminal SHA256:053`a3e6bb119701dfe70c1bbb050bbfe698f95c57fc0d19f9f829f3799a6490adba`;059`1218cd942d196fbcf707ae7f12c1af837041bdcaf7241ad10cccaf89d4e0dc95`. Seal SHA256:053`0deed43a85fab603e245a5a3cf9b76bc354959949fb058c97dcefdbb31119863`;059`4b44a7541126a06d699ac2b23e60a95968a1bb1a0e797b09002ee7aa2d5facd5`. Original selections, histogram rows and accuracy claims remain unchanged.
