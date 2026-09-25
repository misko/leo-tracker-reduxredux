from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path
from types import ModuleType
from typing import Any, Literal

import pytest

from leo.contracts.digests import canonical_digest  # type: ignore[import-untyped]


def _tool() -> ModuleType:
    path = (
        Path(__file__).parents[2] / "tools/calibrate_raw_satellite_activity_structural_penalties.py"
    )
    spec = importlib.util.spec_from_file_location(
        "calibrate_raw_satellite_activity_structural_penalties_tool",
        path,
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _identity(label: str) -> str:
    return "sha256:" + hashlib.sha256(label.encode()).hexdigest()


def _write(path: Path, value: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return path


def _search_configuration(
    tool: ModuleType,
    member_id: str,
    pair_index: int,
    satellite_cost: float,
    episode_cost: float,
) -> dict[str, Any]:
    return {
        "algorithm": "starlink-full-window-coarse-to-fine-v1",
        "output_schema": tool.REPLAY_SCHEMA,
        "null_certificate_algorithm": tool.NULL_CERTIFICATE_ALGORITHM,
        "sky_frequency_hz": 10e9,
        "member_evaluation_scope_digest": _identity(f"scope:{member_id}"),
        "producer_implementation": {
            "algorithm": "fixture-producer-manifest-v1",
            "files": [{"path": "fixture.py", "digest": _identity("fixture-code")}],
        },
        "window": {
            "start_s": 0.0,
            "end_s": 1.0,
            "duration_s": 1.0,
            "scheduled_probe_count": 10,
            "cell_count": 10,
        },
        "catalogue_screen": {"final_catalog_count": 3},
        "pair_index_not_used_by_search": pair_index,
        "raw_replay": {
            "cell_duration_s": 0.1,
            "minimum_active_duration_s": 0.5,
            "satellite_cost": satellite_cost,
            "episode_cost": episode_cost,
        },
    }


def _member(
    tool: ModuleType,
    member_id: str,
    pairs: list[tuple[float, float]],
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    configurations = [
        _search_configuration(tool, member_id, index, satellite_cost, episode_cost)
        for index, (satellite_cost, episode_cost) in enumerate(pairs)
    ]
    family_digests = {
        tool.search_configuration_family_digest(configuration) for configuration in configurations
    }
    # The pair index is intentionally not a structural setting and would make
    # this family invalid.  Remove it in the fixture configurations.
    assert len(family_digests) == len(pairs)
    for configuration in configurations:
        del configuration["pair_index_not_used_by_search"]
    family_digests = {
        tool.search_configuration_family_digest(configuration) for configuration in configurations
    }
    assert len(family_digests) == 1
    return (
        {
            "member_id": member_id,
            "duration_dataset_digest": _identity(f"duration:{member_id}"),
            "pilot_scan_digest": _identity(f"pilot:{member_id}"),
            "member_evaluation_scope_digest": _identity(f"scope:{member_id}"),
            "search_configuration_family_digest": next(iter(family_digests)),
            "search_configuration_digests": [
                {"pair_index": index, "digest": canonical_digest(configuration)}
                for index, configuration in enumerate(configurations)
            ],
        },
        configurations,
    )


def _cluster(
    tool: ModuleType,
    cluster_id: str,
    member_ids: tuple[str, ...],
    pairs: list[tuple[float, float]],
) -> tuple[dict[str, Any], dict[str, tuple[dict[str, Any], list[dict[str, Any]]]]]:
    members = {member_id: _member(tool, member_id, pairs) for member_id in member_ids}
    return (
        {
            "cluster_id": cluster_id,
            "source_provenance_ids": [f"capture:{cluster_id}"],
            "members": [members[member_id][0] for member_id in member_ids],
        },
        members,
    )


def _replay(
    tool: ModuleType,
    member: dict[str, Any],
    configuration: dict[str, Any],
    status: Literal["activation", "certified_null", "inconclusive"],
) -> dict[str, Any]:
    selected = [60000] if status == "activation" else []
    delta = -3.0 if status == "activation" else 0.0
    elided_constant = 2.0
    modeled_null_cost = 8.0
    null_cost = modeled_null_cost + elided_constant
    solved = status != "inconclusive"
    certificate: dict[str, Any] | None = None
    result_kind = "catalogue_screened_grouped_activity"
    if status == "certified_null":
        result_kind = "certified_null"
        certificate = {
            "algorithm": tool.NULL_CERTIFICATE_ALGORITHM,
            "certified": True,
            "modeled_null_cost": modeled_null_cost,
            "optimistic_selected": False,
            "optimistic_delta_from_null": 0.0,
            "active_cell_count": 0,
            "episode_count": 0,
            "assignment_count": 0,
        }
    objective = {
        "null_cost": null_cost,
        "total_cost": null_cost + delta,
        "delta_from_null": delta,
        "constant_elided_from_exact_decision_problem": elided_constant,
    }
    association_objective = {
        "null_cost": null_cost if status == "certified_null" else modeled_null_cost,
        "total_cost": (
            null_cost + delta if status == "certified_null" else modeled_null_cost + delta
        ),
        "delta_from_null": delta,
    }
    association = (
        {
            "selected_catalog_numbers": [],
            "selected_satellite_count": 0,
            "objective": association_objective,
        }
        if status == "certified_null"
        else {
            "association": {
                "selected_catalog_numbers": selected,
                "objective": association_objective,
            }
        }
    )
    raw_inventory: dict[str, Any] = {
        "declared_post_acquisition_inventory_complete": True,
        "truncated_candidate_count": 0,
    }
    if status == "certified_null":
        raw_inventory["omitted_clutter_objective_constant"] = elided_constant
    else:
        raw_inventory["dominated_weak_candidate_elision"] = {
            "omitted_clutter_objective_constant": elided_constant,
        }
    document = {
        "schema": tool.REPLAY_SCHEMA,
        "candidate_only": True,
        "specificity_claimed": False,
        "payload_decoded": False,
        "structural_costs_calibrated": False,
        "unknown_satellite_count_solved": False,
        "global_optimum_claimed": False,
        "null_vs_any_activation_solved": solved,
        "catalogue_search_performed": status != "certified_null",
        "catalogue_search_avoided_by_global_null_certificate": status == "certified_null",
        "catalogue_search_exact": False,
        "raw_inventory": raw_inventory,
        "input": {
            "duration_dataset_digest": member["duration_dataset_digest"],
            "pilot_scan_digest": member["pilot_scan_digest"],
        },
        "configuration": configuration["raw_replay"],
        "search_configuration": configuration,
        "search_configuration_digest": canonical_digest(configuration),
        "null_certificate": certificate,
        "association": association,
        "joint_search": (
            {"selected_catalog_numbers": selected} if status != "certified_null" else None
        ),
        "decision": {
            "result_kind": result_kind,
            "selected_catalog_numbers": selected,
            "selected_satellite_count": len(selected),
            "full_persisted_inventory_objective": objective,
        },
    }
    if status != "certified_null":
        document["full_persisted_inventory_objective"] = objective
    return document


class _Study:
    def __init__(self, tool: ModuleType, tmp_path: Path) -> None:
        self.tool = tool
        self.tmp_path = tmp_path
        self.pairs = [(1.0, 1.0), (5.25, 5.75)]
        tuning_rows: list[dict[str, Any]] = []
        holdout_rows: list[dict[str, Any]] = []
        unused_rows: list[dict[str, Any]] = []
        self.members: dict[str, tuple[dict[str, Any], list[dict[str, Any]]]] = {}

        row, members = _cluster(tool, "tuning-a", ("tuning-a-rx0",), self.pairs)
        tuning_rows.append(row)
        self.members.update(members)
        row, members = _cluster(
            tool,
            "tuning-b",
            ("tuning-b-rx0", "tuning-b-rx1"),
            self.pairs,
        )
        tuning_rows.append(row)
        self.members.update(members)
        for index in range(13):
            cluster_id = f"tuning-extra-{index:02d}"
            member_id = f"{cluster_id}-rx0"
            row, members = _cluster(tool, cluster_id, (member_id,), self.pairs)
            tuning_rows.append(row)
            self.members.update(members)
        for index in range(59):
            cluster_id = f"holdout-{index:02d}"
            member_id = f"{cluster_id}-rx0"
            row, members = _cluster(tool, cluster_id, (member_id,), self.pairs)
            holdout_rows.append(row)
            self.members.update(members)
        for index in range(2):
            cluster_id = f"unused-{index}"
            row, members = _cluster(tool, cluster_id, (f"{cluster_id}-rx0",), self.pairs)
            unused_rows.append(row)
            self.members.update(members)

        self.plan = {
            "schema": tool.PLAN_SCHEMA,
            "study_id": "frozen-null-study",
            "controlled_study_family_digest": (
                tool.controlled_study_configuration_family_digest(
                    next(iter(self.members.values()))[1][0]
                )
            ),
            "ordered_penalty_pairs": [
                {
                    "pair_index": index,
                    "satellite_cost": satellite_cost,
                    "episode_cost": episode_cost,
                }
                for index, (satellite_cost, episode_cost) in enumerate(self.pairs)
            ],
            "qualification": {
                "interval_method": tool.INTERVAL_METHOD,
                "required_holdout_cluster_count": 59,
                "confidence_level": 0.95,
                "maximum_false_activation_rate": 0.05,
            },
            "splits": {
                "tuning": {"clusters": tuning_rows},
                "holdout": {"predeclared": True, "clusters": holdout_rows},
                "unused": {"clusters": unused_rows},
            },
        }
        self.plan_path = _write(tmp_path / "plan.json", self.plan)

    def _member_for(self, cluster_id: str, member_id: str) -> dict[str, Any]:
        del cluster_id
        return self.members[member_id][0]

    def index(
        self,
        split: Literal["tuning", "holdout"],
        pair_indices: tuple[int, ...],
        outcomes: dict[tuple[str, str, int], str],
        *,
        lock_digest: str | None = None,
    ) -> Path:
        clusters = self.plan["splits"][split]["clusters"]
        entries: list[dict[str, Any]] = []
        for cluster in clusters:
            for member in cluster["members"]:
                member_id = member["member_id"]
                for pair_index in pair_indices:
                    configuration = self.members[member_id][1][pair_index]
                    status = outcomes.get(
                        (cluster["cluster_id"], member_id, pair_index), "certified_null"
                    )
                    replay_path = _write(
                        self.tmp_path
                        / "replays"
                        / f"{split}-{cluster['cluster_id']}-{member_id}-{pair_index}.json",
                        _replay(
                            self.tool,
                            self._member_for(cluster["cluster_id"], member_id),
                            configuration,
                            status,  # type: ignore[arg-type]
                        ),
                    )
                    entries.append(
                        {
                            "cluster_id": cluster["cluster_id"],
                            "member_id": member_id,
                            "pair_index": pair_index,
                            "replay_path": str(replay_path),
                            "replay_file_digest": _digest(replay_path),
                        }
                    )
        return _write(
            self.tmp_path / f"{split}-index.json",
            {
                "schema": self.tool.EVIDENCE_INDEX_SCHEMA,
                "study_id": self.plan["study_id"],
                "plan_digest": _digest(self.plan_path),
                "split": split,
                "lock_digest": lock_digest,
                "entries": entries,
            },
        )

    def lock(self) -> tuple[dict[str, Any], Path]:
        tuning_index = self.index(
            "tuning",
            (0, 1),
            {
                ("tuning-a", "tuning-a-rx0", 0): "activation",
                ("tuning-b", "tuning-b-rx0", 0): "inconclusive",
                ("tuning-b", "tuning-b-rx1", 0): "activation",
            },
        )
        result = self.tool.lock_penalty_pair(
            plan_path=self.plan_path,
            expected_plan_digest=_digest(self.plan_path),
            evidence_index_path=tuning_index,
            expected_evidence_index_digest=_digest(tuning_index),
        )
        lock_path = _write(self.tmp_path / "lock.json", result)
        return result, lock_path


def test_exact_one_sided_95_percent_binomial_gate_has_the_59_cluster_boundary() -> None:
    tool = _tool()
    at_59 = tool.exact_one_sided_binomial_upper(0, 59)
    at_58 = tool.exact_one_sided_binomial_upper(0, 58)
    assert at_59 == pytest.approx(0.04950759524247663)
    assert at_59 < 0.05
    assert at_58 > 0.05
    assert tool.exact_one_sided_binomial_upper(59, 59) == 1.0
    with pytest.raises(ValueError, match="0 <= false activations"):
        tool.exact_one_sided_binomial_upper(2, 1)


def test_locks_first_complete_tuning_null_then_qualifies_zero_of_59(tmp_path: Path) -> None:
    tool = _tool()
    study = _Study(tool, tmp_path)
    lock, lock_path = study.lock()

    assert lock["holdout_evidence_inspected"] is False
    assert lock["predeclared_split_accounting"] == {
        "tuning_cluster_count": 15,
        "holdout_cluster_count": 59,
        "unused_cluster_count": 2,
    }
    assert lock["candidate_evaluations"][0]["cluster_accounting"] == {
        "cluster_count": 15,
        "false_activation_count": 2,
        "certified_null_count": 13,
        "inconclusive_count": 0,
    }
    # Any activation wins at cluster level even when another member is inconclusive.
    tuning_b = lock["candidate_evaluations"][0]["clusters"][1]
    assert tuning_b["status"] == "false_activation"
    assert tuning_b["all_members_certified_null"] is False
    assert lock["decision"]["locked_pair_index"] == 1
    assert lock["decision"]["locked_penalty_pair"]["satellite_cost"] == 5.25

    holdout_index = study.index("holdout", (1,), {}, lock_digest=_digest(lock_path))
    result = tool.qualify_locked_penalty(
        plan_path=study.plan_path,
        expected_plan_digest=_digest(study.plan_path),
        lock_path=lock_path,
        expected_lock_digest=_digest(lock_path),
        evidence_index_path=holdout_index,
        expected_evidence_index_digest=_digest(holdout_index),
    )
    assert result["holdout_pair_indices_inspected"] == [1]
    assert result["holdout_cluster_accounting"] == {
        "cluster_count": 59,
        "false_activation_count": 0,
        "certified_null_count": 59,
        "inconclusive_count": 0,
    }
    assert result["false_activation_rate_gate"]["exact_one_sided_upper_bound"] == pytest.approx(
        0.04950759524247663
    )
    assert result["decision"] == {
        "status": "qualified",
        "qualified": True,
        "structural_costs_calibrated_for_declared_empirical_null_scope": True,
    }


def test_holdout_inconclusive_is_not_dropped_from_the_denominator(tmp_path: Path) -> None:
    tool = _tool()
    study = _Study(tool, tmp_path)
    _, lock_path = study.lock()
    holdout_index = study.index(
        "holdout",
        (1,),
        {("holdout-00", "holdout-00-rx0", 1): "inconclusive"},
        lock_digest=_digest(lock_path),
    )
    result = tool.qualify_locked_penalty(
        plan_path=study.plan_path,
        expected_plan_digest=_digest(study.plan_path),
        lock_path=lock_path,
        expected_lock_digest=_digest(lock_path),
        evidence_index_path=holdout_index,
        expected_evidence_index_digest=_digest(holdout_index),
    )
    assert result["holdout_cluster_accounting"]["cluster_count"] == 59
    assert result["holdout_cluster_accounting"]["inconclusive_count"] == 1
    assert result["false_activation_rate_gate"]["exact_one_sided_upper_bound"] is None
    assert result["decision"]["status"] == "inconclusive"
    assert result["decision"]["qualified"] is False


def test_any_holdout_activation_fails_the_exact_rate_gate(tmp_path: Path) -> None:
    tool = _tool()
    study = _Study(tool, tmp_path)
    _, lock_path = study.lock()
    holdout_index = study.index(
        "holdout",
        (1,),
        {("holdout-00", "holdout-00-rx0", 1): "activation"},
        lock_digest=_digest(lock_path),
    )
    result = tool.qualify_locked_penalty(
        plan_path=study.plan_path,
        expected_plan_digest=_digest(study.plan_path),
        lock_path=lock_path,
        expected_lock_digest=_digest(lock_path),
        evidence_index_path=holdout_index,
        expected_evidence_index_digest=_digest(holdout_index),
    )
    assert result["holdout_cluster_accounting"]["false_activation_count"] == 1
    assert result["false_activation_rate_gate"]["exact_one_sided_upper_bound"] > 0.05
    assert result["false_activation_rate_gate"]["failure_certain_under_best_case"] is True
    assert result["decision"]["status"] == "failed_false_activation_rate_gate"
    assert result["decision"]["qualified"] is False


def test_missing_or_wrong_pair_holdout_evidence_is_refused(tmp_path: Path) -> None:
    tool = _tool()
    study = _Study(tool, tmp_path)
    _, lock_path = study.lock()
    wrong_index = study.index("holdout", (0,), {}, lock_digest=_digest(lock_path))
    with pytest.raises(ValueError, match="coverage mismatch"):
        tool.qualify_locked_penalty(
            plan_path=study.plan_path,
            expected_plan_digest=_digest(study.plan_path),
            lock_path=lock_path,
            expected_lock_digest=_digest(lock_path),
            evidence_index_path=wrong_index,
            expected_evidence_index_digest=_digest(wrong_index),
        )

    tuning_index = study.index("tuning", (0, 1), {})
    index_document = json.loads(tuning_index.read_text())
    index_document["entries"].pop()
    _write(tuning_index, index_document)
    with pytest.raises(ValueError, match="coverage mismatch"):
        tool.lock_penalty_pair(
            plan_path=study.plan_path,
            expected_plan_digest=_digest(study.plan_path),
            evidence_index_path=tuning_index,
            expected_evidence_index_digest=_digest(tuning_index),
        )


def test_replay_bytes_and_search_configuration_are_both_tamper_evident(tmp_path: Path) -> None:
    tool = _tool()
    study = _Study(tool, tmp_path)
    tuning_index = study.index("tuning", (0, 1), {})
    index_document = json.loads(tuning_index.read_text())
    replay_path = Path(index_document["entries"][0]["replay_path"])

    replay = json.loads(replay_path.read_text())
    replay["decision"]["selected_satellite_count"] = 7
    _write(replay_path, replay)
    with pytest.raises(ValueError, match="replay file digest mismatch"):
        tool.lock_penalty_pair(
            plan_path=study.plan_path,
            expected_plan_digest=_digest(study.plan_path),
            evidence_index_path=tuning_index,
            expected_evidence_index_digest=_digest(tuning_index),
        )

    replay = _replay(
        tool,
        study.members["tuning-a-rx0"][0],
        deepcopy(study.members["tuning-a-rx0"][1][0]),
        "certified_null",
    )
    replay["search_configuration"]["raw_replay"]["cell_duration_s"] = 0.2
    _write(replay_path, replay)
    index_document["entries"][0]["replay_file_digest"] = _digest(replay_path)
    _write(tuning_index, index_document)
    with pytest.raises(ValueError, match="internally inconsistent"):
        tool.lock_penalty_pair(
            plan_path=study.plan_path,
            expected_plan_digest=_digest(study.plan_path),
            evidence_index_path=tuning_index,
            expected_evidence_index_digest=_digest(tuning_index),
        )


def test_full_and_cost_stripped_search_digests_are_independently_bound(tmp_path: Path) -> None:
    tool = _tool()
    study = _Study(tool, tmp_path)
    tuning_index = study.index("tuning", (0, 1), {})
    index_document = json.loads(tuning_index.read_text())
    entry = index_document["entries"][0]
    replay_path = Path(entry["replay_path"])
    replay = json.loads(replay_path.read_text())
    replay["search_configuration"]["member_bound_search_scope"] = "changed-noncost-setting"
    replay["search_configuration_digest"] = canonical_digest(replay["search_configuration"])
    _write(replay_path, replay)
    entry["replay_file_digest"] = _digest(replay_path)
    _write(tuning_index, index_document)
    with pytest.raises(ValueError, match="full search configuration was not predeclared"):
        tool.lock_penalty_pair(
            plan_path=study.plan_path,
            expected_plan_digest=_digest(study.plan_path),
            evidence_index_path=tuning_index,
            expected_evidence_index_digest=_digest(tuning_index),
        )

    # Even if the plan's full digest is coherently updated, the independently
    # frozen cost-stripped family digest still rejects the changed search.
    plan = json.loads(study.plan_path.read_text())
    plan["splits"]["tuning"]["clusters"][0]["members"][0]["search_configuration_digests"][0][
        "digest"
    ] = replay["search_configuration_digest"]
    _write(study.plan_path, plan)
    index_document["plan_digest"] = _digest(study.plan_path)
    _write(tuning_index, index_document)
    with pytest.raises(ValueError, match="search configuration family mismatch"):
        tool.lock_penalty_pair(
            plan_path=study.plan_path,
            expected_plan_digest=_digest(study.plan_path),
            evidence_index_path=tuning_index,
            expected_evidence_index_digest=_digest(tuning_index),
        )


def test_plan_refuses_split_source_overlap_and_nonpredeclared_holdout(tmp_path: Path) -> None:
    tool = _tool()
    study = _Study(tool, tmp_path)
    overlap = deepcopy(study.plan)
    overlap["splits"]["holdout"]["clusters"][0]["source_provenance_ids"] = ["capture:tuning-a"]
    with pytest.raises(ValueError, match="source provenance"):
        tool.parse_plan(overlap)

    reused_scan = deepcopy(study.plan)
    reused_scan["splits"]["holdout"]["clusters"][0]["members"][0]["pilot_scan_digest"] = (
        reused_scan["splits"]["tuning"]["clusters"][0]["members"][0]["pilot_scan_digest"]
    )
    with pytest.raises(ValueError, match="source provenance"):
        tool.parse_plan(reused_scan)

    not_predeclared = deepcopy(study.plan)
    not_predeclared["splits"]["holdout"]["predeclared"] = False
    with pytest.raises(ValueError, match="predeclared"):
        tool.parse_plan(not_predeclared)

    wrong_tuning_count = deepcopy(study.plan)
    wrong_tuning_count["splits"]["tuning"]["clusters"].pop()
    with pytest.raises(ValueError, match="exactly 15"):
        tool.parse_plan(wrong_tuning_count)

    incomparable_penalties = deepcopy(study.plan)
    incomparable_penalties["ordered_penalty_pairs"] = [
        {"pair_index": 0, "satellite_cost": 1.0, "episode_cost": 3.0},
        {"pair_index": 1, "satellite_cost": 2.0, "episode_cost": 2.0},
    ]
    with pytest.raises(ValueError, match="componentwise nondecreasing"):
        tool.parse_plan(incomparable_penalties)


def test_controlled_family_rejects_coherently_shifted_member_window(tmp_path: Path) -> None:
    tool = _tool()
    study = _Study(tool, tmp_path)
    tuning_index = study.index("tuning", (0, 1), {})
    index_document = json.loads(tuning_index.read_text())
    plan = json.loads(study.plan_path.read_text())
    plan_member = plan["splits"]["tuning"]["clusters"][0]["members"][0]
    shifted_scope = _identity("shifted-scope:tuning-a-rx0")
    shifted_family: str | None = None

    for entry in index_document["entries"]:
        if entry["cluster_id"] != "tuning-a" or entry["member_id"] != "tuning-a-rx0":
            continue
        replay_path = Path(entry["replay_path"])
        replay = json.loads(replay_path.read_text())
        configuration = replay["search_configuration"]
        configuration["window"]["start_s"] = 0.1
        configuration["window"]["end_s"] = 1.1
        configuration["member_evaluation_scope_digest"] = shifted_scope
        replay["search_configuration_digest"] = canonical_digest(configuration)
        _write(replay_path, replay)
        entry["replay_file_digest"] = _digest(replay_path)
        pair_index = entry["pair_index"]
        plan_member["search_configuration_digests"][pair_index]["digest"] = replay[
            "search_configuration_digest"
        ]
        observed_family = tool.search_configuration_family_digest(configuration)
        shifted_family = observed_family if shifted_family is None else shifted_family
        assert shifted_family == observed_family

    assert shifted_family is not None
    plan_member["member_evaluation_scope_digest"] = shifted_scope
    plan_member["search_configuration_family_digest"] = shifted_family
    _write(study.plan_path, plan)
    index_document["plan_digest"] = _digest(study.plan_path)
    _write(tuning_index, index_document)

    with pytest.raises(ValueError, match="controlled study search family mismatch"):
        tool.lock_penalty_pair(
            plan_path=study.plan_path,
            expected_plan_digest=_digest(study.plan_path),
            evidence_index_path=tuning_index,
            expected_evidence_index_digest=_digest(tuning_index),
        )


def test_replay_branches_reconcile_association_and_certificate_algorithm(tmp_path: Path) -> None:
    tool = _tool()
    study = _Study(tool, tmp_path)
    tuning_index = study.index("tuning", (0, 1), {})
    index_document = json.loads(tuning_index.read_text())
    entry = index_document["entries"][0]
    replay_path = Path(entry["replay_path"])
    replay = json.loads(replay_path.read_text())
    replay["association"]["selected_catalog_numbers"] = [60000]
    replay["association"]["selected_satellite_count"] = 1
    _write(replay_path, replay)
    entry["replay_file_digest"] = _digest(replay_path)
    _write(tuning_index, index_document)
    with pytest.raises(ValueError, match="null association contains"):
        tool.lock_penalty_pair(
            plan_path=study.plan_path,
            expected_plan_digest=_digest(study.plan_path),
            evidence_index_path=tuning_index,
            expected_evidence_index_digest=_digest(tuning_index),
        )


def test_replay_objective_constant_location_is_strictly_branch_specific(
    tmp_path: Path,
) -> None:
    tool = _tool()
    study = _Study(tool, tmp_path)
    _, lock_path = study.lock()

    active_index = study.index(
        "holdout",
        (1,),
        {("holdout-00", "holdout-00-rx0", 1): "activation"},
        lock_digest=_digest(lock_path),
    )
    active_document = json.loads(active_index.read_text())
    active_entry = active_document["entries"][0]
    active_path = Path(active_entry["replay_path"])
    active_replay = json.loads(active_path.read_text())
    active_replay["raw_inventory"]["omitted_clutter_objective_constant"] = 2.0
    _write(active_path, active_replay)
    active_entry["replay_file_digest"] = _digest(active_path)
    _write(active_index, active_document)
    with pytest.raises(ValueError, match="catalogue-screen raw objective constant"):
        tool.qualify_locked_penalty(
            plan_path=study.plan_path,
            expected_plan_digest=_digest(study.plan_path),
            lock_path=lock_path,
            expected_lock_digest=_digest(lock_path),
            evidence_index_path=active_index,
            expected_evidence_index_digest=_digest(active_index),
        )

    null_index = study.index("holdout", (1,), {}, lock_digest=_digest(lock_path))
    null_document = json.loads(null_index.read_text())
    null_entry = null_document["entries"][0]
    null_path = Path(null_entry["replay_path"])
    null_replay = json.loads(null_path.read_text())
    null_replay["raw_inventory"]["dominated_weak_candidate_elision"] = {
        "omitted_clutter_objective_constant": 2.0,
    }
    _write(null_path, null_replay)
    null_entry["replay_file_digest"] = _digest(null_path)
    _write(null_index, null_document)
    with pytest.raises(ValueError, match="certified-null raw objective constant"):
        tool.qualify_locked_penalty(
            plan_path=study.plan_path,
            expected_plan_digest=_digest(study.plan_path),
            lock_path=lock_path,
            expected_lock_digest=_digest(lock_path),
            evidence_index_path=null_index,
            expected_evidence_index_digest=_digest(null_index),
        )

    tuning_index = study.index("tuning", (0, 1), {})
    index_document = json.loads(tuning_index.read_text())
    entry = index_document["entries"][0]
    replay_path = Path(entry["replay_path"])
    replay = json.loads(replay_path.read_text())
    replay["null_certificate"]["algorithm"] = "forged-null-proof-v1"
    _write(replay_path, replay)
    entry["replay_file_digest"] = _digest(replay_path)
    _write(tuning_index, index_document)
    with pytest.raises(ValueError, match="internally inconsistent"):
        tool.lock_penalty_pair(
            plan_path=study.plan_path,
            expected_plan_digest=_digest(study.plan_path),
            evidence_index_path=tuning_index,
            expected_evidence_index_digest=_digest(tuning_index),
        )


def test_qualification_recomputes_coherently_tampered_lock(tmp_path: Path) -> None:
    tool = _tool()
    study = _Study(tool, tmp_path)
    lock, lock_path = study.lock()
    tampered = deepcopy(lock)
    first = tampered["candidate_evaluations"][0]
    first["eligible_for_lock"] = True
    first["cluster_accounting"] = {
        "cluster_count": 15,
        "false_activation_count": 0,
        "certified_null_count": 15,
        "inconclusive_count": 0,
    }
    tampered["decision"] = {
        "locked": True,
        "locked_pair_index": 0,
        "locked_penalty_pair": tampered["ordered_penalty_pairs"][0],
        "reason": "first_ordered_pair_passing_complete_tuning_null_gate",
    }
    _write(lock_path, tampered)
    holdout_index = study.index("holdout", (0,), {}, lock_digest=_digest(lock_path))

    with pytest.raises(ValueError, match="canonical tuning-evidence adjudication"):
        tool.qualify_locked_penalty(
            plan_path=study.plan_path,
            expected_plan_digest=_digest(study.plan_path),
            lock_path=lock_path,
            expected_lock_digest=_digest(lock_path),
            evidence_index_path=holdout_index,
            expected_evidence_index_digest=_digest(holdout_index),
        )


def test_known_activation_dominates_other_inconclusive_holdout_cluster(tmp_path: Path) -> None:
    tool = _tool()
    study = _Study(tool, tmp_path)
    _, lock_path = study.lock()
    holdout_index = study.index(
        "holdout",
        (1,),
        {
            ("holdout-00", "holdout-00-rx0", 1): "activation",
            ("holdout-01", "holdout-01-rx0", 1): "inconclusive",
        },
        lock_digest=_digest(lock_path),
    )
    result = tool.qualify_locked_penalty(
        plan_path=study.plan_path,
        expected_plan_digest=_digest(study.plan_path),
        lock_path=lock_path,
        expected_lock_digest=_digest(lock_path),
        evidence_index_path=holdout_index,
        expected_evidence_index_digest=_digest(holdout_index),
    )
    assert result["holdout_cluster_accounting"]["false_activation_count"] == 1
    assert result["holdout_cluster_accounting"]["inconclusive_count"] == 1
    assert result["false_activation_rate_gate"]["exact_one_sided_upper_bound"] is None
    assert result["false_activation_rate_gate"]["best_case_exact_one_sided_upper_bound"] > 0.05
    assert result["false_activation_rate_gate"]["failure_certain_under_best_case"] is True
    assert result["decision"]["status"] == "failed_false_activation_rate_gate"


def test_plan_and_lock_external_digest_bindings_fail_closed(tmp_path: Path) -> None:
    tool = _tool()
    study = _Study(tool, tmp_path)
    _, lock_path = study.lock()
    holdout_index = study.index("holdout", (1,), {}, lock_digest=_digest(lock_path))

    with pytest.raises(ValueError, match="plan digest mismatch"):
        tool.qualify_locked_penalty(
            plan_path=study.plan_path,
            expected_plan_digest=_identity("wrong-plan"),
            lock_path=lock_path,
            expected_lock_digest=_digest(lock_path),
            evidence_index_path=holdout_index,
            expected_evidence_index_digest=_digest(holdout_index),
        )
    with pytest.raises(ValueError, match="penalty lock digest mismatch"):
        tool.qualify_locked_penalty(
            plan_path=study.plan_path,
            expected_plan_digest=_digest(study.plan_path),
            lock_path=lock_path,
            expected_lock_digest=_identity("wrong-lock"),
            evidence_index_path=holdout_index,
            expected_evidence_index_digest=_digest(holdout_index),
        )
