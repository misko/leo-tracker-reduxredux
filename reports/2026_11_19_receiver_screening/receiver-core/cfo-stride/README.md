# Four-region CFO stride in the wide ordinary detector

The strided bank evaluated **39.0% fewer physical coarse cells** on eight traced receiver rows. All 1,230 evaluated scores were bit-identical to their full-bank counterparts. On 22 held visits, both detectors matched the same **23 archived positive records**, including their raw tracked CFOs. Striding increased regional coarse CPU by **21.1%** and whole detector CPU by **0.98%** on this host. [Qualification](qualification.json) · [Frozen protocol](PROTOCOL.md)

## Release and boundaries

| Role | ABI-1 local ext4 library | SHA-256 |
| --- | --- | --- |
| Original 21-bin coarse bank | `/var/tmp/leo-scout-stride-20261119/control/libleo-adaptive-detector.so` | `db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66` |
| 11 even bins plus bounded native repair | `/var/tmp/leo-scout-stride-20261119/stride/libleo-adaptive-detector.so` | `68876717e4fe51b9aef99d737d771709f95f5eba1fb2b5fd977f96b2892e9b17` |

The original artifact is byte-identical to the canonical prepared-fractional wide release. The opt-in release uses the original four ±1-sample scout neighborhoods on 10 MS/s dual-RX fractional short windows. It evaluates eleven uniformly spaced physical centers across the full ±800 kHz span and uses native scores to restore the immediate 80 kHz neighbors of each region’s strongest even bin. A region can restore one neighbor at the band edge or two in the interior. The original ranking, candidate capacity, fine estimator, gates and fractional confirmation consume the resulting slate. The opaque workspace reserves 51,840 bytes for the packed even templates. The shared object increases by 4,096 bytes with the same ABI symbol names. Seven outside-scope entrypoints kept their exact original payloads, including other rates, single RX, nonfractional and long-dwell paths. [Release receipt](release.json) · [Compatibility](compatibility.json)

The eight measured engineering receiver rows went from 252 coarse cells each to 150–156. Of the resulting 1,230 evaluated cells, 174 were repaired odd bins and the remaining 1,056 were even bins. All uncomputed physical cells stayed outside peak ranking. The instrumented builds reproduced the public payloads of both release builds on all four engineering visits. [Full coarse-grid traces](grid-traces.json.gz)

## Held visits and native cost

The two locked recordings provided 22 admitted visits out of 24 scheduled, with both exclusions on DS29-0082. On DS26-0036, the detector matched all 21 archived positive records. On DS29-0082, it matched both archived records. Each detector emitted 352 native candidates and 46 positive records, with all 22 complete slates changing. DS26 positive records changed 42→41 and DS29 changed 4→5. The full receipts preserve candidates, ranks, scores and changed votes. [DS26 held receipt](DS26-0036-held.json.gz) · [DS29 held receipt](DS29-0082-held.json.gz)

| 108 paired warm calls | Full → strided |
| --- | ---: |
| Pooled detector CPU | 1,583.68 → 1,599.25 ms |
| Pooled coarse CPU | 186.64 → 225.97 ms |
| Median detector CPU | 14.41 → 14.52 ms |
| Median detector wall | 16.36 → 17.08 ms |
| Calls ≤20 ms CPU | 105/108 → 105/108 |
| Calls ≤20 ms wall | 84/108 → 80/108 |

The released repair loop revisits each selected odd bin’s original anchor support and recomputes received-energy normalization. The complete original loop shares that normalization across its vector bank. The smaller cell count did not yield a CPU gain with this implementation. Timings are for interchangeable contexts on one shared x86 host core. Embedded timing and geography are measured separately.

## Signed, weak and alias controls

Both releases retained receiver-level target matches on all strong signed odd, even and edge controls and on the faint intermediate-frequency controls. For the −720 kHz upper-edge plant the first receiver had three matching candidate records with stride, down from four. Both receivers still detected the target. The two same-epoch pilots separated by 160 kHz both matched on the lower edge. On the upper edge, both releases missed the weaker second plant. The two-epoch symbol-alias control retained the same matched records on both edges. Empty and seeded noise emitted zero positives. [Complete control payloads](smoke.json.gz) · [Evidence seal](prediction-lock.json)
