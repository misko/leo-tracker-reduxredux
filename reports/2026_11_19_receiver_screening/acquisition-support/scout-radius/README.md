# Four scout centers with a two-sample radius

Radius two admitted the integer epochs of three additional archived positive records and advanced all three through native confirmation. Their adjacent-seed fractional matches were already present with radius one. Both builds matched the same **33 of 36** archived positive identities, and native positives changed from 62 to 58. Pooled host detector CPU rose **3.34%** on 113 warm calls. [Sealed qualification](qualification.json) · [Protocol](PROTOCOL.md)

## Released artifacts

| Role | ABI-1 library | SHA-256 |
| --- | --- | --- |
| Four centers, radius one | `/srv/bulk/leo-dev/20261119-scout-radius/control/libleo-adaptive-detector.so` | `db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66` |
| Four centers, radius two | `/srv/bulk/leo-dev/20261119-scout-radius/radius2/libleo-adaptive-detector.so` | `41e5660c4fbc11a2ff5ee67d4dcb8d695567705d85265e15884083d2c72ae399` |

The only native source change is the local support radius at the 10 MS/s wide fractional dual-RX short entrypoint. The four original scout centers, clipping at the frame boundary, 21 CFO bins, eight retained slots, ranking, gates and confirmation remain as in the release. Both libraries expose identical public symbol names, and the radius-one artifact is byte-identical to the canonical wide build. Outside the tested scope, both outputs matched for single-RX fractional, dual nonfractional, lower-rate and long-dwell paths. [Release receipt](release.json) · [Compatibility](compatibility.json)

## What reached final output

The pair processed 23 of 24 fixed saved-IQ visits with one unchanged DS29 exclusion. Every admitted call matched its previously sealed raw digest and radius-one output. Fresh candidate slates were written before joining the capture-era references. Neighborhood coverage changed **30/36 → 33/36**, and top-ranked positive coverage changed **11/13 → 12/13**. The three genuine original misses remained outside both neighborhoods. All 33 final archive matches remain within 1 kHz in raw CFO under the existing epoch match. [DS26 held slate](DS26-0036-held.json.gz) · [DS29 held slate](DS29-0082-held.json.gz)

| Visit and RX | Archived positive ranks | Old → new integer seed | Old → new native ranks | New local peaks and limit |
| --- | --- | --- | --- | --- |
| DS26-0036, 2570, RX1 | 0 and 1 | 5274 → 5275 | 0 and 2 → 0 and 1 | 14 local peaks at 5275. Three retained, eleven beyond the eight-slot rank limit. |
| DS29-0082, 2570, RX1 | 4 | 12463 → 12464 | 3 → 3 | Nine local peaks at 12464. Two retained, seven beyond the eight-slot rank limit. |

The selected DS26 CFO centers were +400, +480 and +240 kHz. The two matching archived positives used the first two centers. DS29 retained +320 and +400 kHz; its archived positive used +320 kHz. The selected target-epoch peaks passed the original gate. The new seeds shifted the matched tracked CFOs by about +10.6 Hz on DS26 and +6.6 Hz on DS29. Exact diagnostic traces reproduced both measured candidate slates through the same native shared-library call. [Coarse score and rank trace](coarse-traces.json)

Both builds detected the original weak and signed high-CFO pilots on all four receiver-by-edge checks. Empty, noise and amplitude-eight controls yielded zero positive votes. In the lower-edge two-pilot control, one receiver retained one matching secondary vote where radius one emitted two. The upper-edge two-pilot hits matched. [Synthetic paired candidates](smoke.json.gz)

## Per-receiver work and timing

The four neighborhoods covered 12 → 20 integer epochs in all 46 admitted receiver rows, or 252 → 420 physical CFO-epoch cells before the coarse score aggregation. Each matched timing used the same in-memory saved CI16 with alternating builds. The first XFS scratch attempt blocked before a held receipt and was superseded by the same frozen evaluation with local scratch. Host load average was approximately 63 at the local replay opening. Wall observations include that scheduler load.

| 113 matched warm calls | Radius one → radius two |
| --- | ---: |
| Pooled detector CPU | 1,506.08 → 1,556.32 ms |
| Pooled regional coarse CPU | 157.00 → 202.44 ms |
| Median detector CPU | 13.33 → 13.42 ms |
| Median detector wall | 13.50 → 13.59 ms |
| Calls ≤20 ms CPU | 113/113 → 113/113 |
| Calls ≤20 ms wall | 112/113 → 113/113 |

This panel measures the native detector only. Geographic effects of the changed slates require the separate whole-IQ replay. [Evidence seal](prediction-lock.json)
