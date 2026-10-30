"""Production publication requires actual scoped source and scientific receipts."""

import copy
import os

import pytest
from algo03_production_worker import verify_selected
from algo03_shadow_worker import scientific_receipts, single_candidate, write


def study(root):
    arms = ("c0", "fitted_c")
    write(
        root / "read_receipts/123.json",
        dict(pid=123, parent_pid=os.getpid(), python_spawns=[], denied_paths=[]),
    )
    source = {a: dict(owners={"old": 1}, unreported_postfit_ids=["incidental"]) for a in arms}
    inventory = dict(
        policy={a: dict(proposed_associated_ids=["old", "incidental"]) for a in arms},
        publication_support=source,
    )
    descriptor = root / "snapshot/descriptor.json"
    inv = root / "all-large-track-recovery/job/inventory.json"
    write(descriptor, dict(job_id="job"))
    write(inv, inventory)
    write(
        root / "snapshot/inference/SCAN/observations.json",
        [dict(observation_id=i) for i in ("old", "new", "incidental")],
    )
    support_path = inv.with_name("publication_support.json")
    write(
        support_path,
        dict(
            arms=source, all_verified=True, source_receipts=scientific_receipts([descriptor, inv])
        ),
    )
    trial = root / "target/trial"
    target = dict(norad=2, observation_ids=["new"])
    endpoint = dict(
        endpoint_east_north_km=[0.0, 0.0],
        endpoint_latlon=[37.906, -122.545],
        negative_twice_elbo=900.0,
    )
    write(trial / "protocol.json", dict(targets=[target]))
    write(trial / "control.json", dict(paired_valid=True))
    write(trial / "new_family.json", dict(paired_valid=True, arms={a: endpoint for a in arms}))
    rows = [
        dict(role=r, arm=a, verified=True, owners={"old": 1, "incidental": 3, "new": 2})
        for r in ("control", "new_family")
        for a in arms
    ]
    write(trial / "exact_owner_replay.json", dict(all_verified=True, rows=rows))
    selected = single_candidate(inventory, trial, False)
    return dict(
        selected=selected,
        source_support=source,
        source_support_receipt=scientific_receipts([support_path]),
        read_audit=dict(verified=True),
    )


def test_actual_proof_rebuild_excludes_unreported_postfit_extensions(tmp_path):
    result = study(tmp_path)
    assert result["selected"]["arms"]["c0"]["associated_ids"] == ["new", "old"]
    assert all(verify_selected(result, tmp_path).values())


def test_saved_process_tree_can_be_verified_by_later_reporter(tmp_path):
    result = study(tmp_path)
    result['read_audit'].update(root_process_id=123, supervisor_process_id=999999)
    path = tmp_path / 'read_receipts/123.json'
    import json
    receipt = json.loads(path.read_text())
    receipt['parent_pid'] = 999999
    path.write_text(json.dumps(receipt))
    assert all(verify_selected(result, tmp_path).values())
    result['read_audit']['root_process_id'] = 124
    with pytest.raises(ValueError, match='process receipts'):
        verify_selected(result, tmp_path)


@pytest.mark.parametrize(
    "failure", ["changed_receipt", "extra_support", "missing_source", "bad_audit"]
)
def test_unverified_candidate_falls_back_before_publication(tmp_path, failure):
    result = study(tmp_path)
    if failure == "changed_receipt":
        (tmp_path / "target/trial/control.json").write_text("changed")
    if failure == "extra_support":
        for arm in ("c0", "fitted_c"):
            result["selected"]["arms"][arm]["associated_ids"].append("incidental")
    if failure == "missing_source":
        result.pop("source_support_receipt")
    if failure == "bad_audit":
        result["read_audit"]["verified"] = False
    with pytest.raises(ValueError):
        verify_selected(copy.deepcopy(result), tmp_path)
