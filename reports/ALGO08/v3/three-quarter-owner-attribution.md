# What the fixed member omissions changed in DS30-0220

The three-of-four schedule moved the DS30-0220 endpoint **4.956 km at `c0` and 4.867 km at fitted `c`** from the ordinary saved 20/8 ms endpoints. Removing signed members physically deleted 488 ordinary owners per arm. Of the 1,473 ordinary owners whose native detections survived, 149 lost their assignments and 1,324 kept the same satellite. The sampled solution claimed 279 additional retained detections. Every retained observation assigned by both publications kept its satellite. This is an accounting of the two fits. Neither publication evaluated the retained factors under the ordinary fixed assignments and nuisance state, so the observations cannot apportion the endpoint movement between missing detections and the resulting changes in association and fit.

## Join to signed omissions

Owner IDs were reconstructed from the original session, radio slot and valid start counter. Each joined lane used the exact signed member span, including short tails. The saved sampled native rows matched every original retained row, along with their original delivery clocks, inventory and recording authority. The ordinary and sampled owner maps independently reproduced the published digests. Within each of the four publications, `c0` and fitted `c` assigned exactly the same observation IDs to the same NORADs.

| Recording | Ordinary → sampled owners | Physically removed ordinary owners | Retained, same NORAD | Retained, different NORAD | Retained, lost owner | Retained, gained owner |
|---|---:|---:|---:|---:|---:|---:|
| DS30-0086 | 2,095 → 1,521 | 507 | 1,465 | 2 | 121 | 54 |
| DS30-0220 | 1,961 → 1,603 | 488 | 1,324 | 0 | 149 | 279 |

DS30-0220 physically lost 908 of its 3,700 selected native detections, including 420 that had no ordinary owner. Its retained assignment changes covered 428 of 2,792 positive lanes (15.3%). DS30-0086 physically lost 898 of 3,671 native detections, including 391 without an ordinary owner. Its retained assignment changes covered 177 of 2,773 positive lanes (6.4%).

- **DS30-0220.** NORAD 62440 lost 13 owners to physical omissions and all 52 of its surviving assignments. NORAD 56382 lost 4 physically and all 10 surviving assignments. NORADs 69358, 61585 and 69367 took 179 of the 279 new assignments. The 488 deleted ordinary owners were distributed across 14 segments, led by segment 00 (58) and segment 11 (52). Segments 03 and 09 accounted for 67 of the 149 retained losses. Segments 09 and 02 accounted for 86 of the 279 new assignments. The terminal satellite count rose from 21 to 23 and the track count fell from 60 to 56.
- **DS30-0086.** NORADs 68747 and 66968 account for 56 of the 121 surviving detections that lost an owner. NORADs 67649 and 64418 account for 49 of the 54 new assignments. Both direct switches were 64418 to 69562 in segment 08. The terminal satellite count fell from 28 to 27 and the track count fell from 67 to 51.

## Where the DS30-0220 solutions separated

The sealed lean-route witness preserves all three cold finalists from each local ranking and all three completed fits. The admitted graph changed from 75 to 64 tracks. The ranked nominee count changed from six to five, and each finalist contained 59 ordinary or 53 sampled seed tracks. Both runs marked the five-evaluation prefix scores ambiguous and completed all three contenders. The winning rank was 1 within each run. Each list and objective used its own track inputs, so ranks and score levels cannot establish equivalent hypotheses across the two runs.

The sampled contenders were **1.078–1.305 km** from the ordinary published `c0` endpoint after the five-evaluation prefix. All three were already **4.612–5.167 km** away after the cold fits completed, before curved support was reconsidered and the final two-arm position fits ran. The first recorded points of the published ordinary and sampled fits were 4.612 km apart at `c0` and 4.662 km apart at fitted `c`. The two DS30-0086 paths began at the same origin.

NORAD 62440 appeared in all three ordinary and sampled finalists. Each winning seed had three of its component labels with the same alias. Within each run, all three components passed the first curved support gate. The sampled run dropped all three at the curved support recheck after salvage, while the ordinary run kept all three through that recheck. NORAD 56382 appeared in each ordinary finalist and was absent from the three recorded sampled finalists. The witness archives only those finalists out of the five sampled ranked nodes, so an earlier decision for 56382 is unresolved. The ordinary initial paired finish required one successful repair. The sampled pair passed its initial finish. The cold endpoint movement preceded that difference.

## Position and RF fit

All four saved endpoints per recording matched the terminal, objective grid and accepted fit path. Each endpoint grid score reproduced its own archived fit objective exactly. The objective values carry their own observation and nuisance model and are shown for verification. The terminal RF RMS and horizontal error measure separate outcomes.

| Recording | Arm | Endpoint movement | Horizontal error installed / ordinary / sampled | Terminal RF RMS ordinary → sampled | Endpoint objective ordinary → sampled |
|---|---|---:|---:|---:|---:|
| DS30-0086 | `c0` | 0.138 km | 0.402 / 0.371 / 0.330 km | 179.824 → 159.770 Hz | 16,566.981 → 11,518.155 |
| DS30-0086 | fitted `c` | 0.187 km | 0.410 / 0.382 / 0.335 km | 180.081 → 159.898 Hz | 16,570.066 → 11,525.397 |
| DS30-0220 | `c0` | 4.956 km | 0.318 / 1.412 / 5.491 km | 159.782 → 167.547 Hz | 20,417.145 → 15,880.578 |
| DS30-0220 | fitted `c` | 4.867 km | 0.369 / 1.371 / 5.329 km | 159.682 → 167.474 Hz | 20,423.348 → 15,887.714 |

The comparable deletion counts in the two recordings and different outcomes leave no supported fixed replacement schedule. The loss of 62440 at the recheck also leaves the earlier spatial divergence unexplained. The diagnostic used only saved receipts, with no new fit or waveform read. DS30-0144 remained held out.

[Reproducible ownership and seed readout](three_quarter_owner_attribution.py) · [Sealed diagnostic data](measurements/three-quarter-owner-attribution.json.gz) · [DS30-0086 development receipt](three-quarter-members.md) · [DS30-0220 challenge receipt](three-quarter-challenge.md)
