# Receiver agreement beyond the offered square

Use the saved all-track causal catalogue score at every original probe. Keep the original inside and exterior sets, visibility screen, track mixture, phase prior, and observation denominators. Each of the two receiver groups chooses its own highest-scoring exterior point from all 48 exterior probes, including those near a face. It compares that score with its own highest-scoring point among the 48 inside probes. Use the receiver scores directly. [Existing all-track score](regional-reassignment.md)

For an offered square of width `W`, issue a veto only if every condition holds.

- Each receiver has a unique exterior maximum with a strictly higher score than its best inside probe.
- Both exterior maxima are at least `W` beyond the square by face clearance. For local coordinates `(east, north)`, use `max(abs(east), abs(north)) − W / 2`.
- The two exterior maxima lie within `W` of one another in the local horizontal plane, using Euclidean distance.

The clearance and agreement bounds include equality. Missing or nonfinite scores, incomplete geometry, absent receiver partitions, and exterior ties do not veto. The rule uses the same dimensionless geometry and the same score sign for every offered region. It ignores the pooled score, the production endpoints, the surveyed receiver position, and labels for the offer category. The track contrasts cancel any constant contribution from `c` on a fixed RF, so a veto would apply to both calibration arms. The audit will score the resulting decisions against the public offer categories after applying the rule.

Compute the rule for the original centered, near-edge containing, 1.5 km omitted, and far omitted offers at both public simulated sites, plus the two mirrored 100 m omissions. The mirrored inside rows repeat the original containing boundary probes. Verify their agreement before counting either copy. Use the existing packet of saved scores for each offer. No new region, recording, orbit fit, solver run, or probe is part of this test.

| Input archive | SHA-256 |
|---|---|
| [Original eight offers](measurements/regional-reassignment.json.gz) | `735553ef3b9287884f6473bfc78bd8740e45c23927c79c56d95b0ba53376bb4a` |
| [Mirrored offers](measurements/region-mirrors.json.gz) | `ee8f80ec6267e7fe333d05ac794775fb54bc349cd143022a55599bf2f9af4728` |

Report each receiver's exterior gain and face clearance, the distance between exterior maxima, the veto decision, and whether the offer contains the receiver. Report the incremental CPU of the rule on saved points separately from the cost of obtaining the all-track probes. The existing observations are public development evidence from two locations and have informed earlier tests. This audit estimates neither false-veto frequency at fresh locations nor unknown-site transfer.
