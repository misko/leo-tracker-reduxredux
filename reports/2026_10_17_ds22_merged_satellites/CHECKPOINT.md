# Active goal checkpoint

Objective: iterate and implement satellite association over the new track
approaches; evaluate DS22 associations and position error; get below 0.5 km and
perform well on DSX01 using track merging to simplify satellite matching.

This turn made progress. The goal is active, not achieved or blocked.

- All 68 available sealed DS22 fast inputs ran Graph plus curved-only trimmed
  merging: 216,039 / 243,085 gated winning points, 7,120 Graph fragments and
  6,123 polynomial components. The full 137-member denominator is preserved.
- All 68 available fast recordings and all five frozen DSX01 scans completed
  eight fixed-site association arms: fragments/hard components × c0/fitted-c ×
  zero/1,000-Hz Gaussian component bias. No failures were hidden. Candidate
  labels have no independent identity ground truth.
- Hard pre-merging loses candidate coverage. Identity-guided consolidation
  retains every admitted point and reduces candidate groups. For fitted-c,
  DS22 retains 25,371 points and 1,251→1,132 groups; DSX01 retains 3,621 points
  and 194→166 groups. Each accepted join has one identity, one native constant
  bias, a score improvement and complete residual checks. Failed joins retain
  both fragments. No linear fragment calibrates receiver hardware.
- Four cold regional position pilots on the first DS22 recording completed.
  Hardware-only c0/fitted-c errors are 146.440/146.682 km. The component-bias
  pair both gives 147.803 km. Search never receives the evaluation GPS; the
  endpoint freezes before error evaluation. Discovery uses real time-spread
  subsets, then four full-data finalists. These are bounded experiments, not
  globally or locally certified optima. The initial full-row attempt exceeded
  its compute allocation and is preserved separately.
- 68 adaptive recordings need an observation adapter; one fast recording has
  no pinned tracking export. Their observation counts and position errors are
  not known. They are not counted as successes or silently removed.
- 41 targeted tests passed, including existing Graph and DSX01 calibration
  guards. New-source static checks passed. Artifact hashes, native observation
  ownership, preserved candidate identities, and causal TLE cutoffs were
  independently checked. No scientific job remains running at this checkpoint.

The 0.5-km requirement is contradicted by the pilot errors and unverified for
the remaining population. Neither a count gain nor a passing component test is
completion evidence. DSX01 has no new unknown-site position result here.

Next investigate the geographic objective and identity ambiguity, rather than
raising residual gates. A physically RF-proportional component frequency bias
is a distinct hypothesis from the current native-Hz bias; its hardware/
transmitter gauge and zero-mean prior must be explicit. Test it with matched
c0/fitted-c arms and unchanged points/candidates/budgets. Use the safer
association/consolidation path in geographic discovery instead of treating old
polynomial components as unconditional single-satellite constraints. Causal
orbital timing error, receiver UTC brackets and nominal tuner correction also
need qualification. Any shared-site experiment must state the fixed-installation
assumption and retain scan-local hardware calibration.

Large orbit matrices are hash-bound caches under `/tmp/ds22-merged-orbits-*`;
selected TLE text is frozen in `orbit_elements`. Code snapshots, original point
memberships, case executions, endpoint traces and the complete report are local
to this directory. No production model was promoted in this iteration.
