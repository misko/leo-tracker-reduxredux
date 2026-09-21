from __future__ import annotations

import json

import pytest

from leo.analysis.research.position_subsets import (
    Observation,
    build_subset_matrix,
    canonical_hash,
)
from tools.benchmark_position_subsets import atomic_write_result, plan_jobs


def _observations() -> tuple[Observation, ...]:
    rows = []
    for track in range(4):
        for point in range(8):
            rows.append(
                Observation(
                    observation_id=f"o-{track}-{point}",
                    track_id=f"t-{track}",
                    pass_group_id=f"p-{track // 2}",
                    timestamp_ns=(track * 100 + point) * 1_000_000_000,
                    fitting=point != 7,
                    channel=f"c-{track % 2}",
                    sample_rate_hz=2_000_000,
                )
            )
    return tuple(rows)


def test_nested_density_is_stable_stratified_and_preserves_holdout() -> None:
    observations = _observations()
    first = build_subset_matrix(observations, seeds=[3], temporal_bins=4)
    second = build_subset_matrix(tuple(reversed(observations)), seeds=[3], temporal_bins=4)
    density = {item.fraction: item for item in first if item.method == "density"}
    repeated = {item.fraction: item for item in second if item.method == "density"}
    assert set(density[0.25].fitting_ids) <= set(density[0.5].fitting_ids)
    assert set(density[0.5].fitting_ids) <= set(density[1.0].fitting_ids)
    assert density == repeated
    assert density[0.5].rounding == "floor-global-stratified-round-robin"
    assert len(density[0.25].fitting_ids) == 7
    assert len(density[0.5].fitting_ids) == 14
    assert density[0.5].evaluation_ids == tuple(f"o-{track}-7" for track in range(4))
    assert all(
        any(obs_id.startswith(f"o-{track}-") for obs_id in density[0.5].fitting_ids)
        for track in range(4)
    )


def test_density_does_not_force_a_minimum_per_small_stratum() -> None:
    observations = (
        Observation("a", "one", "pass-a", 0, True, "c", 1),
        Observation("held", "one", "pass-a", 1, False, "c", 1),
    )
    subsets = build_subset_matrix(observations, seeds=[0], temporal_bins=4)
    quarter = next(x for x in subsets if x.method == "density" and x.fraction == 0.25)
    assert quarter.fitting_ids == ()
    assert quarter.unusable_track_ids == ("one",)


def test_pass_subsets_keep_rf_groups_whole_and_do_not_use_norad() -> None:
    subsets = build_subset_matrix(_observations(), seeds=[1])
    half = next(x for x in subsets if x.method == "pass" and x.fraction == 0.5)
    selected = set(half.fitting_ids)
    for pass_id in ("p-0", "p-1"):
        members = {
            x.observation_id for x in _observations() if x.fitting and x.pass_group_id == pass_id
        }
        assert not (selected & members) or members <= selected
    with pytest.raises(TypeError):
        Observation("x", "t", "p", 0, True, "c", 1, norad=123)  # type: ignore[call-arg]


def test_duration_is_primary_campaign_prefix_and_marks_unsupported_evaluation() -> None:
    subsets = build_subset_matrix(_observations(), seeds=[0], durations_s=[150])
    duration = next(x for x in subsets if x.method == "duration" and x.fraction is None)
    assert duration.window_start_ns == 0
    assert duration.window_end_ns == 150_000_000_000
    assert duration.unsupported_evaluation_ids == ("o-2-7", "o-3-7")
    assert not set(duration.evaluation_ids) & set(duration.fitting_ids)


def test_duplicate_ids_rejected_and_hash_is_canonical() -> None:
    rows = _observations()
    with pytest.raises(ValueError, match="duplicate observation_id"):
        build_subset_matrix(rows + (rows[0],), seeds=[0])
    assert canonical_hash({"b": 1, "a": [2]}) == canonical_hash({"a": [2], "b": 1})


def test_small_fractions_are_nested_exact_and_do_not_promote_discarded_training():
    rows = _observations()
    fractions = (1 / 32, 1 / 16, 1 / 8, 1 / 4, 1 / 2, 1.0)
    subsets = build_subset_matrix(rows, seeds=[2], fractions=fractions)
    previous = set()
    for fraction in fractions:
        subset = next(x for x in subsets if x.method == "density" and x.fraction == fraction)
        assert len(subset.fitting_ids) == int(28 * fraction)
        assert previous <= set(subset.fitting_ids)
        assert set(subset.evaluation_ids) <= {r.observation_id for r in rows if not r.fitting}
        previous = set(subset.fitting_ids)
    for invalid in ((), (0, 1), (0.5, 0.25, 1), (0.25, 0.25, 1), (0.25,)):
        with pytest.raises(ValueError, match="fractions"):
            build_subset_matrix(rows, fractions=invalid)


def test_atomic_result_is_idempotent_and_refuses_collision(tmp_path) -> None:
    path = tmp_path / "job.json"
    payload = {"job_id": "abc", "input_hash": "sha256:i", "config_hash": "sha256:c"}
    assert atomic_write_result(path, payload) == "written"
    assert atomic_write_result(path, payload) == "existing"
    assert json.loads(path.read_text()) == payload
    with pytest.raises(FileExistsError):
        atomic_write_result(path, {**payload, "config_hash": "sha256:other"})


def test_plan_reuses_identical_full_membership() -> None:
    body = {
        "schema": "position-subset-benchmark-manifest-v1",
        "scientific_scope": "conditional-fixed-identity-local-replay",
        "observations": [x.__dict__ for x in _observations()],
    }
    body["manifest_hash"] = canonical_hash(body)
    jobs = plan_jobs(body, {"model": "test"})
    full = [job for job in jobs if len(job["subset"]["fitting_ids"]) == 28]
    assert len(full) == 1
    assert {x["method"] for x in full[0]["subset_aliases"]} == {"pass", "duration"}
    assert full[0]["initialization"] == "independent-external-starts-training-objective-only"
