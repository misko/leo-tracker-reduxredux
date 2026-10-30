"""Evaluation-only truth and runtimes must not shrink the recording cohort."""

import json

import pytest

from algo03_production_worker import envelope, verify_selected
from algo03_shadow_worker import scientific_receipts, single_candidate, write
from leo.contracts.fast_graph_position import CENTER, KIND, MODEL_VERSION
from report_algo03_dataset_evaluation import distance_km, plot_report, rows_for_case


def case():
    return dict(case="DS23-0001", dataset="DS23", recording_format="short_window_iq_recording",
                input=dict(sha256="sha256:input"))


def baseline():
    arms = {a: dict(endpoint_latlon=list(CENTER), endpoint_east_north_km=[0, 0],
                    RMS_hz=10, negative_twice_elbo=30, final_phase_change_s=0,
                    gates=dict(tracks=[dict(component="track", points=1, compatible=True,
                                            observation_ids=["old"], norad=1)]), linear_gates=[])
            for a in ("c0", "fitted_c")}
    return dict(schema_version=1, kind=KIND, model_version=MODEL_VERSION,
                input_sha256="sha256:input", session_id="recording", state="complete",
                position=dict(latitude_deg=CENTER[0], longitude_deg=CENTER[1]),
                qualification="paired_residual_phase_regional_gates", selected_arm="fitted_c",
                arms=arms, elapsed_seconds=123, matched_c_inputs=True, future_TLE_used=False,
                reference_usage="none", read_audit=dict(all_launched_processes_accounted=True,
                                                        denied_paths=[], receipts=4,
                                                        historical_result_or_GPS_reads=False))


def saved_candidate(folder, terminal):
    write(folder / "baseline-receipt.json", dict(state="complete", terminal=terminal["baseline"],
                                                seconds=2, reused_production=True))
    path = folder / "candidate-v2/terminal.json"
    write(path, terminal)
    write(folder / "candidate-receipt.json", dict(state="complete", seconds=17,
                                                 terminal_path=str(path)))


def test_absent_results_keep_both_arms(tmp_path):
    cohort, rows = rows_for_case(case(), tmp_path, [37, -122], frozen_release_verified=False)
    assert cohort["acquisition_mode"] == "fast"
    assert [r["arm"] for r in rows] == ["c0", "fitted_c"]
    assert all(r["baseline"]["state"] == r["candidate"]["state"] == "missing" for r in rows)
    assert all(r["candidate"]["error_km"] is None for r in rows)


def test_fallback_preserves_exact_error_and_includes_baseline_runtime(tmp_path):
    terminal = envelope(baseline(), dict(read_audit=dict(verified=False)), recovery_seconds=17)
    saved_candidate(tmp_path, terminal)
    _, rows = rows_for_case(case(), tmp_path, [37, -122], frozen_release_verified=True)
    for row in rows:
        assert row["baseline"]["error_km"] == row["candidate"]["error_km"]
        assert row["candidate"]["total_seconds"] == 140
        assert row["baseline"]["total_seconds"] == 123
        assert row["read_audit_verified"]
        assert not row["recovery_read_audit_verified"]


@pytest.mark.parametrize("failure", ["legacy", "state", "comparator"])
def test_unpublished_or_mismatched_candidate_is_failed_without_losing_arms(tmp_path, failure):
    terminal = envelope(baseline(), {}, recovery_seconds=17)
    saved_candidate(tmp_path, terminal)
    if failure == "legacy":
        terminal.pop("schema_version")
    elif failure == "state":
        terminal.update(state="failed", position=None)
    else:
        terminal["baseline"]["elapsed_seconds"] = 124
    (tmp_path / "candidate-v2/terminal.json").write_text(json.dumps(terminal))
    _, rows = rows_for_case(case(), tmp_path, CENTER, frozen_release_verified=True)
    assert len(rows) == 2
    assert all(r["baseline"]["state"] == "complete" for r in rows)
    assert all(r["candidate"]["state"] == "failed" for r in rows)
    assert all(r["candidate"]["error_km"] is None and r["failure"] for r in rows)


def test_report_replays_scientific_proof_using_retained_supervisor_tree(tmp_path):
    recovery = tmp_path / "candidate-v2/recovery"
    source = {a: dict(owners={"old": 1}) for a in ("c0", "fitted_c")}
    inventory = dict(policy={a: dict(proposed_associated_ids=["old"])
                             for a in ("c0", "fitted_c")}, publication_support=source)
    descriptor = recovery / "snapshot/descriptor.json"
    inv = recovery / "all-large-track-recovery/job/inventory.json"
    write(descriptor, dict(job_id="job"))
    write(inv, inventory)
    write(recovery / "snapshot/inference/SCAN/observations.json",
          [dict(observation_id=i) for i in ("old", "new")])
    support = inv.with_name("publication_support.json")
    write(support, dict(arms=source, all_verified=True,
                        source_receipts=scientific_receipts([descriptor, inv])))
    trial = recovery / "target/trial"
    write(trial / "protocol.json", dict(targets=[dict(norad=2, observation_ids=["new"])]))
    write(trial / "control.json", dict(paired_valid=True))
    endpoint = dict(endpoint_east_north_km=[0, 0], endpoint_latlon=list(CENTER),
                    negative_twice_elbo=20)
    write(trial / "new_family.json", dict(paired_valid=True,
                                          arms={a: endpoint for a in ("c0", "fitted_c")}))
    write(trial / "exact_owner_replay.json", dict(all_verified=True,
          rows=[dict(role=r, arm=a, verified=True, owners={"old": 1, "new": 2})
                for r in ("control", "new_family") for a in ("c0", "fitted_c")]))
    write(recovery / "read_receipts/123.json",
          dict(pid=123, parent_pid=999999, python_spawns=[], denied_paths=[]))
    result = dict(decision="ALGO03_single", selected=single_candidate(inventory, trial, False),
                  source_support=source, source_support_receipt=scientific_receipts([support]),
                  read_audit=dict(verified=True, root_process_id=123, supervisor_process_id=999999,
                                  denied_paths=[], all_launched_processes_accounted=True))
    checks = verify_selected(result, recovery)
    saved_candidate(tmp_path, envelope(baseline(), result, recovery_seconds=17, proof_checks=checks))
    _, rows = rows_for_case(case(), tmp_path, CENTER, frozen_release_verified=True)
    assert all(r["candidate"]["state"] == "complete" and r["failure"] is None for r in rows)
    assert all(r["read_audit_verified"] and r["observation_sets_changed"] for r in rows)
    (trial / "control.json").write_text("changed")
    _, rows = rows_for_case(case(), tmp_path, CENTER, frozen_release_verified=True)
    assert all(r["candidate"]["state"] == "failed" for r in rows)
    assert all("Scientific proof changed" in r["failure"] for r in rows)


def test_association_percentage_uses_hash_verified_unique_exported_observations(tmp_path):
    import hashlib

    terminal = envelope(baseline(), {}, recovery_seconds=17)
    saved_candidate(tmp_path, terminal)
    root = tmp_path / "public-export"
    observations = root / "SCAN/observations.json"
    write(observations, [dict(observation_id=i) for i in ("old", "new")])
    write(tmp_path / "evaluation-export/descriptor.json", dict(
        terminal=terminal["baseline"], input_sha256="sha256:input", case="SCAN", root=str(root),
        files={"SCAN/observations.json": "sha256:" + hashlib.sha256(observations.read_bytes()).hexdigest()}))
    _, rows = rows_for_case(case(), tmp_path, CENTER, frozen_release_verified=True)
    for row in rows:
        assert row["baseline"]["associated_points"] == row["candidate"]["associated_points"] == 1
        assert row["candidate"]["available_GLRT_observations"] == 2
        assert row["candidate"]["associated_percent"] == 50
        assert row["observation_denominator_failure"] is None
    observations.write_text("changed")
    _, rows = rows_for_case(case(), tmp_path, CENTER, frozen_release_verified=True)
    assert all(r["candidate"]["associated_percent"] is None for r in rows)
    assert all("observation bytes changed" in r["observation_denominator_failure"] for r in rows)


def test_figures_preserve_missing_members_in_panel_denominators(tmp_path):
    terminal = envelope(baseline(), {}, recovery_seconds=17)
    saved_candidate(tmp_path / "one", terminal)
    _, complete = rows_for_case(case(), tmp_path / "one", CENTER, frozen_release_verified=True)
    _, missing = rows_for_case(case(), tmp_path / "missing", CENTER, frozen_release_verified=True)
    counts = plot_report(complete + missing, ["DS23"], tmp_path)
    assert counts == [dict(dataset="DS23", arm=arm, cohort=2, common_qualified_pairs=1, runtime_pairs=1)
                      for arm in ("c0", "fitted_c")]
    for name in ("error-cdf.png", "paired-error.png", "runtime.png", "figure-denominators.json"):
        assert (tmp_path / name).stat().st_size > 0


def test_geographic_distance():
    assert distance_km([0, 0], [0, 0]) == 0
    assert distance_km([0, 0], [1, 0]) == pytest.approx(111.195, abs=.001)
