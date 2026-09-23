# First long-TRAIN track-quality audit

This training-only audit joins all **1,356** frozen prepared observation IDs in
`scan-hop-85afa91453f8847b` to public projected GLRT candidates. The prepared
evidence digest is `sha256:f52269026aa4455afa431a484ce4198a1bc5c24a116aac0855ef0710b20efe24`.
Every cached ID matched exactly once: hypothesis episode binding selects a
tracklet, its public point selects a candidate, and source group, dealiased CFO,
and support-centre UTC must agree.

`standard_uncertainty_hz` ranges 383.33--418.43 Hz (median 399.77). It derives
from shared timing uncertainty and canonical RF scaling, so it is not a
per-observation SNR calibration. Exact/control GLRT scores and margins are now
exported by the verified join, but no weighting model is fitted or claimed here.
A future inverse-variance or quality weighting must be selected against
randomized training-frequency holdouts only.

[quality.json](quality.json) contains the ID-keyed quality rows and provenance.
[export.py](export.py) is the read-only reproduction source; run it as `leo`.
