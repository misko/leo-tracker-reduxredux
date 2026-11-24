# Do changes in the assigned satellite set explain the next DS30 errors?

The seven held pairs all fixed in both calibration arms and stayed within 2 km under both methods. The candidate gained 1 km coverage on **DS30-0067 and DS30-0323** in both arms and lost it on **DS30-0413** with fitted `c` only. Five of seven held pairs provably changed assigned satellite sets. The other two have equal satellite counts and distinct observation-to-NORAD digests, which leaves set equality unresolved. The satellite-count metric did not predict geographic error in either cohort. [Frozen protocol](satellite-set-transfer-protocol.md) · [First-30 sealed readout](measurements/satellite-set-first30.json) · [Held-seven readout](measurements/satellite-set-held7.json).

## Held recordings #31–37

All values compare the original installed full-20-ms publication with the charted mixed-20/8-ms publication on the same signed recording and offer. The native match fraction uses installed short-lane positives as denominator and mutually unique peaks within ±250 signed Hz and ±2 samples as numerator. The other diagnostics use assigned rows and cardinalities, without fitted RF residuals.

| Recording | Error `c = 0`, m | Error fitted `c`, m | Assigned NORAD count in either arm | Installed short peaks matched |
| --- | ---: | ---: | ---: | ---: |
| DS30-0067 | 1,053 → 264 | 1,038 → 317 | 22 → 22, unresolved | 65.5% |
| DS30-0413 | 1,146 → 1,290 | 939 → 1,014 | 24 → 25, changed | 72.5% |
| DS30-0333 | 1,490 → 1,821 | 1,522 → 1,681 | 24 → 24, unresolved | 67.0% |
| DS30-0430 | 436 → 738 | 518 → 762 | 25 → 29, changed | 68.7% |
| DS30-0299 | 597 → 763 | 426 → 628 | 21 → 16, changed | 77.6% |
| DS30-0323 | 1,191 → 654 | 1,227 → 847 | 27 → 26, changed | 63.6% |
| DS30-0434 | 1,475 → 1,237 | 1,440 → 1,249 | 21 → 25, changed | 67.3% |

Held 1 km coverage moved from **2/7 to 4/7** at fixed zero and **3/7 to 4/7** with fitted `c`. All seven mixed packets gained native positives but assigned fewer observations. On the first held gain, DS30-0067, both 22-satellite outputs used different observation maps and the actual endpoints moved 882 / 950 m. The installed rows are unavailable to determine whether those 22 NORADs match. The other gain, DS30-0323, occurred with one fewer satellite. The held fitted-only coverage loss on DS30-0413 occurred with one more. Both DS30-0430 and DS30-0434 gained four assigned satellites, but their errors moved in opposite directions. Count differences establish at least one change in the set. They leave every same-count identity comparison and individual entry or exit unresolved.

## What transferred

The predeclared primary metric is the installed assigned distinct-satellite count minus the candidate count. A positive Kendall tau-b would support using a count loss to predict worsening. Each calibration arm was scored separately against its own candidate-minus-installed horizontal error. The ownership-share metric uses assigned observations divided by native positives in each publication. The effective count uses inverse squared satellite shares among the charted owners, and fewer effective satellites are the proposed risk.

| Predictor vs error excess | First 30, fixed / fitted | Held seven, fixed / fitted |
| --- | ---: | ---: |
| Loss of assigned satellite count | +0.033 / +0.013 | −0.050 / −0.050 |
| Loss of assigned share of native positives | +0.089 / +0.083 | +0.143 / +0.143 |
| Fewer effective candidate satellites | +0.262 / +0.218 | −0.238 / −0.238 |

Of the first 30, 26 shared fixes per arm supply comparison data. There are 23 proven satellite-set changes, one proven same set and two unresolved sets. The four other pairs contribute their observed coverage outcomes. Only three shared fixes have both exact satellite rosters after binding the previously saved owner evidence. Among them, DS30-0086 dropped one NORAD and added two while improving both arms. DS30-0220 dropped five and added two while worsening both by more than 1 km. DS30-0049 retained the **same exact two NORADs** and regressed **2.646 / 2.620 km**. Its stock/mixed crossover independently reproduces the error change when only the signed receiver packet changes, under either solver. Preserving only the assigned satellite names therefore fails even on an exact observed same-set control. [0049 exact crossover](ds30-0049-saved-crossover.md) · [0086 and 0220 installed-map readbacks](field-installed-packet-saved.md).

The original installed manifests persist counts and owner-map hashes for all these fixes. They omit the full held installed maps, while the charted witnesses retain hash-verified owner rows for every held fix. The group comparison cannot establish which changed native peaks survived into the held installed assignments, or whether a preserved NORAD kept the same time, receiver and role support. The useful quality comparison is to preserve or independently check the original signed observations and their assigned rows under the same calibration policy. A bounded future crossover could record both selected owner maps as research sidecars from the same release entry and compare observation identity, NORAD and role before interpreting the geographic change. The held findings do not support rerouting on satellite count or adopting the candidate-only concentration score.

The earlier second-screen study measures discarded conditional points. The start/end and anchor-arrival studies measure temporal support and selection. This readout measures the actual final assignment cardinalities and wherever available the exact assigned sets. No spatial fit or new release was run. The first-30 result was sealed in commit `d2651df10` before opening held outcomes. Four component tests passed. [Second-screen attrition](ds30-second-screen-attrition.md) · [Track boundaries](track-boundary-membership.md) · [Anchor arrival](anchor-arrival-authority.md).
