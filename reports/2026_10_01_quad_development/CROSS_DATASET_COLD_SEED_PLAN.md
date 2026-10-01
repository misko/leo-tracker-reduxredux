# Cross-dataset cold one-start comparison

Extend the completed first-DS9-block comparison to the first single, first pair and first quad of DS10 and DS11. Membership is metadata-selected and already exposed in development; no independent accuracy validation is claimed. The completed full-panel first-start replay motivates testing implementation equivalence and actual inference cost across datasets.

Use the unchanged frozen `run_seed_limit.py`: original acquisition from the uniform Sacramento disk, zero nuisance initialization, unchanged likelihood/prior/height, 64 iterations, and one versus three starts. Neither arm uses a saved fitted state. Preserve 90/180/360-second inference caps and separately supervised audit caps of the same sizes, as in the original cold comparison. Every outcome remains recorded, including launch failures or equivalence failures. No retries or time-limit relaxation.

Fix orders before running: DS10 single (3,1), pair (1,3), quad (3,1); DS11 single (1,3), pair (3,1), quad (1,3). Together with DS9's historical orders these alternate, but they are not randomized replications. Host load, caches and elapsed dates limit timing interpretation; show CPU as well as wall time, and do not pool historical timing into an unsupported speed guarantee.

Run sequentially under the shared fit lock in bounded stages: both single comparisons first, then both pairs, then both quads. Inspect process/audit/equivalence results after each stage before launching the next. A deadline or implementation-equivalence failure requires diagnosis rather than automatically completing a broader campaign. All stages are read-only analysis of existing radio observations; no new RF.

Require identical acquired proposals across arms and original baseline, identical first-fit state/labels/objective within the original tolerances, exactly one fit in the one-start arm, and the original count in the three-start arm. The final summary additionally compares each winner with its corresponding saved original fit, using the original cold summary tolerances. Independently audit each fit before using its reference error. Report all six new window comparisons separately from the historical DS9 three-window results and the full-panel replay.

Interpretation: this is a check of the accuracy/cost tradeoff of a simpler inference policy, not a new noise or discrepancy model. Keep the original acquisition implementation; do not combine its seed-count change with the separate faster-acquisition experiment.
