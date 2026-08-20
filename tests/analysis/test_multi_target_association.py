from __future__ import annotations

import hashlib
import itertools
import json
import random
from pathlib import Path

import pytest

from leo.analysis.starlink import multi_target as multi_target_module
from leo.analysis.starlink.multi_target import (
    associate_multi_target_observations,
    default_multi_target_association_config,
)
from leo.contracts.digests import canonical_digest
from leo.contracts.multi_target import (
    DuplicateBranchStatus,
    MultiTargetAssociationConfigV1,
    MultiTargetObservationV1,
)
from leo.contracts.standard_pipeline import StandardScientificStatus


def _observation(
    name: str,
    hypothesis: str,
    time_s: float,
    frequency_hz: float,
    slope_hz_per_s: float,
) -> MultiTargetObservationV1:
    return MultiTargetObservationV1(
        observation_id=canonical_digest({"observation": name}),
        component_id=canonical_digest({"component": "shared"}),
        hypothesis_set_id=canonical_digest({"hypothesis": hypothesis}),
        time_s=time_s,
        canonical_cfo_hz=frequency_hz,
        slope_hint_hz_per_s=slope_hz_per_s,
        acceleration_hint_hz_per_s2=0.0,
    )


def _config(**updates: object) -> MultiTargetAssociationConfigV1:
    config = default_multi_target_association_config()
    return MultiTargetAssociationConfigV1.model_validate(
        {**config.model_dump(mode="json"), **updates}
    )


def test_global_path_cover_preserves_identity_through_crossing() -> None:
    observations = tuple(
        _observation(f"a-{index}", f"a-{index}", time_s, -1000 + 20_000 * time_s, 20_000)
        for index, time_s in enumerate((0.0, 0.05, 0.10, 0.15))
    ) + tuple(
        _observation(f"b-{index}", f"b-{index}", time_s, 1000 - 20_000 * time_s, -20_000)
        for index, time_s in enumerate((0.0, 0.05, 0.10, 0.15))
    )

    result = associate_multi_target_observations(observations, config=_config())

    retained = [item for item in result.branches if item.retained]
    assert len(retained) == 2
    assert {tuple(str(item) for item in branch.hypothesis_set_ids) for branch in retained} == {
        tuple(str(canonical_digest({"hypothesis": f"a-{index}"})) for index in range(4)),
        tuple(str(canonical_digest({"hypothesis": f"b-{index}"})) for index in range(4)),
    }
    assert result.status is StandardScientificStatus.COMPLETE
    assert result.converged is True
    assert 2 <= result.assignment_iterations <= 12
    assert sum(item.selected for item in result.edge_decisions) == 6


def test_birth_death_and_one_missed_probe_are_explicit() -> None:
    observations = (
        _observation("a0", "a0", 0.0, 100.0, 10.0),
        _observation("a1", "a1", 0.05, 100.5, 10.0),
        _observation("a3", "a3", 0.15, 101.5, 10.0),
        _observation("b2", "b2", 0.10, 20_000.0, -20.0),
        _observation("b3", "b3", 0.15, 19_999.0, -20.0),
    )

    result = associate_multi_target_observations(observations, config=_config())

    retained = [item for item in result.branches if item.retained]
    assert len(retained) == 2
    selected = [item for item in result.edge_decisions if item.selected]
    assert any(item.missed_probe_count == 1 for item in selected)
    assert sum(len(item.observation_ids) for item in retained) == 5


def test_duplicate_alias_hypothesis_collapses_but_distinct_peaks_do_not() -> None:
    same_hypothesis = tuple(
        _observation(f"a-{index}", f"h-{index}", time_s, 1000 + index, 20.0)
        for index, time_s in enumerate((0.0, 0.05, 0.10))
    ) + tuple(
        _observation(f"b-{index}", f"h-{index}", time_s, 1001 + index, 20.0)
        for index, time_s in enumerate((0.0, 0.05, 0.10))
    )
    result = associate_multi_target_observations(same_hypothesis, config=_config())
    assert any(
        item.status is DuplicateBranchStatus.COLLAPSED_ALIAS_HYPOTHESIS
        for item in result.duplicate_decisions
    )
    assert sum(item.retained for item in result.branches) == 1

    distinct = tuple(
        item.model_copy(
            update={"hypothesis_set_id": canonical_digest({"distinct": item.observation_id})}
        )
        for item in same_hypothesis
    )
    distinct_result = associate_multi_target_observations(distinct, config=_config())
    assert sum(item.retained for item in distinct_result.branches) == 2
    assert all(
        item.status is DuplicateBranchStatus.RETAINED_DISTINCT_SUPPORT
        for item in distinct_result.duplicate_decisions
    )


def test_bounds_propagate_partial_instead_of_silently_dropping() -> None:
    observations = tuple(
        _observation(f"o-{index}", f"h-{index}", index * 0.05, float(index), 20.0)
        for index in range(5)
    )
    result = associate_multi_target_observations(
        observations,
        config=_config(maximum_observations=4),
    )
    assert result.status is StandardScientificStatus.PARTIAL
    assert result.source_observation_count == 5
    assert result.returned_observation_count == 4
    assert result.truncated_observation_count == 1


def test_input_order_does_not_change_canonical_bytes() -> None:
    observations = tuple(
        _observation(f"o-{index}", f"h-{index}", index * 0.05, float(index), 20.0)
        for index in range(6)
    )
    forward = associate_multi_target_observations(observations, config=_config())
    reverse = associate_multi_target_observations(tuple(reversed(observations)), config=_config())
    assert forward == reverse
    assert forward.content_digest == reverse.content_digest


def test_blocking_flow_matches_exhaustive_optional_matching_oracle() -> None:
    config = _config(maximum_gap_s=0.20)
    random_source = random.Random(4417)
    for case in range(20):
        observations = tuple(
            _observation(
                f"oracle-{case}-{index}",
                f"oracle-{case}-{index}",
                index * 0.05,
                1_000.0 + 3.0 * index + random_source.uniform(-40.0, 40.0),
                60.0 + random_source.uniform(-10.0, 10.0),
            )
            for index in range(6)
        )
        ordered = tuple(sorted(observations, key=lambda item: (item.time_s, item.observation_id)))
        decisions = multi_target_module._edge_decisions(ordered, config)
        selected = multi_target_module._minimum_cost_path_cover(ordered, decisions, config)
        accepted = tuple(
            item
            for item in decisions
            if item.status is multi_target_module.AssociationEdgeStatus.ACCEPTED
        )

        best_cost = 0.0
        for count in range(1, len(accepted) + 1):
            for candidate in itertools.combinations(accepted, count):
                sources = {item.source_observation_id for item in candidate}
                destinations = {item.destination_observation_id for item in candidate}
                if len(sources) != count or len(destinations) != count:
                    continue
                cost = sum(
                    item.link_cost - config.birth_penalty - config.death_penalty
                    for item in candidate
                )
                best_cost = min(best_cost, cost)
        selected_by_key = {
            (item.source_observation_id, item.destination_observation_id): item for item in accepted
        }
        actual_cost = sum(
            selected_by_key[key].link_cost - config.birth_penalty - config.death_penalty
            for key in selected
        )
        assert actual_cost == pytest.approx(best_cost, abs=1e-10)
        assert len({source for source, _ in selected}) == len(selected)
        assert len({destination for _, destination in selected}) == len(selected)


def test_sixty_second_association_performance_receipt_is_hash_pinned() -> None:
    receipt_path = Path("corpus/goldens/cfo-dealias-association-performance-v1.json")
    receipt_bytes = receipt_path.read_bytes()
    assert hashlib.sha256(receipt_bytes).hexdigest() == (
        "43acb144dc75467523100715a32c95cd1d008891fd136c13605d4ac097900454"
    )
    receipt = json.loads(receipt_bytes)
    source_path = Path(receipt["implementation"]["source_path"])
    assert (
        hashlib.sha256(source_path.read_bytes()).hexdigest()
        == receipt["implementation"]["source_sha256"]
    )
    fixture = receipt["fixture"]
    assert fixture["duration_s"] == 60.0
    assert fixture["observation_count"] == 1_200
    assert fixture["warmup_count"] == fixture["measurement_count"] == 5
    measured = receipt["reviewed_measurement"]
    acceptance = receipt["acceptance"]
    assert len(measured["measurements_s"]) == 5
    assert max(measured["measurements_s"]) == measured["maximum_s"]
    assert measured["maximum_s"] <= acceptance["maximum_allowed_wall_s"]
    assert measured["incremental_peak_rss_kib"] <= acceptance["maximum_incremental_rss_kib"]
    assert acceptance["wall_pass"] is True
    assert acceptance["memory_pass"] is True


def test_bounded_nonconvergence_is_insufficient_not_a_last_iteration_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    observations = tuple(
        _observation(f"o-{index}", f"h-{index}", index * 0.05, float(index), 20.0)
        for index in range(3)
    )
    calls = 0

    def _alternating_cover(*args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        if calls % 2:
            return frozenset(
                {
                    (observations[0].observation_id, observations[1].observation_id),
                    (observations[1].observation_id, observations[2].observation_id),
                }
            )
        return frozenset()

    monkeypatch.setattr(
        multi_target_module,
        "_minimum_cost_path_cover",
        _alternating_cover,
    )
    result = associate_multi_target_observations(
        observations,
        config=_config(maximum_assignment_iterations=2),
    )
    assert result.converged is False
    assert result.assignment_iterations == 2
    assert result.status is StandardScientificStatus.INSUFFICIENT_DATA
    assert "did not converge" in result.reason
