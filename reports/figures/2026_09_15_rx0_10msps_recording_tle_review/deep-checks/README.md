# Covariance-aware audit of three candidate examples

All three checks retain the screen's leading NORAD but recommend abstention:
the radio-polynomial control is not worse on heldout data. These examples were
selected after the screen; they do not estimate an independent success rate.

Each compressed JSON contains the full production-matcher result, including
all candidate scores, chronological heldout diagnostics, ±500 s controls,
radio-polynomial scores, digests, and orbital-only catalogue exclusions.

| Recording | Leading NORAD | Full evidence |
|---|---:|---|
| `scan-hop-24e4b051b0fbc5ca` | 60413 | [Download](scan-hop-24e4b051b0fbc5ca.json.gz) |
| `scan-hop-c2313aebc38416ef` | 63795 | [Download](scan-hop-c2313aebc38416ef.json.gz) |
| `scan-hop-499abcb9ca352397` | 63780 | [Download](scan-hop-499abcb9ca352397.json.gz) |

The candidate population is conditional on the propagatable catalogue subset.
No identity is claimed. The report's simple RMS checks are exploratory and do
not override these stricter abstentions.
