import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.pipeline_eval import original_receiver as receiver
from tools.pipeline_eval.__main__ import save_json
from tools.pipeline_eval.qualification import capture_whole_results


def test_normal_collection_uses_verified_visits_and_preserves_scheduling_weights(
    tmp_path, monkeypatch
):
    chunks = [(0, 0, 2, 0)]
    plan = {"workers": [(7, 2, chunks)]}
    observed = []

    def verify(work, lock):
        observed.append((work, lock["workers"]))
        return "verified"

    monkeypatch.setattr(capture_whole_results, "collect", verify)
    assert receiver.collect(tmp_path, plan) == "verified"
    assert observed == [(tmp_path, [(7, None, chunks)])]
    assert plan["workers"] == [(7, 2, chunks)]


def test_explicit_input_requires_its_exact_digest(tmp_path):
    path = tmp_path / "input.json"
    save_json(path, {"id": "sensor-capture"})
    with pytest.raises(ValueError, match="--input-sha256"):
        receiver.input_case(None, path, None)
    with pytest.raises(ValueError, match="declared SHA-256"):
        receiver.input_case(None, path, "1" * 64)
    assert receiver.input_case(None, path, receiver._sha(path)) == {"id": "sensor-capture"}
    with pytest.raises(ValueError, match="accompanies --input"):
        receiver.input_case("DS26-0036", None, receiver._sha(path))


def test_unknown_capture_producer_is_rejected_before_staging(tmp_path, monkeypatch):
    digest = "sha256:" + "2" * 64
    case = dict(id="unregistered", session_id="fast-" + "2" * 32, run_id="unknown")
    monkeypatch.setattr(receiver, "chunks", lambda _: [(0, 0, 1, 0)])
    monkeypatch.setattr(
        receiver.capture_release,
        "read_capture",
        lambda _: dict(edge="upper", input_manifest_sha256=digest),
    )
    out = tmp_path / "output"
    with pytest.raises(receiver.capture_release.UnsupportedCaptureRelease, match="unregistered"):
        receiver.prepare(case, out, [min(os.sched_getaffinity(0))], 30, 30, tmp_path, None, False)
    assert not out.exists()


@pytest.mark.parametrize("limits", [(0, 180), (600, 601)])
def test_service_limits_are_checked_before_input_access(tmp_path, limits, capsys):
    with pytest.raises(SystemExit, match="2"):
        receiver.main(
            [
                "--case",
                "unregistered",
                "--cpus",
                "0",
                "--out",
                str(tmp_path / "output"),
                "--raw-limit",
                str(limits[0]),
                "--position-limit",
                str(limits[1]),
            ]
        )
    assert "each service limit" in capsys.readouterr().err


@pytest.mark.parametrize("smoke", [True, False])
@pytest.mark.parametrize("backend", [None, "row-wise"])
@pytest.mark.parametrize("interior_guard", [False, True])
def test_normal_command_handoffs_only_fresh_complete_native_factors(
    tmp_path, monkeypatch, smoke, backend, interior_guard
):
    tle = tmp_path / "catalog.tle"
    tle.write_text("fixture catalogue")
    config = tmp_path / "track.json"
    save_json(config, {})
    origin = tmp_path / "original.json"
    save_json(
        origin,
        dict(
            role="baseline",
            causal_snapshots={tle.name: receiver._sha(tle)},
            job=dict(
                identity=dict(session_id="fixture"),
                evaluation_reference=None,
                search_center=[0.0, 0.0],
                tle_root=str(tmp_path),
                track_config=dict(path=str(config), sha256=receiver._sha(config)),
            ),
        ),
    )
    case = dict(
        id="fixture",
        session_id="fixture",
        panel="test",
        regions=[{"center": [0.0, 0.0]}],
        recording=dict(window_count=1),
        request=dict(path=origin.name, sha256=receiver._sha(origin)),
    )
    source = tmp_path / "case.json"
    save_json(source, case)

    def prepare(
        case,
        out,
        cpus,
        raw_limit,
        position_limit,
        receiver_path,
        _kernel_dir,
        partial,
        peak_selector,
        interior_guard,
    ):
        assert partial is smoke and cpus == [8]
        assert peak_selector == (backend or "installed")
        plan = dict(
            id=case["id"],
            case=case,
            cpus=cpus,
            raw_limit_s=raw_limit,
            position_limit_s=position_limit,
            receiver=str(receiver_path),
            peak_selector=dict(backend=peak_selector),
            workers=[(8, 1, [(0, 0, 1, 0)])],
            smoke=partial,
            recording=case["recording"],
        )
        if interior_guard:
            policy = Path(receiver.final_region.__file__)
            plan["interior_guard"] = {str(policy): receiver._sha(policy)}
        out.mkdir()
        save_json(out / "source-lock.json", plan)
        return plan

    stages = []

    def service(attempt, cpu, limit, stage, _options=None):
        stages.append((stage, cpu, limit))
        if stage == "position":
            request = receiver.whole_iq.read(attempt / "recording/request.json")
            native = request["job"]["native_input"]
            assert native["path"] == str(out / "native.json")
            assert receiver.whole_iq.checked(out / "native.json", native["sha256"]).is_file()
            assert request["job"]["evaluation_reference"] is None
            save_json(
                attempt / "position.json",
                dict(
                    status="ok",
                    boundary="controlled compact fixture",
                    metrics={},
                    arms=dict(c0=dict(latlon=[0.01, 0.02]), fitted_c=dict(latlon=[0.03, 0.04])),
                ),
            )
        return dict(exit_code=0)

    monkeypatch.setattr(receiver, "prepare", prepare)
    monkeypatch.setattr(receiver, "service", service)
    monkeypatch.setattr(receiver, "collect", lambda *_: ("checked-shards", {}, 0.1))
    monkeypatch.setattr(
        capture_whole_results, "summary_rows", lambda _: [dict(status="processed", folded_calls=2)]
    )
    monkeypatch.setattr(capture_whole_results, "assemble", lambda *_: ({"synthetic": True}, {}))
    out = tmp_path / "output"
    args = [
        "--input",
        str(source),
        "--input-sha256",
        receiver._sha(source),
        "--out",
        str(out),
        "--cpus",
        "8",
        "--raw-limit",
        "30",
        "--position-limit",
        "20",
    ]
    if backend:
        args.extend(("--peak-selector", backend))
    if interior_guard:
        args.append("--interior-guard")
    assert receiver.main(args + (["--smoke"] if smoke else [])) == 0
    data = json.loads((out / "summary.json").read_bytes())
    source_lock = receiver.whole_iq.read(out / "source-lock.json")
    assert ("interior_guard" in source_lock) is interior_guard
    assert data["peak_selector"]["backend"] == (backend or "installed")
    assert data["completed_visits"] == 1
    assert stages[0] == ("raw", 8, 30)
    if smoke:
        assert data["status"] == "stage_only"
        assert "result" not in data and not (out / "native.json").exists()
        assert len(stages) == 1
    else:
        assert data["status"] == "ok"
        assert set(data["result"]["arms"]) == {"c0", "fitted_c"}
        assert stages[1] == ("position", 8, 20)


def test_row_wise_backend_requires_qualified_producer_and_unchanged_source(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="unqualified for producer"):
        receiver.selector_evidence("row-wise", tmp_path)

    source = tmp_path / "leo/analysis/starlink/acquisition.py"
    source.parent.mkdir(parents=True)
    source.write_text("fixture installed acquisition")
    digest = receiver._sha(source)
    monkeypatch.setattr(receiver, "ROW_SELECTOR_PRODUCERS", {tmp_path: digest})
    selected = receiver.selector_evidence("row-wise", tmp_path)
    assert selected["version"] == "row-wise-v1"
    assert selected["producer_sha256"] == digest
    assert selected["sha256"] == receiver._sha(Path(selected["source"]))
    with pytest.raises(ValueError, match="differs from the source seal"):
        receiver.peak_selector_for(
            {"producer": str(tmp_path), "peak_selector": dict(selected, version="old")}
        )
    source.write_text("modified installed acquisition")
    with pytest.raises(ValueError, match="declared SHA-256"):
        receiver.peak_selector_for({"producer": str(tmp_path), "peak_selector": selected})


def test_row_wise_patch_is_local_and_prior_plans_keep_installed_selector(monkeypatch):
    from leo.analysis.starlink import acquisition

    original = acquisition._retain_score_map_peaks
    source = Path(acquisition.__file__)
    root = source.parents[3]
    monkeypatch.setattr(receiver, "ROW_SELECTOR_PRODUCERS", {root: receiver._sha(source)})
    lock = {"producer": str(root)}
    installed = receiver.selector_evidence("installed", root)
    selected = receiver.selector_evidence("row-wise", root)
    for plan in (lock, dict(lock, peak_selector=installed)):
        with receiver.peak_selector_for(plan):
            assert acquisition._retain_score_map_peaks is original
    monkeypatch.setattr(acquisition, "__file__", str(source.with_name("other.py")))
    with pytest.raises(ValueError, match="producer must own the peak selector"):
        receiver.peak_selector_for(dict(lock, peak_selector=selected))
    monkeypatch.setattr(acquisition, "__file__", str(source))
    with receiver.peak_selector_for(dict(lock, peak_selector=selected)):
        assert acquisition._retain_score_map_peaks is receiver.prepared_hotpath_peaks.retained_peaks
    assert acquisition._retain_score_map_peaks is original


@pytest.mark.parametrize("enabled", [False, True])
def test_position_worker_applies_the_persisted_policy_before_first_write(
    tmp_path, monkeypatch, enabled
):
    attempt = tmp_path / "position"
    request = attempt / "recording/request.json"
    save_json(
        request,
        dict(
            job=dict(
                native_input=dict(path="recorded_native.json"),
                identity=dict(session_id="fixture"),
                track_config=dict(path="track.json", sha256="b" * 64),
                tle_root="catalogue",
                search_center=[0.0, 0.0],
                screen_center=[0.1, 0.1],
            )
        ),
    )
    save_json(
        attempt / "raw.json", dict(request_sha256=receiver._sha(request), native_sha256="a" * 64)
    )
    lock = dict(receiver="installed", receiver_files={})
    if enabled:
        policy = Path(receiver.final_region.__file__)
        lock["interior_guard"] = {str(policy): receiver._sha(policy)}
    lock_path = tmp_path / "source-lock.json"
    save_json(lock_path, lock)
    save_json(
        attempt / "plan.json",
        dict(
            cpus=[8],
            stage="position",
            receiver="installed",
            source_lock_sha256=receiver._sha(lock_path),
        ),
    )
    monkeypatch.setattr(receiver, "receiver_assets", lambda _: {})
    monkeypatch.setattr(receiver.whole_iq.raw, "mark", lambda _: {})

    solution = dict(
        status="ok",
        boundary="controlled compact fixture",
        metrics=dict(c0_frequency_score=1.5, fitted_c_frequency_score=2.5),
        arms=dict(
            c0=dict(latlon=[0.01, 0.02], rf_rms_hz=52.0),
            fitted_c=dict(latlon=[12.5 / 111, 0.00], rf_rms_hz=49.0),
        ),
    )
    payload = (json.dumps(solution) + "\n").encode()
    position = attempt / "position.json"

    def solve(command, cwd, stdout, check):
        assert cwd == attempt and check
        tile = command.index("--tile")
        assert command[tile + 1 : tile + 3] == ["0.0", "0.0"]
        if enabled:
            assert not position.exists()
            assert command[-2:] == ["--width-km", "25.0"]
        else:
            stdout.write(payload)
        return SimpleNamespace(stdout=payload)

    monkeypatch.setattr(receiver.whole_iq.subprocess, "run", solve)
    assert receiver.worker(attempt) == 0
    if enabled:
        actual = receiver.whole_iq.read(position)
        assert actual["status"] == "withheld"
        assert actual["reason"] == "terminal_compact_fit_at_tile_face"
        for arm, selected in solution["arms"].items():
            assert actual["arms"][arm] == dict(
                selected, latlon=None, forced_latlon=selected["latlon"]
            )
        assert actual["metrics"] | solution["metrics"] == actual["metrics"]
    else:
        assert position.read_bytes() == payload
    assert (attempt / "end.json").is_file()
