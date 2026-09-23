# Independent read-only protocol review

Reviewed 2026-09-23 after the protocol and execution sources were frozen. This
review inspected only `PROTOCOL.md`, `freeze.json`, `execution_sources.json`,
`baseline.py`, `timing.py`, `evaluate.py`, and `selection.py`, plus the
metadata-only split manifest needed to confirm cohort membership. It did not
inspect validation numerical outcomes, baseline/timing run outputs, result
files, reference-error values, cache evidence, or any final TEST artifact.
No process was started, restarted, interrupted, or modified.

| Reviewed source | SHA-256 |
| --- | --- |
| `baseline.py` | `4498d634e08b0a7ea7c8f3753522118a9a2732b5e258bbf670c4088e995c85d3` |
| `timing.py` | `77959cc1cd59971664620b8a8f58a06b1e21d84c35d088fbed1b24f27310afcb` |
| `evaluate.py` | `8aba159018d02fce15a757ba59a70fc1f18a0ed2ea232c5b64bd3e1c118b466e` |
| `selection.py` | `ccbdb55cfd1ab86ea2ce54a0e2cc40a9032f86259c2ea2dc30c043e141d10277` |
| `PROTOCOL.md` | `705edaba5d23670f77eefc7ab1100321b9541ddb386b87758683c4ab15d243ff` |
| `freeze.json` | `e7e86f3be98ac9bd1c79b0d6b1aa5ed30578caa865daa4b1a1464209fa1d4998` |

Confirmed invariants:

- The frozen cohort contains exactly 124 validation IDs in separate eight-hour
  groups: Sep 22 08Z (44) and Sep 21 08Z (80). It equals manifest validation
  membership and is disjoint from the 151 TRAIN IDs and the closed 64-scan
  TEST group.
- Baseline fitting calls the score with `held=False`, starts each group/view
  from the two frozen priors, and seals 16 group/view/prior searches before
  held rows or reference coordinates are evaluated.
- Timing fits begin from sealed baseline locations and identities, retain the
  original training masks and per-track training-profiled CFOs, and produce
  six timing arms per baseline arm: 96 timing arms in addition to 16 baselines.
- Evaluation is the first code path requesting held metrics or reference
  errors. It constructs exactly seven configurations per group/view/prior and
  asserts 112 total rows.
- Eligibility rejects missing coverage, failures, nonfinite errors,
  out-of-prior coordinates, visibility failures, timing-boundary arms, and
  timing arms that miss their stopping rule.
- Selection averages Sacramento/Reno starts within a group/view, averages 6
  and 16 as the medium regime, weights short/medium/long regimes equally, then
  weights the two groups equally. The 0.010 km tie rule orders baseline, global
  epoch, per-scan epoch, then smaller scale within timing families.

No actionable protocol or implementation defect was found within this limited
source-level review. This conclusion does not validate numerical correctness,
runtime behavior, scientific performance, cache contents, or any validation or
TEST outcome.
