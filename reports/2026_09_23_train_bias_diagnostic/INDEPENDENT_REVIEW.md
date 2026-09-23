# Independent review

Reviewed the completed TRAIN-only block-deletion diagnostic, its sealed result,
and the focused tests. No source or result file was changed.

The result seal is valid: `results/inference.json` has SHA-256
`32d6a03e882dd3a3a59ff14512183ae2f262ed0a1a68b8feaf0769b4df7a6147` and
matches its companion digest. The run binds the pooled parent, both 8-hour
parent inferences, numerical helper, single-scan scorer, and its own source.
Their recorded digests match the files read; the three parent companion seals
also verify. It verifies every parent receipt and NPZ cache digest and rejects
any difference between reconstructed and sealed `(track_id, candidate_id,
session_id)` support. The reconstructed support is 6,988 unique fixed tracks.

Each refit removes exactly one `numpy.array_split` contiguous quarter of one
of the two frozen TRAIN session lists, retains the fixed IDs for all remaining
tracks, and starts from the same sealed pooled Sacramento/5-s solution. The
full-support continuation control is a suitable numerical check: 0.135 m is
far smaller than the deletion shifts. The score call uses its default
`include_evaluation=False`; `run.py` does not read a receiver reference, and
the sealed output records both `held_rows_used: false` and
`reference_position_read: false`. The reused score applies the existing
duration-weighted capped 800-Hz training objective.

The reported median 154 m and maximum 530 m deletion shifts, and nearly
opposed group means, reproduce from the sealed rows. The README correctly
limits them to local deletion sensitivity within one prior basin. The opposing
means are evidence of structured instability at the pooled optimum; they do
not establish a common bias, a physical cause, a calibrated uncertainty, or
independent accuracy. The proposed next step should remain a separately
prespecified, physically measurable model test rather than retrospective block
removal.

Validation run: `pytest -q test_run.py` passed 4 tests and Ruff passed.
