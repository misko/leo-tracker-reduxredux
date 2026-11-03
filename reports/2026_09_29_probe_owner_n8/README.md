# Probe ownership preserves more history, but geographic transfer remains mixed

Resolving conflicts observation by observation retains **87.6–90.1% of training observations**, compared with 76.2–79.5% under hard whole-track selection. It improves reference distance on DS9 but worsens DS7 and DS8, leaving one of three panels below 1 km. Coverage recovery alone is not a consistent accuracy improvement.

| Dataset | Original all-track distance (m) | Whole-track selection (m) | Probe-owner distance (m) | Training retained | Retained tracks |
|---|---:|---:|---:|---:|---:|
| DS7 | 1,688.3 | 1,894.8 | 2,095.2 | 87.6% | 450 / 476 |
| DS8 | 722.1 | 820.5 | 861.5 | 89.2% | 446 / 478 |
| DS9 | 2,041.9 | 1,810.8 | 1,662.6 | 90.1% | 466 / 489 |

[Full-precision results](summary.json) · [Frozen protocol](PROTOCOL.md)

## Local ownership instead of whole-track exclusion

Within each scan, each source group is assigned to the eligible track with the most original training observations, with track-ID ties. Only observations owned by another track are removed. The rest of each track history remains eligible. No detector margin, held signal value, reference coordinate or optimized likelihood chooses owners.

Track support is checked after pruning using the existing requirement of two training and one held observation. This explicitly excludes 26, 32 and 23 tracks in DS7, DS8 and DS9. No silent track substitution or second-pass reassignment occurs. Those exclusions leave 22, 26 and 16 source groups unrepresented, respectively. Every surviving observation has a unique source group within its scan.

The retained observation counts are 20,259 / 23,126, 18,171 / 20,384 and 20,140 / 22,373. Times, frequencies, masks and candidate-state observation axes are sliced together in memory; archived inputs remain unchanged. All eight scans stay in every dataset panel.

## Matched held prediction

Evaluate all parameter vectors on the same probe-owner observation support. The new fits' held changes versus all-track parameters are +6.42, +30.05 and −9.52 nats for DS7–DS9. Versus hard whole-track parameters they are +49.50, +7.96 and −13.73 nats. These are parameter comparisons on fixed support, not unequal-dimensional likelihood comparisons.

Once again, the geographic and predictive rankings differ: DS9 moves closer to the reference while its matched held prediction worsens; DS7 and DS8 move farther while their held scores improve. The metrics must remain separate. Discarded observations are lost coverage, not held successes.

## What is and is not resolved

The experiment confirms that enforcing one owner per probe need not discard entire conflicting histories. It does not validate this particular ownership ranking as a calibrated association method. Longer training support is a deterministic coverage heuristic, not evidence that a candidate is physically correct. The chosen owner can therefore preserve a wrong alternative or remove a useful one.

Do not promote this rule or interpret source consistency alone as an accuracy certificate. Keep the raw alternative inventory and compare any future ownership probabilities against independent signal-reliability evidence. A soft probe-level model would need explicit candidate likelihoods and a treatment of shared track parameters; this hard-selection control is not that model.

These results apply to the same single time-balanced N8 panel per dataset as preceding tests. Data were previously exposed, candidate banks remain site-conditioned, and the operator reference uncertainty remains unknown. They are not full-dataset or blind accuracy estimates.

## Validation and artifacts

Two synthetic tests verify surviving partial histories, deterministic ties, candidate-array alignment, original-array preservation and explicit support exclusions. All 18 new fitting starts qualify, with original bounds and finite-difference gates. Actual-data checks verify sidecar/partition alignment, unique surviving source groups, original-score replay and timing-grid replay. Processes finish in 32–43 seconds under 180-second caps, with no retries.

[ownership.py](ownership.py), [run.py](run.py), [launch.py](launch.py), [input/code hashes](manifest.json), per-track removed indices and exclusion reasons, all starts, results and receipts, and [summarize.py](summarize.py) are retained. Summary generation verifies frozen hashes and adds reference distances only after training-based selection.

No RF collection, IQ reads, production modifications, public-contract changes, golden-fixture edits or remote publication occurred.
