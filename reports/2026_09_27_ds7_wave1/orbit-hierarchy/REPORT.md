# DS7 repeated-satellite support admission gate

Status: **STOP — no orbit-hierarchy variant fit admitted.**

This reference-free audit queried the public tracking endpoint once for each of the
88 frozen DS7 sessions. The 88 requests completed in 7.270 seconds with a
3-second per-request limit and a 90-second metadata budget. The receipt retains
only source/configuration digests, product creation time, candidate catalogue and
physical-group identifiers, and held-support/abstention/claim fields. It does not
retain observer-site or position-diagnostic data.

The split was declared structurally: complete chronological groups `group8-01`
through `group8-05` are donors and complete groups `group8-06` through
`group8-11` are targets. The audit rejects any group ordering or membership that
does not flatten to the exact frozen 88, so no recording from a target's group can
enter its donor side.

Of 348 projected candidate rows, 305 met the candidate-support diagnostic: held
leader rank 1, persisted on held data, positive held runner margin, and no
abstention. Three leading catalogue numbers repeated across the separated sides:

| Catalogue candidate | Donor group | Target group | Classification |
|---:|---|---|---|
| 63656 | group8-03 | group8-08 | candidate repeat only |
| 64001 | group8-02 | group8-08 | candidate repeat only |
| 66578 | group8-02 | group8-06 | candidate repeat only |

These repeats are useful coverage evidence, but every such row remains
`candidate_only=true` and `identity_claimed=false`. Across the complete projection
there are zero independently asserted identity rows and therefore zero qualifying
same-satellite identity or calibration priors. Repetition of a leading candidate
does not turn that candidate into an asserted satellite identity.

One member, `scan-fw-19441e44ae5e633c`, had no completed tracking product at
query time. Its membership is retained with null product metadata and no invented
support. The other 87 products share configuration digest
`sha256:f54e5ab518dae837df03eaf7a4d54b9d30807f0a5edc872f1b9351c70ec2c054`
and TLE-match digest
`sha256:3c660b30fe415db05f1ecb4f62b58515347fdc55bba83f91c5d8a5cc890a35e4`.

The source-alternative inventory at `../orbits/inventory.json` has file SHA-256
`f1cc3f2a6e6b2aeb643f21ffab6e2b567833b4fc4ba0164accf2e3a444243493`.
It reports ready causal public-GP coverage for all 88 captures from both
Space-Track and the Hugging Face mirror. SupGP and provider ephemeris are
unavailable. GP product availability does not change the failed identity gate.

The machine-readable receipt is `gate-receipt.json`, with projection digest
`sha256:a9f8800d86b790fea285d4beac6182059e8d91276a4e97dc7f4ba8b523cce847`.
No IQ was read, no RF/source artifact was changed, no reference was scored, and no
variant fit was run.

Verification:

```text
.venv/bin/python -m pytest -q tests/research/test_ds7_orbit_hierarchy_gate.py
4 passed in 0.02s

.venv/bin/ruff check tools/ds7_orbit_hierarchy_gate.py tests/research/test_ds7_orbit_hierarchy_gate.py
All checks passed!
```
