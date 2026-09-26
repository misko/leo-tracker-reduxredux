# Bounded SOL implementation and validation

The user authorized implementation and tests of the proposed improvements. The experiment keeps visits259–263 and the existing phase-blind GLRT candidate selection fixed. No RF collection, production changes, satellite identity inference or assumed inter-dwell phase connection is authorized by this experiment.

## Delegated work

1. SOL tracker: joint receiver-product frequency/phase estimation, frozen first20ms forward prediction and separately labeled rolling causal prediction. Compare constant-frequency, smooth/rate and robust models on the same observations. Fit differential states on even tones and score odd tones.
2. SOL response: independent tone trajectories, frozen training-only relative channel phase/delay correction, delay ambiguity accounting and later-frame agreement. Preserve the common phase gauge.
3. SOL validation: data-split and interpolation-support audit, independent prediction checks, synthetic regressions, capture clock/LO/baseline evidence and limitations on the expected geometric phase.

Root maintains shared pilot-cache.npz/json, coordinates interfaces, reviews outcomes and assembles final results. All handwritten changes use apply_patch; workers own separate report and test files.

## Scientific gates

Keep the estimated corrections inspectable and report original phase as well as residuals. Do not use held phase to choose offsets, cycle branches, thresholds or hyperparameters. Fit successes alone do not qualify improved phase recovery. Retain failed/ambiguous predictions in counts, and do not unwrap across dwell gaps. Distinguish intra-frame RX0-derived common-frequency preprocessing from differential tone-held validation: current preprocessing uses all RX0 tones, so held tones are not fully independent raw frequency support.

The primary practical question is whether corrections improve predictions on subsequent frames and other tones without imposing slow behavior on those outputs. Broadband agreement is corroboration, not absolute phase truth. Geometry requires measured antenna baseline and clock/LO reference evidence; absent values will be reported, not invented.
