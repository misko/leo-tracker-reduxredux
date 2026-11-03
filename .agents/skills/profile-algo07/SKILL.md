---
name: profile-algo07
description: Profile and accelerate the standard fast-scan ALGO07 pipeline while checking frozen scientific results. Use for runtime bottlenecks, queue throughput, exact numerical optimization, and performance regression checks in this repository.
---

# Profile ALGO07

Use the repository CLI `python -m leo.cli.algo07_profile`. Read
[the benchmark protocol](../../../docs/operations/algo07-runtime-benchmark.md)
before freezing a baseline or interpreting a speedup.

For numerical replays, `tools/profile_algo07_numerics.py snapshot` obtains a
prepared input through the public evidence port, relocates and freezes it;
`run --mode capture` records real likelihood tensors, while `run --mode replay`
executes the full guarded ALGO07 worker over those prepared inputs. Compare
intermediate screens and optimizer histories with
`tools/compare_algo07_runtime_replays.py`. Historical research reconstruction
uses the separate `profile_algo07_research_snapshot.py` adapter and must not be
reported as a public-terminal or whole-pipeline replay. Concurrent trials' read
audits must be separated by recorded process ancestry.

Use `tools/profile_algo07_glrt.py` for bounded native-GLRT fixtures. Select the
actual installed native worker root: the research checkout's older fast-scan
adapter may accept only 2.5 MS/s, while production processes 10 MS/s. Snapshot
whole paired-receiver windows using a recorded random seed within each channel,
freeze their verified IQ and implementation bytes, and compare every published
candidate field. These small fixtures locate hotspots; they do not establish a
whole-scan or position speedup.

The production chain includes GLRT, ALGO02 graph localization, then ALGO03–07
recovery stages. Improving only the final reassociation worker is not an
end-to-end speedup. Separate active computation, discovery/validation overhead,
queue delay, and acquisition duration. Attribute child-worker time separately:
a parent cProfile file does not profile its children.

Before an optimization, freeze input and reference-output hashes with `freeze`
and verify them with `verify`. Include both c=0 and fitted-c, accepted recovery,
rejection/fallback, slow cases, and unavailable cases. Keep causal TLE versions,
native observations/owners, priors, phase quadrature, initial positions, solver
budgets, and acceptance gates matched. Evaluation GPS is for reporting only.

Choose the next change from measured profiles. Prefer eliminating repeated
work or exact algebraic improvements. A smaller candidate set, coarser phase
grid, relaxed acceptance gate, different prior, or earlier timeout is a change
of algorithm, not a runtime-only improvement. Do not update reference results
to make a changed result pass.

Run component-owned tests, then matched baseline/candidate replays. Compare
native owner maps, selected satellites, both endpoints and frequency objectives,
gate decisions, convergence, and fallback reasons. Record numerical tolerances
before the candidate run; investigate any difference that changes a decision.
Passing a saved-result audit is not equivalent to rerunning numerical inference.

Use bounded runs over existing recordings and isolated output directories.
Production reads go through public storage/export ports. Preserve validation
when new results are consumed; an optimization must still detect changed or
corrupt inputs. Never write beneath `/mnt/qnap01` or benchmark into production
result namespaces. Do not collect new RF data for this task.

For each successful iteration publish code, tests, a Markdown report, timing
data, parity results, and figures to the requested remote. State component and
overall speedups separately, with runtime environment and concurrency. Install
a qualified change only within the user's deployment authorization, then verify
live behavior and retain the previous release for rollback.
