# Twelve-source-scan prefix test of frozen score-balanced selection

For each dataset take the earliest 12 scans in the existing frozen 24-scan
pool. This is a prefix of that sparse pool, not the first 12 scans of the
entire dataset and not necessarily consecutive acquisition. Use only original
outside-pool targets starting after the last source scan ends (300 seconds
after its start). Freeze membership from timestamps before any new fitting.

Fit the prefix12 with original q020 and six fixed starts (three cold plus
three training-only timing-grid starts). At its fitted source point compute
the same training-only geometry information, observed Hessians and profiled
score gradients. Apply the unchanged score-balanced objective over all 495
eight-of-twelve subsets. No coefficient tuning or geographic reference use.
Require source derivative audits and identical selection with half-step
geometry matrices; preserve failures.

Refit the selected eight with the same six starts. Compare to prefix12 and
the existing six-start earliest-eight fit. Evaluate all three positions on
every eligible later outside scan, integrating one shared timing per scan
under the same original q020 rule. Existing targets are exposed, not blind.
Report all DS7/DS8/DS9 outcomes and prefix selection/scouting cost honestly.

Three workers capped at 300 seconds. Save prefix12 fits before derivative
selection so a later failure does not erase them. No new RF, production edits
or publication. No claim of independent absolute accuracy without surveyed
reference and timing evidence.
