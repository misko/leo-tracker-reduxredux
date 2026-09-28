# Complete the frozen DS8/DS9 chronological baseline panels

Continue the exact 16-row plan sealed in ../2026_09_28_ds89_baseline_transfer.
Reuse DS8-001 and DS9-001 without rerunning them. Export and fit ordinals 002–008
for each dataset, in order, with no replacements or outcome-based selection.
The original baseline, analysis-version rules and post-seal geographic metric
remain unchanged. This continuation does not alter the preflight evidence.

Use two concurrent workers, one per dataset, each sequential internally and
limited to 1,200 seconds total. Each observation export is capped at 60 seconds,
bank export at 120 seconds, input validation at 30 seconds and baseline fit at
180 seconds, shortened if the worker deadline requires it. Each numerical child
uses one thread, nice19 and at most 4 GiB. Preserve partial files, timeouts,
unavailable inputs and failed fits; no retries, replacements or cap extensions.
Any rows not reached by the deadline remain explicitly pending.

Read existing public tracking/TLE ports from the same pinned installed release.
Freeze actual analysis and candidate-bank bytes before each fit. DS9 mint-time
GLRT metrics are compared with current export hashes without conflating the
API-evidence-file digest with the metrics-manifest digest. No new RF or IQ
processing; source stores remain read-only. Candidate propagation is bounded.

Use the unchanged DS7 fast baseline and the preflight numerical configuration:
Student-t(4,100 Hz), stationary offsets, five-anchor top-eight candidate union,
three timing starts, original bounds and optimizer tolerances. No free slope
or new spatial prior. Qualification remains convergence and no boundary.
Seal every record's fit inputs/outputs before geographic scoring.

Primary output is two eight-record individual-position distributions, including
the two preflight records. Report qualified and all-returned outcomes, below-1km
counts with all eight attempts as denominators, starts, failures and held scores.
Eight-record joint fits are a subsequent, separately bounded observation budget;
do not substitute individual averages for a joint likelihood fit. All records
come from an exposed, unsurveyed site and do not demonstrate new-site performance.
