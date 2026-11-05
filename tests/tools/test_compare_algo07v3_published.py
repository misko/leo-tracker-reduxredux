import numpy as np
import pytest
from compare_algo07v3_published import exact_persisted, mapped_predictive, read_export


@pytest.fixture
def numerical_additive_documents(tmp_path):
    import hashlib
    from copy import deepcopy

    descriptor = dict(source_worker_root="/old", files={})
    for relative in ("worker/trial/value.json", "worker/cache/value.json"):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"{}")
        descriptor["files"][relative] = "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
    original = dict(
        decision="ALGO03_single",
        selected=dict(
            kind="new_family",
            arms={"c0": {"owners": {"point": 123}, "score": 2.0}},
            targets=["track"],
            trial="/old/trial",
            source_receipts={},
        ),
        attempts=[dict(rejected_score=4.0)],
        stages=[
            dict(name="inventory", status="complete", returncode=0),
            dict(name="target-0-audit", status="complete", returncode=0),
        ],
        source_support={},
        inventory_summary=[],
        eligible_tracks=1,
        selected_track_ids=["track"],
        no_GPS_selection=True,
        causal_only=True,
        matched_c_arms=True,
        rf_checks={"valid": True},
        policy="policy",
        shadow_only=True,
        production_changed=False,
        job_id="id",
        baseline={},
        maximum_seconds=60,
        ranking="ranking",
        limitations=[],
        source_support_receipt={},
        seconds=1,
    )
    scientific = mapped_predictive(original, descriptor, tmp_path)
    excluded = {
        "policy",
        "shadow_only",
        "production_changed",
        "job_id",
        "baseline",
        "maximum_seconds",
        "ranking",
        "limitations",
        "source_support_receipt",
        "seconds",
    }
    scientific = {k: v for k, v in scientific.items() if k not in excluded}
    terminal = dict(
        decision="ALGO04_additive",
        state="complete",
        failure=None,
        future_TLE_used=False,
        matched_c_inputs=True,
        candidate=deepcopy(original),
        acceptance_reason="paired",
    )
    guarded = dict(deepcopy(original), read_audit={"verified": True})
    caches = [
        dict(
            script="script",
            output="/old/trial",
            source="/old/cache",
            reused=reuse,
            reason="reuse" if reuse else "recompute",
            returncode=0,
            wall_seconds=1,
            **({"charged_original_seconds": 2} if reuse else {"command": ["script"]}),
        )
        for reuse in (True, False)
    ]
    policy = dict(
        reference_limit_s=15.0,
        centered_lbfgsb=True,
        extra_optimizer_rounds=1,
        physical_priors_and_target_phase_support_unchanged=True,
        reference_updates=[{"phase": 0.2}],
        optimizer_calls=[{"score": 3.0}],
        problem_count=1,
    )
    receipt = dict(
        policy,
        helper_sha256="h",
        patched_aliases=[],
        restored_aliases=[],
        script="s",
        arguments=[],
        seconds=1,
        script_sha256="s",
        bootstrap_sha256="b",
    )
    replay = [
        dict(
            name=s["name"],
            original_name=s["name"],
            reused=c["reused"],
            reason=c["reason"],
            status="complete",
            **(
                {
                    "charged_original_seconds": 1,
                    "additional_logical_seconds": 0,
                    "reuse_wall_seconds": 1,
                }
                if c["reused"]
                else {}
            ),
        )
        for s, c in zip(original["stages"], caches, strict=True)
    ]
    candidate = dict(
        decision="ALGO04_additive",
        selected=deepcopy(scientific["selected"]),
        retained=deepcopy(scientific),
        candidate=deepcopy(scientific),
        admission_reason="paired",
        completed_target_ids=["track"],
        stage_replay=replay,
        numerical_receipts={"target-0-audit": deepcopy(policy)},
        no_GPS_selection=True,
        causal_only=True,
        matched_c_arms=True,
    )
    return (
        original,
        guarded,
        terminal,
        caches,
        {"target-0-audit": receipt},
        candidate,
        descriptor,
        tmp_path,
    )


@pytest.mark.parametrize(
    "changed",
    [
        None,
        "owner",
        "loser",
        "phase",
        "optimizer",
        "reuse",
        "target",
        "reason",
        "unknown",
        "failed",
        "guarded",
        "branch",
    ],
)
def test_numerical_mapping_checks_all_science_and_original_admission(
    numerical_additive_documents, changed
):
    from compare_algo07v3_published import compare_numerical_recovery

    args = numerical_additive_documents
    original, guarded, terminal, caches, receipts, candidate, descriptor, folder = args
    if changed == "owner":
        candidate["selected"]["arms"]["c0"]["owners"]["point"] = 456
    if changed == "loser":
        candidate["candidate"]["attempts"][0]["rejected_score"] += 1e-12
    if changed == "phase":
        candidate["numerical_receipts"]["target-0-audit"]["reference_updates"][0]["phase"] += 1e-12
    if changed == "optimizer":
        candidate["numerical_receipts"]["target-0-audit"]["optimizer_calls"][0]["score"] += 1e-12
    if changed == "reuse":
        candidate["stage_replay"][0]["reason"] = "different"
    if changed == "target":
        candidate["completed_target_ids"] = []
    if changed == "reason":
        candidate["admission_reason"] = "different"
    if changed == "unknown":
        receipts["target-0-audit"]["unknown"] = True
    if changed == "failed":
        caches[0]["returncode"] = 1
    if changed == "guarded":
        guarded["read_audit"]["verified"] = False
    if changed == "branch":
        terminal["decision"] = "ALGO04_fallback"
    if changed:
        with pytest.raises(ValueError):
            compare_numerical_recovery(*args)
    else:
        compare_numerical_recovery(*args)


@pytest.mark.parametrize("count", [None, 1, 2, 3])
def test_numerical_creation_count_requires_exact_independent_accounting(
    numerical_additive_documents, count
):
    from compare_algo07v3_published import compare_numerical_recovery

    args = numerical_additive_documents
    args[4]["target-0-audit"]["problem_count"] += 2
    kwargs = {} if count is None else dict(context_counts={"target-0-audit": count})
    if count == 2:
        compare_numerical_recovery(*args, **kwargs)
    else:
        with pytest.raises(ValueError):
            compare_numerical_recovery(*args, **kwargs)


@pytest.mark.parametrize(
    "changed", [None, "input", "source", "count", "optimizer", "receipt", "arm"]
)
def test_context_count_oracle_is_bound_and_cannot_hide_numerical_work(tmp_path, changed):
    import hashlib
    import json

    from compare_algo07v3_published import read_context_counts

    folder = tmp_path / "ALGO04"
    (folder / "worker/recovery/numerical-receipts").mkdir(parents=True)
    inventory = folder / "worker/inventory.json"
    inventory.write_bytes(b"{}")
    helper = tmp_path / "helper.py"
    helper.write_bytes(b"# frozen context helper\n")
    def sha(p):
        return hashlib.sha256(p.read_bytes()).hexdigest()
    relative = "worker/recovery/numerical-receipts/target-1-audit.json"
    original = {"helper_sha256": sha(helper)}
    (folder / relative).write_text(json.dumps(original))
    descriptor = dict(
        source_worker_root="/original/worker",
        input_sha256="input",
        files={
            "worker/inventory.json": "sha256:" + sha(inventory),
            relative: "sha256:" + sha(folder / relative),
        },
    )
    dp = folder / "descriptor.json"
    dp.write_text(json.dumps(descriptor))
    row = dict(
        receipt_sha256=sha(folder / relative),
        helper_sha256=sha(helper),
        arms=["c0", "fitted_c"],
        problem_count=2,
        policy_kind="baseline",
        optimizer_calls=[],
        reference_updates=[],
    )
    binding = dict(path=str(helper), sha256=sha(helper))
    value = dict(
        source=str(folder),
        descriptor_sha256=sha(dp),
        input_sha256="input",
        stages={"target-1-audit": row},
        inputs={"worker/inventory.json": sha(inventory)},
        tool=binding,
        modules={"helper": binding},
    )
    if changed == "input":
        inventory.write_bytes(b"changed")
    if changed == "source":
        helper.write_bytes(b"changed")
    if changed == "count":
        row["problem_count"] = 3
    if changed == "optimizer":
        row["optimizer_calls"] = [{"score": 1.0}]
    if changed == "receipt":
        row["receipt_sha256"] = "different"
    if changed == "arm":
        row["arms"] = ["c0", "c0"]
    path = tmp_path / "oracle.json"
    path.write_text(json.dumps(value))
    if changed:
        with pytest.raises(ValueError):
            read_context_counts(path, tmp_path, {"target-1-audit": original})
    else:
        assert read_context_counts(path, tmp_path, {"target-1-audit": original}) == {
            "target-1-audit": 2
        }


@pytest.mark.parametrize(
    "changed", [None, "owners", "prior", "replay", "targets", "unknown", "gap", "kind"]
)
def test_additional_preparation_compares_all_fields_and_rejects_other_branches(changed):
    from copy import deepcopy

    from compare_algo07v3_published import compare_additional_preparation

    owners = {a: {"point": 123} for a in ("c0", "fitted_c")}
    targets = [{"observations": ["a", "b"]}]
    original = dict(
        selected={"kind": "new_family"},
        gap_selected=None,
        targets=targets,
        eligible_targets=1,
        baseline_owners=owners,
    )
    inventory = dict(fragments=targets, summary={"count": 1})
    preflight = dict(checks={"c0": 0.0, "fitted_c": 1e-7}, corrected=[1.0, 2.0], seconds=12.0)
    protocol = dict(family_prior={"phase_sigma": 2.0})
    candidate = deepcopy(
        dict(
            status="additional_recovery_prepared",
            inventory=dict(inventory, targets=targets, eligible_targets=1),
            preflight={k: v for k, v in preflight.items() if k != "seconds"},
            selected_owners=owners,
            families=[protocol["family_prior"]],
            replay_checks=preflight["checks"],
            recovery_complete=False,
        )
    )
    if changed == "owners":
        candidate["selected_owners"]["fitted_c"]["point"] = 456
    if changed == "prior":
        candidate["families"][0]["phase_sigma"] += 1e-12
    if changed == "replay":
        candidate["replay_checks"]["c0"] += 1e-12
    if changed == "targets":
        candidate["inventory"]["targets"].pop()
    if changed == "unknown":
        candidate["new_field"] = True
    if changed == "gap":
        original["gap_selected"] = {"selected": True}
    if changed == "kind":
        original["selected"]["kind"] = "two_family"
    if changed is None:
        compare_additional_preparation(original, inventory, preflight, protocol, candidate)
    else:
        with pytest.raises(ValueError):
            compare_additional_preparation(original, inventory, preflight, protocol, candidate)


def test_persisted_comparison_checks_every_scientific_value():
    old = dict(case="SCAN", phase=[1.0, 2.0], owners={"point": 69333}, score=1.0)
    new = dict(phase=np.array([1.0, 2.0]), owners={"point": 69333}, score=1.0)
    exact_persisted(old, new, {"case"})
    for changed in (
        dict(new, phase=np.array([1.0, 2.00000000001])),
        dict(new, owners={"point": 12345}),
        dict(new, score=1.000000000001),
    ):
        with pytest.raises(ValueError):
            exact_persisted(old, changed, {"case"})


@pytest.mark.parametrize("changed", [None, "bytes", "hash", "policy", "epoch", "unknown", "center"])
def test_preflight_metadata_mapping_binds_files_policy_and_causality(tmp_path, changed):
    import hashlib
    import json

    from compare_algo07v3_published import map_preflight_metadata

    request = dict(
        search_center=[37.0, -122.0],
        screen_center=[37.5, -122.0],
        identity={"input_sha256": "input"},
    )
    receipt = dict(
        origin_utc_ns=12,
        cutoff_utc_ns=10,
        regional_center=request["screen_center"],
        reference_position_used=False,
        candidate_count=2,
        previous_count=2,
        snapshot_count=1,
        radius_km=250.0,
        candidate_filter="regional elevation >= -12deg; no whitelist",
        search_center=request["search_center"],
        search_box_width_km=25.0,
        previous_prior_repair="reject epoch differences under one second",
        latest_max_epoch_utc_ns=9,
        latest_max_collection_utc_ns=8,
    )
    files = {}
    for key, path in (
        ("bank_sha256", "worker/inference/SCAN/bank.npz"),
        ("latest_tle_sha256", "worker/inference/SCAN/selected.tle"),
        ("previous_tle_sha256", "worker/inference/causal_prior/SCAN/previous.tle"),
    ):
        dest = tmp_path / "ALGO02" / path
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(path.encode())
        receipt[key] = hashlib.sha256(dest.read_bytes()).hexdigest()
        files[path] = "sha256:" + receipt[key]
    (tmp_path / "ALGO02/descriptor.json").write_text(
        json.dumps(dict(files=files, input_sha256="input", source_worker_root="/original/worker"))
    )
    if changed == "bytes":
        dest.write_bytes(b"changed")
    if changed == "hash":
        receipt["bank_sha256"] = "different"
    if changed == "policy":
        receipt["radius_km"] = 251.0
    if changed == "epoch":
        receipt["latest_max_epoch_utc_ns"] = 11
    if changed == "unknown":
        receipt["new_field"] = True
    if changed == "center":
        request["screen_center"] = [38.0, -122.0]
    if changed:
        with pytest.raises(ValueError):
            map_preflight_metadata(receipt, tmp_path, request)
    else:
        value = map_preflight_metadata(receipt, tmp_path, request)
        assert len(value) == 7 and value["candidate_count"] == 2


def test_unknown_or_missing_bookkeeping_does_not_silently_disappear():
    with pytest.raises(ValueError, match="scope"):
        exact_persisted(dict(score=1, surprise=True), dict(score=1), set())
    with pytest.raises(ValueError, match="scope"):
        exact_persisted(dict(score=1), dict(score=1), {"case"})


def test_reference_export_hash_is_checked(tmp_path):
    import json

    stage = tmp_path / "ALGO02"
    stage.mkdir()
    (stage / "value.json").write_text('{"value": 1}')
    (stage / "descriptor.json").write_text(json.dumps(dict(files={"value.json": "wrong"})))
    with pytest.raises(ValueError, match="changed"):
        read_export(tmp_path, "ALGO02", "value.json")


def test_predictive_mapping_does_not_erase_unbound_retry_evidence(tmp_path):
    original = dict(
        selected=None,
        attempts=[
            dict(
                numerical_retry=dict(original_trial="/source/original", retry_trial="/source/retry")
            )
        ],
    )
    with pytest.raises(ValueError, match="no bound"):
        mapped_predictive(original, dict(source_worker_root="/source", files={}), tmp_path)


def test_failed_process_cannot_be_mapped_to_completed_science(tmp_path):
    original = dict(
        selected=None, attempts=[], stages=[dict(name="inventory", status="complete", returncode=1)]
    )
    with pytest.raises(ValueError, match="nonzero exit"):
        mapped_predictive(original, {}, tmp_path)


def test_trigger_checks_full_ranking_including_unselected_families():
    from compare_algo07v3_published import compare_trigger

    original = dict(ranking=[dict(norad=1, score=2.0), dict(norad=2, score=1.0)], selected=[1])
    candidate = dict(
        status="reassociation_targets_ranked",
        ranking=original["ranking"],
        targets=[1],
        recovery_complete=False,
    )
    compare_trigger(original, candidate)
    with pytest.raises(ValueError):
        compare_trigger(original, dict(candidate, ranking=[dict(norad=1, score=2.0)]))
    with pytest.raises(ValueError):
        compare_trigger(original, dict(candidate, targets=[2]))


@pytest.fixture
def no_addition_handoff():
    original = dict(
        baseline_arms={a: dict(endpoint=[1.0, 2.0], objective=3.0) for a in ("c0", "fitted_c")},
        baseline_owners={a: {"point": 12} for a in ("c0", "fitted_c")},
    )
    replay = dict(
        pre_recovery={"c0": 0.0, "fitted_c": 0.0},
        recovery={"status": "fallback"},
        rebuilt={"c0": 0.0, "fitted_c": 0.0},
    )
    decision = dict(
        status="no_qualified_new_family", excluded=[{"norad": 12}], eligible_proposals=0
    )
    additional = dict(decisions={"72h_30s": decision}, trials={}, control=None)
    candidate = dict(
        arms=original["baseline_arms"],
        owners=original["baseline_owners"],
        replay=dict(replay, recovery=decision),
        status="reassociation_prepared",
        recovery_complete=False,
    )
    return original, replay, additional, candidate


def test_handoff_checks_both_arms_owners_and_expanded_rejection(no_addition_handoff):
    from copy import deepcopy

    from compare_algo07v3_published import compare_handoff_no_addition

    original, replay, additional, candidate = no_addition_handoff
    compare_handoff_no_addition(original, replay, additional, candidate)
    for field, arm, key, value in (
        ("arms", "c0", "objective", 3.000000001),
        ("arms", "fitted_c", "endpoint", [1.0, 2.1]),
        ("owners", "c0", "point", 13),
        ("owners", "fitted_c", "point", 13),
    ):
        changed = deepcopy(candidate)
        changed[field][arm][key] = value
        with pytest.raises(ValueError):
            compare_handoff_no_addition(original, replay, additional, changed)
    changed = deepcopy(candidate)
    changed["replay"]["recovery"]["excluded"] = []
    with pytest.raises(ValueError):
        compare_handoff_no_addition(original, replay, additional, changed)


@pytest.mark.parametrize("kind", ["trial", "control", "accepted", "replay"])
def test_handoff_refuses_unmapped_additions_or_replay_fields(no_addition_handoff, kind):
    from compare_algo07v3_published import compare_handoff_no_addition

    original, replay, additional, candidate = no_addition_handoff
    if kind == "trial":
        additional["trials"] = {"new": {}}
    elif kind == "control":
        additional["control"] = {}
    elif kind == "accepted":
        additional["decisions"]["72h_30s"]["status"] = "qualified"
    else:
        replay["new_field"] = True
    with pytest.raises(ValueError):
        compare_handoff_no_addition(original, replay, additional, candidate)


@pytest.fixture
def reconstructed_oracle(tmp_path):
    import hashlib
    import json

    root = tmp_path / "export"
    source = root / "ALGO02/worker/inference/SCAN"
    source.mkdir(parents=True)
    data = source / "input.json"
    data.write_text("{}")
    module = tmp_path / "frozen.py"
    module.write_text("# original numerical source\n")
    value = dict(owners={"point": 12}, score=1.0)
    output = tmp_path / "oracle.json"
    from check_algo07v3_scan_likelihood import fingerprint

    output.write_text(json.dumps(fingerprint(value)))

    def binding(path):
        return dict(path=str(path), sha256=hashlib.sha256(path.read_bytes()).hexdigest())

    (root / "ALGO02/descriptor.json").write_text(
        json.dumps(
            dict(files={"worker/inference/SCAN/input.json": "sha256:" + binding(data)["sha256"]})
        )
    )
    receipt = dict(
        source=str(source),
        output=binding(output),
        tool=binding(module),
        inputs=[binding(data)],
        modules={"original": binding(module)},
        scan_identities=["scan"],
    )
    output.with_suffix(".receipt.json").write_text(json.dumps(receipt))
    return value, output, root, data, module


@pytest.mark.parametrize("changed", [None, "value", "input", "source", "output", "identity"])
def test_oracle_mapping_requires_every_value_and_bound_inputs(reconstructed_oracle, changed):
    from compare_algo07v3_published import compare_reconstructed_oracle

    value, output, root, data, module = reconstructed_oracle
    identities = ["scan"]
    if changed == "value":
        value["owners"]["point"] = 13
    elif changed == "input":
        data.write_text('{"changed": true}')
    elif changed == "source":
        module.write_text("# changed source\n")
    elif changed == "output":
        output.write_text("{}")
    elif changed == "identity":
        identities = ["other scan"]
    if changed:
        with pytest.raises(ValueError):
            compare_reconstructed_oracle(value, output, root, identities)
    else:
        compare_reconstructed_oracle(value, output, root, identities)


@pytest.mark.parametrize("changed", [None, "node", "arms", "signed", "base"])
def test_signed_restoration_checks_values_and_keeps_computed_state_exact(monkeypatch, changed):
    from copy import deepcopy

    import compare_algo07v3_published as module
    from check_algo07v3_scan_likelihood import fingerprint

    node, arms = dict(innovations=[1.0, 2.0]), dict(c0={"x": [1.0, 2.0]})
    persisted = dict(
        node=node, arms=arms, signed={"accepted": False, "policy_arms": arms}, base=np.array([3.0])
    )
    reference = fingerprint(persisted)
    candidate = deepcopy(persisted)
    candidate["node"]["innovations"] = np.array([1.0, 2.0])
    candidate["arms"] = {"c0": {"x": np.array([1.0, 2.0])}}
    candidate["signed"]["policy_arms"] = deepcopy(candidate["arms"])
    monkeypatch.setattr(
        module,
        "read_export",
        lambda root, stage, path: (
            {"final_node": node} if path.endswith("/result.json") else {"baseline_arms": arms},
            {},
        ),
    )
    if changed == "node":
        candidate["node"]["innovations"][0] += 1e-12
    elif changed == "arms":
        candidate["arms"]["c0"]["x"][0] += 1e-12
    elif changed == "signed":
        candidate["signed"]["policy_arms"]["c0"]["x"][0] += 1e-12
    elif changed == "base":
        candidate["base"][0] += 1e-12
    if changed:
        with pytest.raises(ValueError):
            module.compare_signed_snapshot(reference, candidate, None)
    else:
        module.compare_signed_snapshot(reference, candidate, None)


@pytest.fixture
def final_fallback(tmp_path):
    import hashlib
    from copy import deepcopy

    descriptor = dict(source_worker_root="/source", files={})
    for name in ("catalogue.json", "input.json", "candidate/protocol.json"):
        path = tmp_path / "worker/recovery" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
        descriptor["files"][str(path.relative_to(tmp_path))] = (
            "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()
        )
    sha = hashlib.sha256(b"{}").hexdigest()
    original = dict(
        selected=None,
        records=[],
        review=[],
        execution_status="complete",
        final=dict(c0=dict(x=[1.0, 2.0]), fitted_c=dict(x=[2.0, 3.0])),
        catalogue_eligibility=dict(
            candidate_count=11,
            catalogue_path="/source/recovery/catalogue.json",
            catalogue_sha256=sha,
            input_path="/source/recovery/input.json",
            input_sha256=sha,
        ),
        case="SCAN",
        seconds=1.0,
        protocol_sha256=sha,
    )
    value = deepcopy(original)
    for key in ("case", "seconds", "protocol_sha256"):
        del value[key]
    for key in ("catalogue_path", "catalogue_sha256", "input_path", "input_sha256"):
        del value["catalogue_eligibility"][key]
    value.update(control_fits={}, candidate_fits={})
    candidate = dict(status="reassociation_evaluated", recovery_complete=True, recovery=value)
    return original, candidate, descriptor, tmp_path


def test_final_fallback_checks_all_results_and_bound_files(final_fallback):
    from compare_algo07v3_published import compare_final_fallback

    compare_final_fallback(*final_fallback)
    original, candidate, descriptor, folder = final_fallback
    candidate["recovery"]["final"]["c0"]["x"][0] += 1e-10
    with pytest.raises(ValueError):
        compare_final_fallback(*final_fallback)


@pytest.mark.parametrize("field", ["control_fits", "candidate_fits", "records", "review"])
def test_final_mapping_rejects_uncovered_fit_branches(final_fallback, field):
    from compare_algo07v3_published import compare_final_fallback

    final_fallback[1]["recovery"][field] = {"unmapped": 1}
    with pytest.raises(ValueError):
        compare_final_fallback(*final_fallback)


def test_final_mapping_rejects_changed_source_link(final_fallback):
    from compare_algo07v3_published import compare_final_fallback

    (final_fallback[3] / "worker/recovery/catalogue.json").write_text('{"changed": true}')
    with pytest.raises(ValueError, match="Source bytes changed"):
        compare_final_fallback(*final_fallback)


def test_no_admission_screen_checks_rejected_candidates_and_both_cavities(final_fallback):
    from copy import deepcopy

    from compare_algo07v3_published import compare_screen_no_admission

    original, final, descriptor, folder = final_fallback
    original.update(targets=[1], guards={}, propagation_failures=[])
    screens = {
        "1": dict(
            cavity={a: dict(seconds=1.0, objective=5.0) for a in ("c0", "fitted_c")},
            proposals=[dict(norad=2, passed=False, score=4.0)],
        )
    }
    candidate = dict(
        status="reassociation_candidates_screened",
        recovery_complete=False,
        admission=dict(
            status="screened",
            targets=[1],
            catalogue_eligibility=final["recovery"]["catalogue_eligibility"],
            propagation_failures=[],
            screens=deepcopy(screens),
            shared={},
            guards={},
            admitted=[],
        ),
    )
    for arm in candidate["admission"]["screens"]["1"]["cavity"].values():
        del arm["seconds"]
    compare_screen_no_admission(original, screens, candidate, descriptor, folder)
    changed = deepcopy(candidate)
    changed["admission"]["screens"]["1"]["proposals"][0]["score"] += 1e-10
    with pytest.raises(ValueError):
        compare_screen_no_admission(original, screens, changed, descriptor, folder)
    changed = deepcopy(candidate)
    del changed["admission"]["screens"]["1"]["cavity"]["c0"]
    with pytest.raises(ValueError):
        compare_screen_no_admission(original, screens, changed, descriptor, folder)
    with pytest.raises(ValueError, match="Missing or extra"):
        compare_screen_no_admission(original, {}, candidate, descriptor, folder)


@pytest.mark.parametrize("width", [0, 3, 12])
@pytest.mark.parametrize("order", ["C", "F"])
@pytest.mark.parametrize("experiment", ["scatter", "factor_reuse"])
def test_experimental_kernels_preserve_exact_results_across_sparse_shapes(width, order, experiment):
    import runpy
    from pathlib import Path

    from leo.analysis.localization_v3.hierarchical import hierarchical_bound

    relative = (
        "reports/2026_11_05_algo07v3_pair/probe_assembly.py"
        if experiment == "scatter"
        else "reports/2026_11_05_algo07v3_assembly/probe_factor_reuse.py"
    )
    path = Path(__file__).resolve().parents[2] / relative
    candidate, _, _ = runpy.run_path(str(path))["candidate_function"]()
    rng = np.random.default_rng(177)
    features = rng.normal(size=(21, width))
    features[rng.random(features.shape) < 0.6] = 0
    features = np.array(features, order=order)
    y, sigma, groups = rng.normal(size=21), rng.uniform(10, 50, 21), np.arange(21) % 4
    prior = np.arange(width) // 3 - 1
    kwargs = dict(prior_groups=prior, powers=0.75, iterations=10)
    original = hierarchical_bound(y, features, sigma, groups, **kwargs)
    actual = candidate(y, features, sigma, groups, **kwargs)
    assert original.keys() == actual.keys()
    for key in original:
        a, b = np.asarray(original[key]), np.asarray(actual[key])
        assert a.dtype == b.dtype and a.shape == b.shape and a.tobytes() == b.tobytes(), key


def test_gap_prepare_only_mapping_verifies_native_support_and_process(tmp_path):
    import hashlib
    import json
    from copy import deepcopy

    from compare_algo07v3_published import compare_gap_no_split

    descriptor = dict(source_worker_root="/worker", files={})

    def write(relative, value):
        path = tmp_path / "worker" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(value).encode()
        path.write_bytes(raw)
        sha = hashlib.sha256(raw).hexdigest()
        descriptor["files"]["worker/" + relative] = "sha256:" + sha
        return sha

    sha = write("inventory.json", {})
    write("validation/result.json", {})
    write(
        "target/source.json",
        dict(
            track_id="t",
            points=2,
            inventory="/worker/inventory.json",
            validation="/worker/validation",
        ),
    )
    write(
        "target/gap/protocol.json",
        dict(parent_observation_ids=["p", "q"], input_sha256={"/worker/inventory.json": sha}),
    )
    write("target/gap/branches.json", dict(branches=[dict(observation_ids=["p", "q"])]))
    stage = dict(
        command=[
            "python",
            "-B",
            "/old/algo05_gap_stage.py",
            "prepare",
            "/worker/target/source.json",
            "/worker/target/gap",
        ],
        returncode=0,
        seconds=1.0,
        timeout_s=180,
    )
    original = dict(
        selected=None,
        candidate=None,
        trials=[],
        excluded=[],
        stages=[stage],
        no_GPS_inference=True,
        causal_only=True,
    )
    candidate = dict(
        original,
        stages=[dict(name="gap-0-prepare", status="complete", seconds=0.5, timeout_s=180)],
        targets=[dict(track_id="t", points=2)],
        numerical_receipts={},
    )
    compare_gap_no_split(original, candidate, descriptor, tmp_path)
    for changed in (
        dict(candidate, targets=[dict(track_id="t", points=1)]),
        dict(candidate, numerical_receipts={"unmapped": 1}),
    ):
        with pytest.raises(ValueError):
            compare_gap_no_split(original, changed, descriptor, tmp_path)
    failed = deepcopy(original)
    failed["stages"][0]["returncode"] = 1
    with pytest.raises(ValueError, match="Completed"):
        compare_gap_no_split(failed, candidate, descriptor, tmp_path)
    write("target/gap/branches.json", dict(branches=[dict(observation_ids=["p"])]))
    with pytest.raises(ValueError, match="Actual split"):
        compare_gap_no_split(original, candidate, descriptor, tmp_path)
