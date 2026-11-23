# Partial stereo matching for a coarse Doppler proposal

Matching overlapping Doppler tracks across the two radios changed **none of the four first-ranked probes** relative to independent contrast scoring. On valid North it chose a point **98 m outside** the offered square. Weak DS30-0016 supplied no eligible stereo pairs, and its selected proposal was **13.080 km** from the reference. The rule failed its frozen transfer screen. [Protocol](unordered-doppler-protocol.md) · [Scored receipts](measurements/unordered-doppler-summary.json) · [All blind probe scores and signed assignments](measurements/unordered-doppler.json.gz)

## What was coupled

The prior differential scout scored three offset-invariant contrasts per representative track and abstained on weak, North and dense. The earlier mixture shared receiver nuisance terms and ran a full-data handoff, but its independent track mixtures lost dense owners. The geographic mixture keeps the full physical evidence for its regional decision, while the adaptive grid changes only which map points are published. This experiment keeps every active curved track with at least six points and compares two costs on the same catalogue, measurements and coarse locations. [Earlier arc scout](arc-doppler-start.md) · [Mixture handoff](mixture-joint-start.md) · [Regional score maps](geographic-peak.md) · [Adaptive publication grid](adaptive-grid.md)

Each of three disjoint temporal differences uses the original RF and radio noise at both sample indices. Nominal causal Doppler, phase tangent and all six horizon signs are evaluated at the actual times on every probe. The candidate pairs arcs only across radios on the same channel and actual RF with at least two common times. It scores both against one satellite and one clipped phase before deciding whether both individual contrast costs clear the cap. A minimum-cost bipartite matching selects the nonoverlapping stereo pairings that reduce the separate track costs. Tracks may remain independent or unmatched, and a spacecraft may recur on other channels or times. Each track keeps its own signed integer lift. The original full-observation position solver and withholding decisions remained untouched. [Scoring and pairing](unordered_doppler.py)

## Blind rank after reference scoring

Positive exterior gain favors the exterior. Loss and gain use the same fixed denominator of all sampled arcs.

| Original offer | Curved arcs / eligible stereo pairs | Top point, east / north km | Top error km | Independent → joint exterior gain | Side of top point, both scores |
|---|---:|---:|---:|---:|---|
| Weak DS30-0016 containing | 3 / 0 | −6.250 / 0.000 | 13.080 | −0.44964 → −0.44964 | Inside |
| North containing, +100 m | 13 / 5 | −12.598 / 0.000 | 0.197 | +0.00839 → +0.00714 | Exterior |
| North near omission, −100 m | 13 / 5 | −12.598 / 0.000 | 0.002 | +0.01327 → +0.00998 | Exterior |
| North far omission, −52.5 km | 13 / 5 | −62.500 / 0.000 | 2.497 | +6.03362 → +6.92643 | Exterior |

All three North offers used the same signed receiver document, original causal cutoff and 1,569 orbits. The winning probes paired five of five eligible stereo edges, with all 13 arcs matched. Joint scoring lowered North containing loss from **15.817 to 10.131** per arc. Most of this reduction came from charging one orbit nomination per stereo pair. The same exterior minimum remained. The rest of the rank order changed, so identical winners do not imply identical spatial score surfaces. On weak, the three active arcs supplying this test came from one receiver. With no valid edges the full 33-point rank order agrees exactly. [Sealed probe costs and support](measurements/unordered-doppler.json.gz)

Both methods match **2 of 3** original cold satellite-and-alias assignments on the weak top proposal and **10 of 13** on North containing. This is recall against the existing full-data cold winner, at the new coarse points. Neither matched the complete assignment. Both scores are proposals. No fitted position, paired calibration ablation or new omission verdict was produced, and the geographic scorer read the references only after all four independent receipts were sealed. [Archived cold controls](measurements/arc-doppler-start.json.gz) · [Separate post-seal scorer](unordered_doppler_score.py)

## Charged cost

| Offer | Common graph and causal preparation CPU s | Sampled projection CPU s | Extra stereo matching CPU s | Complete scout CPU s |
|---|---:|---:|---:|---:|
| Weak | 1.829 | 0.035 | 0.00011 | 0.059 |
| North containing | 2.044 | 0.101 | 0.00476 | 0.179 |
| North near omission | 2.038 | 0.100 | 0.00473 | 0.175 |
| North far omission | 1.939 | 0.100 | 0.00444 | 0.171 |

Sample setup and scoring are inside the complete scout clock. Common preparation remains necessary in both models. On the two containing offers with archived same-input cold clocks, unqualified proposals leave the original work in the bill. Adding the measured scout to the original cold route gives **0.266 versus 0.207 CPU s** on weak and **0.565 versus 0.386 s** on North, assuming common Graph and catalogue preparation. The earlier same-input North exact assignment rebuild and both fixed-point scores consumed another **0.041 CPU s** when deliberately invoked. Neither missing offer has a matched stage-only cold clock in this comparison. The far offer's original withholding path stops before cold scoring, so the forced diagnostic supplies no operational saving there. [Original cost and rebuild scopes](arc-doppler-start.md) · [Published omissions](north-causal-transfer.md)

The four retained probe runs used one low-priority Gauss core and one numerical thread. One setup attempt reached prepared tracks and stopped before projection because saved track times were lists. The runner converts to the released array representation before the curvature gate. Nine focused tests passed. No waveform was opened and no position optimizer ran. [Regression tests](../../../tests/pipeline_eval/test_unordered_doppler.py)

To reproduce, use the original released payload first in the research worker's environment. Under the shared Gauss lock, CPU 2, nice 15 and I/O priority 7, run `unordered_doppler_trial.py CASE OUTPUT` in a fresh process for `weak`, `north-containing`, `north-near` and `north-far`. Set the report directory, installed ALGO08v3 payload, release `src`, release root and research root on `PYTHONPATH` in that order. Use the released interpreter, archive-readable account and a new output directory on tmpfs. Then use `unordered_doppler_score.py DIRECTORY NEW_SUMMARY NEW_FULL` with the report directory and checkout sources on `PYTHONPATH`. [Trial bindings](unordered_doppler_trial.py)
