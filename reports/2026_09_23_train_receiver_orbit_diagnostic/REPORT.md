# Frozen TRAIN paired-receiver residual diagnostic

## Result

The frozen diagnostic completed on exactly 151 TRAIN scans and 6,988 fixed
tracks. It found 486 passing RX0/RX1 track pairs in 407 provisional
scan/candidate groups, containing 6,281 matched training samples. Candidate
equality remains provisional. No VAL, TEST, held-frequency, reference
coordinate, position refit, or new RF data was used.

The group-bootstrap mean RX0-minus-RX1 residual slope was -4.52 Hz/s (95% CI
-6.09 to -2.88). The quadratic coefficient was 0.075 Hz/s² (95% CI -0.210 to
0.360). The common residual slope was -5.40 Hz/s (95% CI -8.69 to -2.20), and
the common quadratic coefficient was 0.062 Hz/s² (95% CI -0.317 to 0.426).
Bootstrap resampling used whole scan/candidate groups with seed 20260923.

These pooled slopes do not support a shared receiver-drift correction. The
differential slope changed from -6.21 Hz/s in the first TRAIN group to -2.49
Hz/s in the second; the second-group interval included zero. More decisively,
lane means ranged from -11.21 to +6.32 Hz/s and changed sign across RF lanes.
That heterogeneity conflicts with a single RX0/RX1 drift term. The common
slope also varied by lane and TRAIN group, so it is not adequate evidence for
a common orbit/propagation correction.

Element-age strata could not be computed truthfully: the bound state caches
persist the causal snapshot digest and collection time, but not each
candidate's TLE element epoch. The plot therefore labels snapshot collection
age and the result marks element-age analysis unavailable. No orbit-age claim
is made.

## Support and ambiguity

The frozen gates rejected 2,695 tracks without an opposite receiver, 2,982
candidate track combinations with a lane or sample-rate mismatch, 525 with
less than 3 seconds overlap, and 834 with fewer than eight one-to-one matches
inside 80 ms. No pair failed the centered 2 kHz frequency gate after reaching
it. Sensitivity runs at 40, 80, and 120 ms were identical because the passing
samples were aligned more tightly than 40 ms.

Seventy-three provisional scan/candidate groups produced multiple passing
track pairs. One track appeared in two passing pairs; the maximum reuse was
two. All passing pairs were retained as frozen, while uncertainty resampled
the enclosing scan/candidate group so reused or competing pairs were never
treated as independent bootstrap units. This remaining association ambiguity
is another reason not to deploy a correction from the pooled mean.

## Provenance and checks

The executed analyzer binds its own digest, the pooled inference, both fixed-ID
parent inferences, all 151 receipt/NPZ hashes, capture and analysis manifests,
and causal TLE snapshot digests in `results/inference.json`. It proves exact
`(session_id, track_id, candidate_id)` equality with the fixed parents and
exact observation joins with the recovered public graph path. It also proves
the absolute-support/relative-cache time anchor for every recovered
observation before orbit interpolation or receiver matching.

The strict recovery source is `recover_metadata_strict.py`; its completed
canonical artifact is `/tmp/leo-train-rx-metadata.json`. Recovery accounting is
151 successful and zero failed sessions. The earlier `recover_metadata.py`
attempt remains preserved and is not the source of the executed result.

Three synthetic tests cover deterministic one-to-one time matching, recovery
of slope and quadratic terms in the presence of a large constant offset, and
whole-group rather than row bootstrap behavior. Pytest and Ruff pass.

From the repository root, reproduce the result after the strict recovery has
produced `/tmp/leo-train-rx-metadata.json` with:

```bash
uv run pytest -q tests/tools/test_train_receiver_orbit_diagnostic.py
uv run ruff check reports/2026_09_23_train_receiver_orbit_diagnostic/analyze.py tests/tools/test_train_receiver_orbit_diagnostic.py
uv run python reports/2026_09_23_train_receiver_orbit_diagnostic/analyze.py
sha256sum reports/2026_09_23_train_receiver_orbit_diagnostic/analyze.py reports/2026_09_23_train_receiver_orbit_diagnostic/results/inference.json
cat reports/2026_09_23_train_receiver_orbit_diagnostic/results/inference.sha256
```

The analyzer requires a fresh `results` directory by design. The published
digests are analyzer
`8f49f6372d092660aa51418893a21e70885dfdd8d42891525e9fe2cb532b5688`
and inference
`12a5906d2c9611799065d1e7fcb736f21de0ff0bb7b7d6ebb1a55fb6fdec65d1`.

Render the sealed lane and TRAIN-block consistency estimates without rerunning
the diagnostic with:

```bash
uv run python reports/2026_09_23_train_receiver_orbit_diagnostic/render_consistency.py
sha256sum reports/2026_09_23_train_receiver_orbit_diagnostic/render_consistency.py reports/2026_09_23_train_receiver_orbit_diagnostic/results/consistency.png
cat reports/2026_09_23_train_receiver_orbit_diagnostic/results/consistency.sha256
```

The consistency renderer digest is
`2531ca0cd06066186e6885ff0a36e45b0e1f53699aabcf7892f456e82d2621f9`;
the rendered PNG and its sidecar are
`264ec86b53192864b55898976272366562796c7ec1878ee1b8a32c01e099630a`.

The appropriate next experiment is a prespecified grouped cross-fit of a
shared receiver differential model across disjoint satellite/pass groups. The
present lane and TRAIN-group inconsistency means that experiment must qualify
the shared structure before any correction is applied to unpaired tracks.
