# Portable v5 with a competing outside region

The competing-region gate withheld both historical omitted offers and the fresh omitted offer in 33.7–34.0 s. The first gate had published both historical wrong offers. The new gate also withheld the historical Site 1 and fresh containing offers in 35–36 s. Historical Site 2's containing offer reached the 195-second cap. The method published no positions, so neither zero calibration nor fitted calibration produced a measured location error or conditional fit RMS. [Protocol](PROTOCOL.md) · [Source lock](source-lock.json) · [Sealed scores](scores.json)

| Query | Inside / outside held Doppler score | Outcome, both calibration arms |
|---|---:|---|
| Historical Site 1, containing | 74.0 / 79.1 | Withheld |
| Historical Site 1, omitted | 43.9 / 74.0 | Withheld |
| Historical Site 2, containing | — | Timed out |
| Historical Site 2, omitted | 39.1 / 65.7 | Withheld |
| Fresh site, containing | 73.9 / 79.5 | Withheld |
| Fresh site, omitted | 45.0 / 79.8 | Withheld |
| Fresh shuffle | — | Withheld |

The strongest outside alternatives at the two containing offers that finished scoring were 15–19 km from the inside estimates. The held score collapsed votes by proposed satellite. Different candidate identities can therefore get two votes on overlapping observations of the same physical arc. The small score increases on containing queries do not establish a better outside position. The larger score separation on omitted queries supports their rejection under this rule. Its observed containing coverage was zero. [Historical predictions](historical.jsonl.gz) · [Fresh predictions](fresh.jsonl.gz)
