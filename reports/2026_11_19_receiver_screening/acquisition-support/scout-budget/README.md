# Sixteen ranked differential scout centers

Sixteen centers recovered **zero additional capture-era positive records** on the held panel and increased pooled host detector CPU by **21.95%**. The 23 admitted dual-RX visits produced 46 distinct-center lists, each of length 16 with the original four centers in the same order. Native positives fell from 62 to 60. The same 33 of 36 archived positives matched the final detector in both builds, including their raw tracked CFOs. [Sealed qualification](qualification.json) · [Protocol](PROTOCOL.md)

## Release artifacts

| Role | ABI-1 host library | SHA-256 |
| --- | --- | --- |
| Off, four centers and wide CFO band | `/srv/bulk/leo-dev/20261119-scout-budget/control/libleo-adaptive-detector.so` | `db80b772cf9f52941cc0073067816e571308cb43c3096516b77f73ed54986c66` |
| Scout16, wide CFO band | `/srv/bulk/leo-dev/20261119-scout-budget/scout16/libleo-adaptive-detector.so` | `85a62f4867f9959b9cc51edee1acb6c688aaee437c9a82b298f9f538e1d9c682` |

The off artifact is a byte-identical copy of the canonical four-center width build. Scout16 operates only on the 10 MS/s fractional short-window path. The same differential fold and three lag score ranks feed a one-pass local-peak collection, stable radix ranking and the original five-sample circular separation rule. Its ±1-sample coarse neighborhoods admit up to 48 epochs per receiver before the unchanged 21-bin search. The eight final candidate slots, contrast thresholds, CFO paths and controls remain fixed. The ABI exports identical symbol names. Seventeen synthetic entrypoint comparisons produced identical non-timing payloads outside Scout16's scope, including one- and dual-RX short windows at other rates, nonfractional short windows, and 10 MS/s long-dwell scheduler strides of 10, 20 and 120 ms. [Release receipt](release.json) · [Entrypoint checks](compatibility.json)

## Capture-era positives and epoch coverage

The held panel used fresh raw detector calls and one unchanged DS29 capture exclusion. The archive supplied authenticated measurement references after the fresh native receipts were written. The diagnostic scout executable calls the actual private ranker in the release archive. It checks the pinned top-four prefix before emitting ranks. For the archive comparison, an epoch is in scope only when its integer index is in a selected center’s clipped ±1 neighborhood. Final positive matching allows circular frame epoch and symbol-CFO aliases under the original tolerances.

| Recording | Valid visits | Archived positive epochs in neighborhoods, 4 → 16 | Top archived epoch in neighborhoods | Final archived positives matched |
| --- | ---: | ---: | ---: | ---: |
| DS26-0036 | 12 | 17/22 → 17/22 | 6/8 → 6/8 | 19/22 → 19/22 |
| DS29-0082 | 11 | 13/14 → 13/14 | 5/5 → 5/5 | 14/14 → 14/14 |

Three uncovered archive records were two samples from a retained scout center in both builds. One nearer nonselected basin moved from 3,376 to 446 samples away. No selection entered its actual neighborhood. Every valid visit changed some full native fields, while the final set of matched archived positive identities stayed the same. Tracked positives beyond absolute 400 kHz stayed at 20. The held scope measures acquisition recovery and supplies no position estimate or v5 parity result. [DS26 paired receipt](DS26-0036-held.json.gz) · [DS29 paired receipt](DS29-0082-held.json.gz)

## Native cost and controls

| 113 paired warm calls | Four centers → sixteen |
| --- | ---: |
| Pooled detector CPU | 1,617.64 → 1,972.78 ms |
| Median detector CPU | 14.23 → 17.51 ms |
| Pooled coarse CPU | 184.62 → 488.60 ms |
| Pooled proposal ranking CPU | 58.66 → 43.69 ms |
| CPU calls ≤20 ms | 113/113 → 108/113 |
| Wall calls ≤20 ms | 112/113 → 98/113 |

The median detector call consumed 71% → 88% of the visit interval on one pinned host CPU. Timings cover the in-memory native detector and its Python call boundary. Maximum observed CPU rose from 18.35 to 21.23 ms and maximum wall from 20.69 to 96.34 ms. No ARM runtime measurement was made in this panel.

Both builds recovered the signed ±688.125 kHz and weak ±193.45 kHz pilots on each physical receiver. Empty, noise and the amplitude-8 controls emitted no positive records. The added basins displaced weaker secondary pilots in the two simultaneous-pilot controls despite their unchanged primary matches. Secondary matched receiver/edge pairs went from four to one. [Synthetic diagnostics](smoke.json.gz) · [Component source checksums](test-lock.json)
