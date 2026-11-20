import sys
from types import ModuleType, SimpleNamespace

import pytest

from tools.pipeline_eval.qualification import compact_finish_eval as study
from tools.pipeline_eval.scoring import ARMS
from tools.pipeline_eval.variants import compact_finish


def install(monkeypatch, name, **attrs):
    module = ModuleType(name)
    vars(module).update(attrs)
    monkeypatch.setitem(sys.modules, name, module)
    return module


@pytest.mark.parametrize("repair", [False, True])
def test_finish_retains_published_owners_and_uses_only_frozen_adoptees(monkeypatch, repair):
    prefix = "leo.analysis.localization_v3."
    metadata = {"cutoff_utc_ns": 12}
    observations, tracks = [{"observation_id": "original"}], ["track"]
    prepared = dict(
        tracks=dict(observations=observations, tracks=tracks), sky=dict(metadata=metadata)
    )
    region = SimpleNamespace(latlon=lambda point: list(point))
    scan = SimpleNamespace(search_region=region)
    cavity = {"policy_arms": "cavity policy"}
    catalogue = {"cutoff_utc_ns": 12}
    residual = {"families": []}
    packet = {"case": "SCAN", "targets": [{"source": "residual curve"}]}
    addition = {"decisions": {"72h_30s": {"status": "qualified"}}}
    owners = {arm: {"original": 1} for arm in ARMS}
    actual_owners = {arm: {"original": 1, "incidental": 2} for arm in ARMS}
    baseline_arms = {arm: {"endpoint_latlon": [1, 2]} for arm in ARMS}

    def support(policy_arms, replayed):
        assert policy_arms == "cavity policy" and replayed == actual_owners
        return {arm: {"owners": owners[arm]} for arm in ARMS}

    install(
        monkeypatch,
        prefix + "recovery_inventory",
        recovery_context=lambda a, b: (scan, cavity) if (a, b) == (scan, cavity) else None,
        baseline_pair=lambda context: (baseline_arms, actual_owners),
        publication_support=support,
    )

    def reconstruct(context, arms, reported):
        assert context == (scan, cavity) and arms == baseline_arms and reported == owners
        return residual

    install(monkeypatch, prefix + "selected_incumbent", reconstruct_incumbent=reconstruct)

    def rank(track_rows, obs, supported, identities):
        assert (track_rows, obs, supported, identities) == (
            tracks,
            observations,
            owners,
            ["a", "b"],
        )
        return {"targets": packet["targets"]}

    install(
        monkeypatch, prefix + "residual_preflight", rank_targets=rank, preflight=lambda *a: packet
    )
    install(monkeypatch, prefix + "residual_screen", screen_candidates=lambda *a: packet)

    def recover(fresh, supported, screen, records, obs, *, family_count, clock):
        assert (supported, screen, records, obs) == (owners, packet, catalogue, observations)
        assert fresh() is residual and family_count == 0 and clock() > 0
        return addition

    install(monkeypatch, prefix + "additional_recovery", recover_additional=recover)

    def state(point, adopted_owners, rms):
        context = {"problems": {a: (SimpleNamespace(scan=scan), point) for a in ARMS}}
        arms = {
            a: dict(endpoint_latlon=point, proposed_owners=adopted_owners[a], RMS_hz=rms)
            for a in ARMS
        }
        return context, arms

    added_owners = {a: dict(owners[a], recovered=3) for a in ARMS}
    added_context, added_arms = state([3, 4], added_owners, 70)

    def adopt(fresh, arms, support, selection, recovered, screen, records, obs):
        assert fresh() is residual and selection is None
        assert (arms, support, recovered, screen, records, obs) == (
            baseline_arms,
            owners,
            addition,
            packet,
            catalogue,
            observations,
        )
        return dict(context=added_context, arms=added_arms, owners=added_owners)

    install(
        monkeypatch,
        prefix + "reassociation_context",
        adopt_additional=adopt,
        rank_families=lambda context: ([], [3]) if context is added_context else ([], []),
    )
    install(monkeypatch, prefix + "reassociation_history", select_history=lambda h, q: (h, q))
    history_reads = []

    def history(archive, cutoff):
        history_reads.append((archive, cutoff))
        return "history"

    def admit(incumbent, ranked, records, scan_receipt):
        assert incumbent["context"] is added_context and ranked["targets"] == [3]
        assert records is catalogue and scan_receipt is metadata
        return {"admission": {"admitted": [3] if repair else []}}

    def final(incumbent, admission, records, scan_receipt, collect, *, on_selected):
        assert (
            incumbent["owners"] == added_owners
            and records is catalogue
            and scan_receipt is metadata
        )
        assert bool(admission["admission"]["admitted"]) is repair
        point = [5, 6] if repair else [3, 4]
        if repair:
            assert collect("first") == ("history", "first")
            assert collect("second") == ("history", "second")
            reassigned_owners = {a: dict(added_owners[a], recovered=4) for a in ARMS}
            on_selected(*state(point, reassigned_owners, 69))
        return dict(
            recovery_complete=True,
            recovery=dict(
                selected="3_to_4" if repair else None,
                final={arm: dict(x=point, associated=2) for arm in ARMS},
            ),
        )

    application = install(monkeypatch, "leo.application")
    application.localization_v3 = install(
        monkeypatch,
        "leo.application.localization_v3",
        prepare_additional_catalogue=lambda archive, cutoff: catalogue,
        prepare_reassociation_history=history,
        screen_reassociation_candidates=admit,
        fit_reassociation=final,
    )
    got = compact_finish.finish("archive", ["b", "a"], prepared, scan, cavity, {})
    assert got["status"] == "ok" and got["boundary"] == compact_finish.BOUNDARY
    assert history_reads == ([("archive", 12)] if repair else [])
    assert got["metrics"]["addition_status"] == "qualified"
    assert got["metrics"]["reassociation_selected"] == ("3_to_4" if repair else None)
    for arm in ARMS:
        assert got["arms"][arm]["latlon"] == ([5, 6] if repair else [3, 4])
        assert got["metrics"][f"{arm}_conditional_rms_hz"] == (69 if repair else 70)


def test_comparison_requires_both_endpoint_and_frequency_parity():
    def prediction(method, points, rms):
        return dict(
            method=method,
            worker_wall_s=2 if method == study.FULL else 1,
            worker_cpu_s=1.8,
            result=dict(
                status="ok",
                arms={
                    a: {"latlon": p, "rf_rms_hz": x}
                    for a, p, x in zip(ARMS, points, rms, strict=True)
                },
                metrics={},
            ),
        )

    points = [[37, 122], [37, 122]]
    full = prediction(study.FULL, points, [30, 31])
    finish = prediction(study.FINISH, [[37, 122], [37.003, 122]], [31, 31])
    cavity = prediction(study.CAVITY, points, [29, 30])
    result = study.score_case({"id": "test", "truth": [37, 122]}, [finish, full, cavity])
    assert result["speedup"]["wall_s"] == 2
    assert [p["passed"] for p in result["parity"].values()] == [False, False]
    assert result["parity"]["c0"]["coordinate_delta_m"] == 0
    assert result["parity"]["fitted_c"]["conditional_rms_delta_hz"] == 0


def test_extension_matches_the_archived_objective_if_no_conditional_rms_exists(tmp_path):
    point = [37, 122]
    archived = {
        "arms": {a: dict(latlon=point, conditional_rms_hz=None, frequency_score=250) for a in ARMS}
    }
    ref = {"truth": point, "reference": {"baseline": {a: {"latlon": point} for a in ARMS}}}
    prediction = {
        "result": {
            "arms": {a: {"latlon": point} for a in ARMS},
            "metrics": dict(
                {f"{a}_frequency_score": 250 for a in ARMS}, addition_status="qualified"
            ),
        },
    }
    assert study.score_extension(tmp_path, ref, archived, prediction)
    prediction["result"]["metrics"]["c0_frequency_score"] = 250.01
    assert not study.score_extension(tmp_path, ref, archived, prediction)


def test_worker_refuses_qnap_output_before_compilation(monkeypatch):
    def compile_kernel(path):
        pytest.fail("kernel compilation on a read-only root")

    monkeypatch.setattr(compact_finish.orbit_projector, "compile_kernel", compile_kernel)
    with pytest.raises(ValueError, match="QNAP"):
        compact_finish.run({}, "/mnt/qnap01/finish")


@pytest.mark.parametrize("offered", [False, True])
def test_adapter_verifies_cavity_once_for_both_nomination_paths(monkeypatch, tmp_path, offered):
    signed = {"scan": "genuine causal scan"}
    nominations = {"offered": offered}
    fitted = {"status": "complete", "policy_arms": "selected"}
    fit_calls = []

    def fit_cavity(context, proposals):
        fit_calls.append((context, proposals))
        return fitted

    name = "leo.analysis.localization_v3"
    parent = install(monkeypatch, name)
    family = install(
        monkeypatch,
        name + ".family_cavity",
        nominate_families=lambda context: nominations,
        cavity_policy=fit_cavity,
    )
    parent.family_cavity = family
    install(monkeypatch, "leo.operations.tle_archive", TleArchiveReader=lambda path: path)
    job = {"tle_root": str(tmp_path), "scan_identities": ["case"]}
    monkeypatch.setattr(compact_finish.v5_lean, "_read", lambda request: {"job": job})

    def infer(prepared, region, bound, timings):
        nominees = family.nominate_families(signed)
        if nominees["offered"]:
            family.cavity_policy(signed, nominees)
        return {"status": "ok", "metrics": {"cavity_offered": offered}}

    monkeypatch.setattr(compact_finish.v5_core, "infer", infer)
    results = []

    def projector(request, result, library):
        results.append(compact_finish.v5_core.infer("front end", None, None, {"cavity": 1.0}))

    monkeypatch.setattr(compact_finish.orbit_projector, "worker", projector)

    def finish(archive, identities, prepared, scan, cavity, timings):
        assert (archive, identities, prepared) == (tmp_path, ["case"], "front end")
        assert scan == signed["scan"] and cavity is fitted and timings["cavity"] >= 1.0
        return {"status": "ok", "metrics": {"finished": True}}

    monkeypatch.setattr(compact_finish, "finish", finish)
    compact_finish.worker(None, None, None)
    assert fit_calls == [(signed, nominations)]
    assert results == [{"status": "ok", "metrics": {"cavity_offered": offered, "finished": True}}]
    assert family.cavity_policy is fit_cavity and compact_finish.v5_core.infer is infer
