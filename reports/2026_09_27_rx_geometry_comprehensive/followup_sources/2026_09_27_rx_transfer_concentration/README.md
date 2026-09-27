# Why the RX association update loses predictive accuracy

This is a posthoc attribution of the existing six-recording conditional transfer
experiment, not new validation, a fitted model, or a geographic accuracy claim.
No new observations, positions, candidate lists, or parameters were introduced.
The source receipt and analysis code are hashed in `results.json`.

## Findings

Positive gain means lower held-frequency NLL with the RX association update.
Contributions below use the full occupied-second denominator, so they add.

| Contribution to mean gain | A → B | B → A |
|---|---:|---:|
| All 344 tracks | −0.004239 | +0.000359 |
| 12 tracks whose MAP identity changes | +0.001177 | −0.007287 |
| 332 tracks whose MAP identity stays fixed | −0.005416 | +0.007646 |
| Baseline confidence below 0.9 | −0.002362 | −0.001424 |
| Baseline confidence 0.9–0.99 | +0.001384 | −0.003059 |
| Baseline confidence at least 0.99 | −0.003260 | +0.004841 |

The confidence rows partition all tracks; the MAP rows are a separate partition.
The bins were fixed for description, not chosen as an acceptance rule.

**Stable MAP identity does not imply a harmless update.** For forward prediction,
the unchanged-MAP tracks account for the net regression. RX can suppress a small
alternative probability that matters greatly for held frequency evidence, without
changing the most likely candidate. One `4c563` track changes maximum probability
from 0.99448 to 0.99994, keeps candidate 62495, and worsens predictive NLL by
0.4061/observation; candidate 69497 fits the held block best. This is an outcome
diagnostic, not proof that 69497 is the physical satellite.

**Some updates also make very confident harmful switches.** In reverse prediction,
one `4c563` track moves from candidate 64497 (baseline probability 0.96529) to
53027 (RX-updated probability 0.999974), although the held frequency block favors
64497. Its gain is −0.9560/observation and its contribution to the full average is
−0.004506. The full track IDs and five largest positive/negative contributions
are retained in `results.json`.

**Neither deleting one recording nor a simple confidence gate solves this.**
The forward mean remains negative after removing any one of the six recordings
(range −0.007975 to −0.001063). The reverse mean changes sign across those
descriptive omissions (−0.003230 to +0.005034). These are not new leave-one-out
model fits or independent tests. The least-confident bin has negative gain in
both directions; the middle and high-confidence bins disagree by direction.
There is no justified confidence threshold to deploy from this table.

For scale only, choosing the best candidate after observing each held block
would improve the weighted score by 0.15815 forward and 0.17248 reverse.
This hindsight bound is not attainable evidence, a physical identity label, or
a geographic estimator. It only shows that the frozen candidate inventory is
not uniformly devoid of predictive alternatives.

## Implication for the next model

The next useful hypothesis is **an unreliable-RX latent state**, rather than
more aggressive use of RX evidence. Let `q_F` be frequency-only candidate
probabilities and `q_RX` the current RX-updated probabilities. A conservative
mixture `q_safe = (1−λ) q_F + λ q_RX` retains frequency-only support.

For any held likelihood vector and `0 ≤ λ < 1`,

```text
P_safe(held) ≥ (1−λ) P_F(held)
NLL_safe − NLL_F ≤ −log(1−λ) / held_observation_count
```

This is a mathematical loss bound, **not proof of improved average prediction
or position**. It is not an RMS cap: candidate likelihoods and poor observations
remain in the score. A posterior blend is a conservative generalized update;
calling λ an inferred physical reliability probability would require an explicit
generative reliability model and its evidence normalization.

Any reliability weight must be fixed before a new test or learned only within
nested training folds. A randomized whole-group evaluation must keep overlapping
raw windows, physical RX pairs, and other correlated observations together and
fit preprocessing using training data only. The current temporal diagnostics may
motivate this model but cannot validate it. Independent Sacramento/Reno candidate
generation remains mandatory. Geographic resolution still requires a separate
matched location experiment after predictive evidence supports proceeding.

## Reproduction

From the repository root:

```bash
python3 -m unittest discover -s reports/2026_09_27_rx_transfer_concentration -p 'test_*.py'
python3 reports/2026_09_27_rx_transfer_concentration/audit.py
```

The audit refuses to overwrite `results.json`; use a fresh copied analysis
directory for reproduction. Five tests pass, including the hindsight bound,
contribution denominator, inconsistent-score rejection, and duplicate rejection.
The executable also verifies exact parity with both published pooled gains.
