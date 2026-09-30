# Early-sign redundancy and transfer across visits

This experiment tests whether correlations in early candidate bits yield a
reusable copy, inversion, or parity rule. It reads only existing DS10 paired
caches. These are template-relative real signs, not validated message bits.

## Two fixed tests

1. Apply the public-reference parity rule unchanged:
   `sign(OFDM 3, bin 524) XOR sign(OFDM 3, bin 537) XOR sign(OFDM 5, bin 524) = 1`.
   This is the sole lower-edge rule with zero errors on all 39 held-out reference
   frames in the existing `lower_edge_parity.json`. Reference selection did not
   use DS10. Symbols are physical OFDM indices; bins are native FFT coordinates.
2. Learn simple two-position XOR rules from early-half RX0 frames within DS10.
   Both positions must have 20–80% ones, discovery must have at least 12 frames,
   and at least 90% of discovery frames must satisfy the rule. Test every selected
   rule on later-half RX1 and separately using its first position from RX0 and
   second from RX1. No rule is selected by test performance. Freeze all rules
   and apply them to the other two visits' later-half frames.

The split is the same chronological split used by the header recovery assay.
These evaluation frames have been used in earlier analyses; they are held out
from fitting these rules, not a pristine confirmation dataset. Per-position
marginal bias and all nonzero cyclic shifts of the first constituent provide
descriptive controls. Frames and overlapping rules are dependent; no significance
or FEC claim follows from pooled percentages.

## Public-reference parity

| Visit | Test frames | RX0 satisfaction | RX1 satisfaction |
|---|---:|---:|---:|
| v1085 | 23 | 47.8% | 65.2% |
| v1150 | 9 | 44.4% | 66.7% |
| v1162 | 11 | 36.4% | 36.4% |

This does not validate the reference equation on DS10. For example, v1085 RX1's
65.2% is below its shifted-constituent control mean of 71.1%; its marginal-bias
baseline is 63.1%. The result cannot distinguish changed structure, scrambling,
phase/convention mismatch, or noise. Do not use this equation to correct bits.

## Locally learned pair relations

Only v1085 has enough discovery frames (22); v1150 and v1162 have 9 and 10 and
abstain from local fitting. Seven rules pass discovery on v1085:

| First (symbol, bin) | Second (symbol, bin) | XOR |
|---|---|---:|
| (3, 515) | (3, 520) | 1 |
| (3, 515) | (7, 542) | 0 |
| (3, 524) | (3, 527) | 0 |
| (3, 540) | (5, 549) | 1 |
| (5, 517) | (5, 525) | 0 |
| (5, 517) | (5, 546) | 1 |
| (5, 520) | (7, 546) | 1 |

The search examines all pairs of discovery-variable coordinates in symbols 2–7,
so chance selections are possible. No confidence or parity-success gating is
applied to evaluation. All seven rules are retained in the following averages.

| Test visit | RX1 rule satisfaction | RX1 marginal baseline | Cross-RX satisfaction | Cross-RX marginal baseline |
|---|---:|---:|---:|---:|
| v1085 | 71.4% | 61.0% | 68.9% | 59.0% |
| v1150 | 55.6% | 56.3% | 55.6% | 52.4% |
| v1162 | 53.2% | 50.2% | 49.4% | 48.2% |

Within v1085, the shifted controls average 60.5% for RX1 and 58.6% cross-RX.
The modest same-visit excess motivates local structure analysis but does not
establish a correctable code. Across visits, the excess largely disappears.
v1085 and v1162 are on the same RF channel and their selected centers are
10.5845 seconds apart; all three share the conditional NORAD 63400 association.
Thus even this conditional same-satellite, same-channel revisit does not confirm
a persistent rule set. Satellite association is not a decoded identity and is
not used to tune these equations.

## Consequence

The known T-code is not the only observable structure, but neither this public
parity equation nor these seven local pair rules currently provide a validated
way to correct additional bits. We have not inferred ID, time, position, CRC,
or a message layout. A subsequent decoder should preserve uncertain signs and
test any proposed rule across visits before applying correction. Apparent
within-visit redundancy could arise from limited message diversity, correlated
distortion, or a visit-dependent mapping.

`early_redundancy.py` writes every selected rule, frame index, source digest,
per-receiver statistic and cross-visit transfer to ignored
`local/within-visit/early-redundancy.json`. Two synthetic tests verify copy versus
inversion discovery, constant-position exclusion, and the marginal-bias control.
Both tests and Ruff pass. No existing manifests or sealed analysis files changed.
