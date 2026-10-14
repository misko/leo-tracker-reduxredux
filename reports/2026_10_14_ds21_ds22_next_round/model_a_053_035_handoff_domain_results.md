# A053/035 timing handoff and search domains

The exact final-seed counterfactual confirms that the original high stage damages the inherited low likelihood through its shared satellite timing changes. The locked-high replication prevents that immediate loss. Separate post-seal geometry shows that neither case's current search disks contain the configured position. These are distinct limitations; this audit performs no fits and proposes no reference-derived seeds.

The completed replication is reported in `model_a_053_035_timing_replication_results.md` (commit 20c3d1eed). Its fresh original and locked-high selections are respectively 226.014→59.420 km on 053 and 188.807→179.059 km on 035. All selected final fits meet the unchanged full KKT ≤0.001. Its 42 new high/final calls and twelve inherited low attempts remain separate from this zero-fit audit. Both full condition matrices sealed before this audit's single configured-reference call.

For every completed final path, this audit evaluates three states under exactly the same full-frame likelihood, priors and learned frozen receiver contrast: its actual final seed, that seed with only its absolute satellite timing vector restored to its own saved low state, and its actual final endpoint. Geography, common calibration, RF dependence, clock function and learned contrast remain fixed in the timing counterfactual. Low observation rows are checked against the full frame, and every restored low NLL reproduces its original low-stage NLL within 1e-6. This is an attribution diagnostic, not a fitted continuation or a new eligible candidate.

| Case / original path | Low saved NLL | Low NLL after high handoff | Low NLL after joint fit | Low mass saved → handed off → final |
|---|---:|---:|---:|---:|
| 053 / 0 | 16041.210426 | 18438.845926 | 18204.974143 | 827.42 → 212.71 → 267.36 |
| 035 / 3 | 23229.051289 | 24304.659381 | 23211.770396 | 656.11 → 447.62 → 657.06 |

On 053 path 0, the timing move alone adds 2397.635499 to low NLL before joint optimization. Restoring low timings also improves high NLL by 262.091614. However, restoring them increases the shared timing-prior contribution by 264.104729. The original high-only objective therefore prefers its actual timing state by 2.013116, despite its worse frequency likelihood in both bands. This supports a greedy stage/prior tradeoff; it does not establish a failed high-stage solver. The final joint fit recovers only part of the low signal mass. The locked-high path 0 starts with the full low mass intact and ends at low/high NLL 16006.517289/7617.076836 with low mass 847.70.

On 035 path 3, the original timing move worsens low NLL by 1075.608093, improves high NLL by 662.716942 and increases the timing-prior cost by 106.545961. Here the high-only objective improves by 556.170982 through an explicit tradeoff against the absent low likelihood. The final joint fit recovers the low NLL. All ten completed original paths across these two cases suffer positive low NLL loss at the handoff; all ten completed locked-high paths have exactly zero timing-only loss. The two rejected 053 high paths and the inherited failed 035 low path in each arm remain explicit missing continuations.

The following geometry is retrospective. Distances are in the common regional coordinate plane used by the solver, rather than geodesic error bounds. All original proposal disks have radius 25 km. No configured coordinate was used in source freezing, fitting, candidate selection, or this audit's likelihood counterfactuals.

| Case / proposals | Nearest center distance km | Distance to disk union km | Configured point in any disk? |
|---|---:|---:|---|
| 053 BEFORE | 27.149074 | 2.149074 | No |
| 053 AFTER | 59.493376 | 34.493376 | No |
| 035 BEFORE | 5.796443 | 0 | Yes |
| 035 AFTER | 98.359065 | 73.359065 | No |

The 053 BEFORE start-5 center is 34.567130 km from the configured point: its 25 km disk also excludes the configured position. Retaining old candidates and disks can repair replacement regressions without making every desired position feasible. Changing native timing phase inside the current excluded domains cannot by itself remove that feasibility restriction. The original 035/029 fixed-union preservation experiment already tested original A stages; repeating those calls would add no new control.

The next proposed A test should first qualify a fixed 053 union bank and all twelve genuine BEFORE/AFTER starts using the existing transport ports, then retain the reviewed locked-high handoff identically for every path. Comparing the shared six AFTER paths against all twelve within that same bank tests start preservation with openly unequal cost (at most 18 versus 36 new stage calls). It cannot compare original cross-bank MAP values. Any subsequent radius experiment should use a frozen training-only trigger: strict stationary endpoint at its own geographic boundary plus an outward descent direction. Matched 25/50 km continuations must share the same initial state, contrast, center, observations and priors, and retain the original 20-second/600-iteration cap and strict full acceptance. Apply the trigger to all eligible paths, retain the incumbent, and rank by training objective. Do not choose a center, radius or path from the retrospective domain distances above. Native-phase changes should remain a separate intervention after feasible search coverage is established. No new fits are authorized or launched by this report.

The durable source is `tools/model_a_timing_handoff_audit.py` (6bc2b9c4f); the five component tests pass and Ruff passes. The actual audit took 10.948 seconds and made 60 objective evaluations, 60 explicit orbit predictions and 120 band likelihood evaluations, plus the predictions internal to those objectives; zero optimizer calls. The single configured-reference read is used only for the post-seal domain table. No held-out data is evaluated. Limits were 120 seconds internal, 135 seconds external TERM and 140 seconds KILL. The exclusive launch and complete termination bind the exact source protocol and output; orphan attempts cannot retry.

Authority: `/srv/bulk/leo-research-ds21-ds22/2026_10_14/model-a-timing-handoff-053035-v1`. The adjacent JSON preserves all twenty completed path counterfactuals, all four missing continuations, case selections, every disk distance, source protocol and durable receipt hashes. This diagnostic and the replication remain separate from the original full-cohort histogram 013. No subkilometer result or scientific promotion is established.
