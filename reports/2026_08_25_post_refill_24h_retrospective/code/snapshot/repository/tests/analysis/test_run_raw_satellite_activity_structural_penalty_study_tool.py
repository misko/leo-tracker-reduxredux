from __future__ import annotations

import json
import shutil
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from tests.analysis.test_calibrate_raw_satellite_activity_structural_penalties_tool import (
    _replay,
)
from tests.analysis.test_freeze_raw_satellite_activity_structural_penalty_plan_tool import (
    _Corpus,
    _digest,
    _write,
)
from tools import calibrate_raw_satellite_activity_structural_penalties as adjudicator
from tools import run_raw_satellite_activity_structural_penalty_study as runner


class _CertifiedNullScreen:
    def __init__(self, plan_document: dict[str, Any]) -> None:
        self.plan = adjudicator.parse_plan(plan_document)
        execution = runner._execution_inputs(plan_document)
        self.runnable_by_path: dict[Path, runner.RunnableMember] = {}
        for split in ("tuning", "holdout"):
            pair_indices = tuple(pair.pair_index for pair in self.plan.pairs)
            members = runner._preflight_members(
                plan_document=plan_document,
                plan=self.plan,
                split=split,
                pair_indices=pair_indices,
                execution=execution,
            )
            self.runnable_by_path.update({item.dataset_path: item for item in members})
        self.calls: list[tuple[str, int]] = []

    def __call__(self, **arguments: Any) -> dict[str, Any]:
        runnable = self.runnable_by_path[Path(arguments["dataset_path"]).resolve()]
        configuration = arguments["config"]
        pair = next(
            item
            for item in self.plan.pairs
            if item.satellite_cost == configuration.satellite_cost
            and item.episode_cost == configuration.episode_cost
        )
        self.calls.append((runnable.member.member_id, pair.pair_index))
        member_document = {
            "duration_dataset_digest": runnable.member.duration_dataset_digest,
            "pilot_scan_digest": runnable.member.pilot_scan_digest,
        }
        return _replay(
            adjudicator,
            member_document,
            runnable.expected_search_configurations[pair.pair_index],
            "certified_null",
        )


def _frozen_plan(tmp_path: Path) -> tuple[dict[str, Any], Path, str, _CertifiedNullScreen]:
    corpus = _Corpus(tmp_path / "corpus")
    document = corpus.build()
    path = _write(tmp_path / "frozen-plan.json", document)
    return document, path, _digest(path), _CertifiedNullScreen(document)


def test_tuning_runs_every_member_pair_and_index_survives_relocation(tmp_path: Path) -> None:
    plan_document, plan_path, plan_digest, screen = _frozen_plan(tmp_path)
    relocated_plan = tmp_path / "relocated-plan" / "frozen-plan.json"
    relocated_plan.parent.mkdir(parents=True)
    shutil.copyfile(plan_path, relocated_plan)

    output_root = tmp_path / "evidence"
    index_path, index_document = runner.run_study_split(
        plan_path=relocated_plan,
        expected_plan_digest=plan_digest,
        split="tuning",
        output_root=output_root,
        screen_function=screen,
    )

    assert len(screen.calls) == 16 * 2
    assert len(index_document["entries"]) == 16 * 2
    assert {item["pair_index"] for item in index_document["entries"]} == {0, 1}
    assert all(not Path(item["replay_path"]).is_absolute() for item in index_document["entries"])

    # Re-use is deterministic and does not invoke the scientific producer again.
    _, repeated = runner.run_study_split(
        plan_path=relocated_plan,
        expected_plan_digest=plan_digest,
        split="tuning",
        output_root=output_root,
        screen_function=screen,
    )
    assert repeated == index_document
    assert len(screen.calls) == 16 * 2

    relocated_output = tmp_path / "relocated-evidence"
    shutil.move(output_root, relocated_output)
    relocated_index_path = relocated_output / index_path.name
    parsed_plan = adjudicator.parse_plan(plan_document)
    entries = adjudicator._parse_evidence_index(
        json.loads(relocated_index_path.read_text(encoding="utf-8")),
        index_path=relocated_index_path,
        plan=parsed_plan,
        plan_digest=plan_digest,
        split="tuning",
        pair_indices=(0, 1),
        lock_digest=None,
    )
    assert len(entries) == 16 * 2


def test_refuses_duration_tamper_and_execution_drift_before_screen(tmp_path: Path) -> None:
    plan_document, plan_path, plan_digest, screen = _frozen_plan(tmp_path)
    first_member = plan_document["splits"]["tuning"]["clusters"][0]["members"][0]
    Path(first_member["duration_dataset_path"]).write_text("{}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duration dataset digest mismatch"):
        runner.run_study_split(
            plan_path=plan_path,
            expected_plan_digest=plan_digest,
            split="tuning",
            output_root=tmp_path / "tampered-output",
            screen_function=screen,
        )
    assert screen.calls == []

    plan_document, _, _, screen = _frozen_plan(tmp_path / "drift")
    drifted = deepcopy(plan_document)
    drifted["execution_inputs"]["raw_replay_without_structural_costs"][
        "minimum_active_duration_s"
    ] = 0.2
    drifted_path = _write(tmp_path / "drifted-plan.json", drifted)
    with pytest.raises(ValueError, match="no longer match the predeclared search digest"):
        runner.run_study_split(
            plan_path=drifted_path,
            expected_plan_digest=_digest(drifted_path),
            split="tuning",
            output_root=tmp_path / "drifted-output",
            screen_function=screen,
        )
    assert screen.calls == []


def test_holdout_requires_canonical_lock_and_runs_only_locked_pair(tmp_path: Path) -> None:
    _, plan_path, plan_digest, screen = _frozen_plan(tmp_path)
    with pytest.raises(ValueError, match="requires both a penalty lock"):
        runner.run_study_split(
            plan_path=plan_path,
            expected_plan_digest=plan_digest,
            split="holdout",
            output_root=tmp_path / "premature-holdout",
            screen_function=screen,
        )
    assert screen.calls == []

    tuning_index_path, _ = runner.run_study_split(
        plan_path=plan_path,
        expected_plan_digest=plan_digest,
        split="tuning",
        output_root=tmp_path / "tuning-evidence",
        screen_function=screen,
    )
    lock_document = adjudicator.lock_penalty_pair(
        plan_path=plan_path,
        expected_plan_digest=plan_digest,
        evidence_index_path=tuning_index_path,
        expected_evidence_index_digest=_digest(tuning_index_path),
    )
    lock_path = _write(tmp_path / "penalty-lock.json", lock_document)
    tuning_call_count = len(screen.calls)

    _, holdout_index = runner.run_study_split(
        plan_path=plan_path,
        expected_plan_digest=plan_digest,
        split="holdout",
        output_root=tmp_path / "holdout-evidence",
        lock_path=lock_path,
        expected_lock_digest=_digest(lock_path),
        screen_function=screen,
    )

    holdout_calls = screen.calls[tuning_call_count:]
    assert len(holdout_calls) == 59
    assert {pair_index for _, pair_index in holdout_calls} == {0}
    assert len(holdout_index["entries"]) == 59
    assert {item["pair_index"] for item in holdout_index["entries"]} == {0}
    assert holdout_index["lock_digest"] == _digest(lock_path)


def test_refuses_server_and_qnap_output_roots(tmp_path: Path) -> None:
    _, plan_path, plan_digest, screen = _frozen_plan(tmp_path)
    for output_root in (Path("/srv/forbidden-study"), Path("/mnt/qnap01/forbidden-study")):
        with pytest.raises(ValueError, match="refuses output"):
            runner.run_study_split(
                plan_path=plan_path,
                expected_plan_digest=plan_digest,
                split="tuning",
                output_root=output_root,
                screen_function=screen,
            )
    assert screen.calls == []
