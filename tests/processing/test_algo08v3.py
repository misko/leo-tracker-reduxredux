import json
from io import BytesIO
from pathlib import Path
from subprocess import CompletedProcess

import pytest
from PIL import Image

from leo.contracts.algo08_region import Algo08Region
from leo.contracts.algo08v3 import EXECUTION_RELEASE
from leo.contracts.digests import canonical_digest
from leo.contracts.fast_standard_analysis import ALGO08V2, ALGO08V3, PLOTS, standard_label
from leo.processing import algo08v3
from leo.storage.fast_scan import FastScanStore, immutable_json
from leo.storage.fast_standard_analysis import FastStandardAnalysisStore


@pytest.fixture
def publication(monkeypatch, tmp_path):
    recording = tmp_path / "recording"
    store = FastScanStore(tmp_path / "bulk")
    region = Algo08Region((37.906, -122.545), 25).document()
    region_file = tmp_path / "region.json"
    immutable_json(region_file, region)
    inventory = dict(schema_version=1, kind="fast-scan-source", recording_name=recording.name,
                     segments=[], window_count=2)
    digest = canonical_digest(inventory)
    session = "fast-" + digest[7:39]
    old_run = "algo08-v2-example"
    binding = dict(session_id=session, region=region, input_sha256=digest, raw_authority=digest,
                   orbit_policy="stock", terminal_sha256=canonical_digest(["source terminal"]))
    stream = BytesIO()
    Image.new("RGB", (2, 2)).save(stream, format="PNG")
    pngs = dict.fromkeys(PLOTS, stream.getvalue())
    calls = []
    release = dict(EXECUTION_RELEASE)
    monkeypatch.setattr(store, "inventory", lambda path, **options: (session, digest, inventory))

    def make_launcher(decision):
        def launch(command, **options):
            calls.append(command)
            assert command[1] == "-IB"
            assert Path(command[2]).name == "algo08v3_launcher.py"
            assert Path(command[3]) == algo08v3.DEFAULT_LAUNCHER
            assert Path(command[command.index("--recording") + 1]) == recording
            assert json.loads(Path(command[command.index("--region") + 1]).read_bytes()) == region
            root = Path(command[-1])
            assert not any(root.iterdir())
            source = FastScanStore(root)
            standard = FastStandardAnalysisStore(root)
            source.publish_inventory(session, inventory)
            source.publish(old_run, dict(
                kind="fast-scan.report", model_version=ALGO08V2, run_id=old_run, session_id=session,
                recording_name=recording.name, window_count=inventory["window_count"],
                counts=dict(processed=2), points=[{"cfo_hz": 17.0}]))
            if decision == "withheld":
                standard.withhold(old_run, "no active tracks", **binding)
            else:
                arms = {arm: dict(endpoint_latlon=region["center"], associated_points=1, owner_sha256=digest)
                        for arm in ("c0", "fitted_c")}
                document = dict(**binding, schema_version=3, run_id=old_run, state="complete",
                                model_version=ALGO08V2, selected_model=ALGO08V2, figures_model=ALGO08V2,
                                reference_usage="evaluation_only", arms=arms, glrt_points=2)
                grid = dict(schema_version=1, kind="conditional-position-grid", matched_c_grid=True,
                            conditioning="published satellite ownership and phase linearization fixed",
                            endpoint_latlon={arm: row["endpoint_latlon"] for arm, row in arms.items()},
                            box_width_km=region["width_km"], region_center=region["center"],
                            points=[], evaluated_points=0, planned_points=0, complete=True)
                path = dict(schema_version=2, kind="recorded-position-path", selected_model=ALGO08V2,
                            box_width_km=region["width_km"], region_center=region["center"],
                            stages=[dict(model_version=ALGO08V2, arms={
                                 arm: dict(endpoint=[0, 0], history_available=False, rounds=[])
                                 for arm in arms})])
                standard.publish(old_run, document, pngs, position_grid=grid, position_path=path)
            immutable_json(root / "algo08v3-release.json", dict(release, session_id=session, decision=decision))
            return CompletedProcess(command, 0, "", "")

        monkeypatch.setattr(algo08v3.subprocess, "run", launch)

    return dict(store=store, recording=recording, region=region, region_file=region_file, pngs=pngs,
                old_run=old_run, binding=binding, calls=calls, launcher=make_launcher, release=release)


def _publish(fixture, **options):
    return algo08v3.publish_algo08v3(fixture["recording"], store=fixture["store"],
                                   region_file=fixture["region_file"], **options)


@pytest.mark.parametrize("decision", ["complete", "withheld"])
def test_publish_algo08v3_rebinds_frozen_products_and_reuses_completed_run(publication, decision):
    publication["launcher"](decision)
    receipt = _publish(publication)
    assert receipt["decision"] == decision
    assert receipt["execution_release"] == EXECUTION_RELEASE
    assert receipt["terminal_sha256"] != publication["binding"]["terminal_sha256"]
    assert receipt["run_id"].startswith("algo08-v3-")
    standard = FastStandardAnalysisStore(publication["store"].root)
    manifest = standard.detail(receipt["run_id"])
    assert manifest["model_version"] == ALGO08V3
    assert standard_label(manifest["model_version"]) == EXECUTION_RELEASE["version"]
    assert manifest["terminal_sha256"] == receipt["terminal_sha256"]
    assert manifest["source_terminal_sha256"] == publication["binding"]["terminal_sha256"]
    assert standard.detail(publication["old_run"])["state"] == "pending"
    report = publication["store"].detail(receipt["run_id"])
    assert report["model_version"] == ALGO08V3
    assert report["points"] == [{"cfo_hz": 17.0}]
    if decision == "complete":
        for item in manifest["artifacts"]:
            assert standard.artifact(receipt["run_id"], item["name"], item["sha256"]) == publication["pngs"][item["name"]]
        assert len(manifest["artifacts"]) == len(PLOTS)
        assert standard.position_grid(receipt["run_id"])["binding"]["run_id"] == receipt["run_id"]
        path = standard.position_path(receipt["run_id"])
        assert path["stages"][-1]["model_version"] == path["selected_model"] == ALGO08V3
    else:
        assert manifest["reason"] == "no active tracks"
        assert manifest["artifacts"] == []
    assert _publish(publication) == receipt
    assert len(publication["calls"]) == 1


def test_resume_sealed_frozen_execution_after_report_write_failure(monkeypatch, publication):
    publication["launcher"]("complete")
    store = publication["store"]
    publish = store.publish
    with monkeypatch.context() as fault:
        def interrupted(*args):
            raise OSError("report write interrupted")

        fault.setattr(store, "publish", interrupted)
        with pytest.raises(OSError, match="report write interrupted"):
            _publish(publication)
    assert store.publish == publish
    assert _publish(publication)["decision"] == "complete"
    assert len(publication["calls"]) == 1


def test_refuses_mismatched_release(publication):
    publication["launcher"]("withheld")
    publication["release"]["version"] = "ALGO08v2"
    with pytest.raises(ValueError, match="Unrecognized ALGO08v3 execution release"):
        _publish(publication)
    assert publication["store"].page()["items"] == []


def test_existing_result_rejects_corrupt_artifact(publication):
    publication["launcher"]("complete")
    receipt = _publish(publication)
    standard = FastStandardAnalysisStore(publication["store"].root)
    run_id = receipt["run_id"]
    artifact = standard.detail(run_id)["artifacts"][0]
    path = standard.folder(run_id) / (artifact["sha256"].removeprefix("sha256:") + ".png")
    path.write_bytes(b"incomplete")
    with pytest.raises(ValueError, match="figure integrity"):
        _publish(publication)
    assert len(publication["calls"]) == 1


def test_reference_attaches_to_sealed_result_on_retry_without_affecting_it(publication):
    publication["launcher"]("complete")
    receipt = _publish(publication)
    standard = FastStandardAnalysisStore(publication["store"].root)
    run_id = receipt["run_id"]
    assert standard.detail(run_id)["evaluation_reference"] is None
    assert _publish(publication, evaluation_reference=(37.8, -122.5)) == receipt
    detail = standard.detail(run_id)
    assert detail["evaluation_reference"]["latitude_deg"] == 37.8
    assert detail["arms"]["fitted_c"]["evaluation_error_m"] > 0
    assert detail["terminal_sha256"] == receipt["terminal_sha256"]
    assert len(publication["calls"]) == 1


def test_frozen_launcher_changes_only_known_display_labels(tmp_path):
    from matplotlib.text import Text
    from leo.processing.algo08v3_launcher import run

    launcher = tmp_path / "run"
    launcher.write_text(
        'import sys\nfrom matplotlib.text import Text\n'
        'assert sys.argv[1:] == ["--flag"]\n'
        'assert Text(text="ALGO08v2 selected result · fitted c").get_text() == "ALGO08v3 selected result · fitted c"\n'
        'assert Text(text="scan · ALGO08v2 · RMS for every").get_text() == "scan · ALGO08v3 · RMS for every"\n'
        'assert Text(text="scan\\nALGO08v2 · diagnostic position map\\n").get_text() == '
        '"scan\\nALGO08v3 · diagnostic position map\\n"\n'
        'assert Text(text="ALGO08v2").get_text() == "ALGO08v2"\n'
    )
    run(str(launcher), ["--flag"])
    assert Text(text="ALGO08v2 selected result · fitted c").get_text() == "ALGO08v2 selected result · fitted c"
