# Exact source-exclusion mixture: valid normalization, poor predictive transfer

The exact soft source-exclusion model keeps every exported track in the observation space and sums all permitted signal/background interpretations. It improves reference distance on DS8 and DS9, worsens DS7, and leaves only DS8 below 1 km. Its complete-track held score is substantially worse than the original model on all three panels. **Do not promote it as the geographic or predictive baseline.**

| Dataset | Original distance (m) | Hard subset distance (m) | Exact soft-exclusion distance (m) | Held replacement change (nats) |
|---|---:|---:|---:|---:|
| DS7 | 1,688.3 | 1,894.8 | 1,926.1 | −2,294.42 |
| DS8 | 722.1 | 820.5 | 642.3 | −1,716.70 |
| DS9 | 2,041.9 | 1,810.8 | 1,884.0 | −1,849.64 |

Held replacement change compares the newly fitted new model with the original fitted original model, on the **same complete exported track set**. This differs from the preceding hard-subset report, which scored only retained tracks. [Full-precision results and score decomposition](summary.json) · [Frozen protocol](PROTOCOL.md)

## Same observation dimensions for every interpretation

Each track has its original conditional satellite density f and linear-trend background density b. A latent active set cannot contain two tracks that share a probe group. An inactive track still contributes b; its observations do not disappear. Condition the original independent 0.8 signal prior on this exclusion graph.

The normalized density is:

`log p = sum log b + log Z(log 4 + log f − log b) − log Z(log 4)`.

Z sums over all independent sets, including the empty set. The denominator is essential: it normalizes the restricted prior. Omitting inactive-track likelihoods or this prior normalization would produce a different, invalid comparison. Without graph conflicts, the expression reduces exactly to the existing 0.8 f + 0.2 b model.

The three panels have 183, 162 and 163 conflict edges. Their largest eligible connected components have 8, 6 and 7 tracks, respectively, so exhaustive component enumeration is small. Every independent set is included; there is no beam approximation or selected-hypothesis truncation. Posterior active probabilities are the exact gradient weights. Expected active-track totals at the new fits are 331.4/476, 346.6/478 and 335.4/489; inactive tracks remain scored.

## What the test distinguishes

Moving parameters within the new model improves its held score by only +1.60, +16.19 and +1.06 nats. The much larger negative replacement changes therefore arise primarily from changing the observation model, not failure to refine its starting parameters. Evaluating the new parameters through the old model also lowers its held score in all three panels (−30.65, −2.08 and −10.46 nats).

The exact density is a working model on **exported track contrasts**, conditional on fixed graph and retained banks. It is not a calibrated likelihood for raw IQ. Background-track dependence, data-dependent detection/graph construction and candidate-bank conditioning remain approximations. Mathematical normalization does not establish physical correctness.

One restrictive assumption is particularly important: a single shared probe excludes coexistence of two **whole signal tracks**, including all their non-overlapping observations. The legacy complete-hypothesis rule motivates testing it, but this model may needlessly force otherwise informative track histories into the background. The predictive loss does not prove this is the sole cause; it identifies a limitation to test before more geographic tuning.

## Decision

Retain the exact partition implementation and its tests as a normalization reference, not as a promoted estimator. A further source-conflict model should resolve alternatives at the probe/observation level while allowing track histories to coexist elsewhere. It must retain an explicit likelihood for the same measured data under every alternative. Avoid searching graph penalties or priors against these known reference distances.

Ordinary pooling remains the geographic control. The present outcomes are one time-balanced N8 set per dataset, with two local starts per new model; they are not global-optimum guarantees, full-dataset medians or blind accuracy estimates.

## Verification

Three synthetic tests verify reduction to the old no-conflict mixture, unit total probability on a finite discrete observation space, exact partition derivatives and refusal of oversized components. Actual-data no-conflict checks reproduce the old score, gradient and held score at each original fit within 1e-7. All six new optimizer starts qualify and pass finite-difference audits. Processes finish in 10–12 seconds under 180-second caps.

[partition.py](partition.py), [exclusive.py](exclusive.py), [tests](test_partition.py), [run.py](run.py), [launch.py](launch.py), [input/code hashes](manifest.json), per-dataset outputs and receipts, and [summarize.py](summarize.py) are retained. Exact enumeration refuses components above 12 tracks rather than silently approximating them. All original observations and partitions remain unchanged.

Reference uncertainty is unquantified and all evaluated data were previously exposed. No new RF, production changes, public-contract mutation or remote publication occurred.
