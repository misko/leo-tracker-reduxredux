# Evidence and reproduction guide

This is a bounded research experiment over the existing DS24 recordings. The
operational estimator and persisted contracts are unchanged. The preceding
[cumulative review](../2026_10_25_ds24_ambiguity_position/REVIEW.md) explains the
retained baseline, earlier negative results and why these branches were chosen.

The position branch owns [its source](position/policy.py),
[protocol](position/PROTOCOL.md), [input and implementation bindings](position/protocol.json)
and [tests](position/test_experiment.py). It compares no addition, a hard
satellite identity and a whole-source identity mixture on DS24-0011. All six
method/arm slots, including numerical or qualification failures, belong in the
result. Raw RF results are sealed before the separate geographic evaluation.

The qualification branch owns [its runner](qualification/qualify.py),
[adequacy calculations](qualification/adequacy.py),
[protocol](qualification/PROTOCOL.md), [bindings](qualification/protocol.json)
and [tests](qualification/test_qualification.py). It preserves the four
information-selected complete sources from 0014–0017. Candidate evidence,
residual adequacy, original support and final estimator qualification are
separate outcomes. This branch does not fit a new geographic position.

The detector branch owns [its findings](REPLAY_FINDINGS.md),
[protocol](REPLAY_PROTOCOL.md), [runner](replay_one_window.py),
[tests](test_replay_one_window.py) and [full result](replay_one_window.json).
It replays exactly one original window with the historical deployed detector.
The containing chunk is fully verified; only the declared window enters the
detector. There is no injection or new recording.

These artifacts are not a standalone corpus. The original tracking contracts,
causal orbit banks, prior fit and ownership archives, numerical arrays and raw
IQ remain external read-only dependencies. Their exact paths and digests are
recorded in the branch protocols and publication manifest. A future replay must
verify those bindings and reconstruct the stated environment before executing
the frozen scripts. Running against arbitrary current workspace code does not
reproduce this experiment. The detector specifically uses the historical
deployment identified in its authority receipt.

The report preserves sources, protocols, compact results, complete outcome
tables, figures and independent audits. Large arrays are recorded in the
publication manifest with external paths and hashes. The regional inference
box remains 25×25 km centered at 37.906, -122.545. Evaluation GPS is used only
after the position branch's RF seal and audit. No postscan TLE inference,
cross-scan stationary pooling or new RF is introduced.
