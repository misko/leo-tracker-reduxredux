from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from leo.api.app import create_app
from leo.api.production import ProductionSettings
from leo.operations.native_recording_registry import NativeRecordingRegistry
from leo.presentation.fixtures import build_fixture_repository
from tests.cli.test_native_recording_bundle import bundle, digest


def setup_recording(tmp_path):
    path, _ = bundle(tmp_path)
    registry = NativeRecordingRegistry(tmp_path / "registry")
    bundle_id = registry.register(path, expected_sha256=digest(path.read_bytes()))
    app = create_app(
        build_fixture_repository(tmp_path), artifact_root=tmp_path, native_recordings=registry
    )
    return path, registry, bundle_id, TestClient(app)


def test_native_recording_pages_preserve_failed_outcome_and_exact_sample_counter(tmp_path):
    path, registry, bundle_id, client = setup_recording(tmp_path)
    page = client.get("/api/v1/native-recordings?limit=1").json()
    assert page["total"] == 1 and page["next_cursor"] is None
    summary = page["items"][0]["summary"]
    assert summary["runtime_result"] == -5 and summary["owner_status"] == "failed"
    assert not summary["physical_precision_qualified"]
    assert not summary["original_native_iq_verified"]
    first = client.get(f"/api/v1/native-recordings/{bundle_id}?limit=1").json()
    assert first["summary"] == summary
    row = first["rows"][0]
    source = json.loads((path.parent / "source-binding.json").read_text())
    measurement = row["measurement"]
    assert isinstance(measurement["native_start_sample"], str)
    expected = (int(measurement["native_start_sample"]) - int(source["native_origin"])) / 60e6
    assert row["coarse_relative_scheduled_start_s"] == expected
    assert row["coarse_relative_refined_start_s"] == expected + measurement["delay_s"]
    assert "manifest_path" not in json.dumps(first)
    assert str(tmp_path) not in json.dumps(first)
    assert registry.register(path, expected_sha256=bundle_id) == bundle_id
    assert len(list(registry.root.iterdir())) == 1


def test_rejections_remain_visible_and_do_not_affect_supported_cfo_range(tmp_path):
    _, _, bundle_id, client = setup_recording(tmp_path)
    response = client.get(f"/api/v1/native-recordings/{bundle_id}").json()
    measurements = [row["measurement"] for row in response["rows"]]
    supported = [row["cfo_hz"] for row in measurements if row["supported"]]
    rejected = [row for row in measurements if not row["supported"]]
    assert rejected
    assert response["summary"]["supported_cfo_max_hz"] == max(supported)
    first = client.get(f"/api/v1/native-recordings/{bundle_id}?limit=1").json()
    second = client.get(
        f"/api/v1/native-recordings/{bundle_id}?limit=1&cursor={first['next_cursor']}"
    ).json()
    assert (
        second["rows"][0]["measurement"]["sequence"] != first["rows"][0]["measurement"]["sequence"]
    )


@pytest.mark.parametrize("corruption", ["missing", "modified", "registration", "symlink"])
def test_changed_registration_or_bundle_remains_listed_but_unavailable(tmp_path, corruption):
    path, registry, bundle_id, client = setup_recording(tmp_path)
    target = path.parent / "owner-receipt.json"
    if corruption == "missing":
        target.unlink()
    elif corruption == "modified":
        target.write_text("modified")
    elif corruption == "registration":
        (registry.root / (bundle_id + ".json")).write_text("{}")
    else:
        target.unlink()
        target.symlink_to(path)
    page = client.get("/api/v1/native-recordings").json()
    assert page["items"] == [
        {"bundle_id": bundle_id, "summary": None, "error": "integrity_unavailable"}
    ]
    response = client.get(f"/api/v1/native-recordings/{bundle_id}")
    assert response.status_code == 409
    assert str(tmp_path) not in response.text


def test_unregistered_ids_invalid_pages_and_disabled_reader(tmp_path):
    _, _, bundle_id, client = setup_recording(tmp_path)
    assert client.get("/api/v1/native-recordings/" + "0" * 64).status_code == 404
    for url in [
        "/api/v1/native-recordings?limit=101",
        "/api/v1/native-recordings?cursor=-1",
        f"/api/v1/native-recordings/{bundle_id}?limit=1001",
        "/api/v1/native-recordings/not-a-digest",
    ]:
        assert client.get(url).status_code == 422
    assert client.post("/api/v1/native-recordings").status_code == 405
    disabled = TestClient(create_app(build_fixture_repository(tmp_path), artifact_root=tmp_path))
    assert disabled.get("/api/v1/native-recordings").status_code == 503
    assert disabled.get(f"/api/v1/native-recordings/{bundle_id}").status_code == 503


def test_cli_registers_without_copying_payloads_and_discovers_new_entries(tmp_path):
    path, _ = bundle(tmp_path)
    root = tmp_path / "registry"
    reader = NativeRecordingRegistry(root)
    assert reader.list_recordings().total == 0 and not root.exists()
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "leo.cli.native_recording_register",
            "--manifest",
            str(path),
            "--sha256",
            digest(path.read_bytes()),
            "--registry",
            str(root),
        ],
        text=True,
        capture_output=True,
        check=True,
    )
    assert json.loads(result.stdout)["bundle_id"] == reader.list_recordings().items[0].bundle_id
    assert len(list(root.iterdir())) == 1
    assert list(root.iterdir())[0].stat().st_size < 1000


def test_registration_refuses_bad_pin_before_creating_output_and_qnap(tmp_path, monkeypatch):
    path, _ = bundle(tmp_path)
    registry = NativeRecordingRegistry(tmp_path / "registry")
    with pytest.raises(ValueError):
        registry.register(path, expected_sha256="0" * 64)
    assert not registry.root.exists()
    with pytest.raises(ValueError, match="absolute local"):
        NativeRecordingRegistry(Path("/mnt/qnap01/native"))
    monkeypatch.setenv("LEO_NATIVE_RECORDING_REGISTRY", str(registry.root))
    assert ProductionSettings.from_environment().native_recording_registry == registry.root
