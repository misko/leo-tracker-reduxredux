from pathlib import Path
from hashlib import sha256
import json

import pytest

from reports.ALGO08.v3 import history_risk_0016_raw as runner


@pytest.fixture
def stage(tmp_path, monkeypatch):
    monkeypatch.setattr(runner, "TMPFS", tmp_path)
    monkeypatch.setattr(runner, "STAGING_LOCK", tmp_path/"custody.lock")
    root = tmp_path/"custody"
    segment = root/runner.RECORDING.name/"segment"
    segment.mkdir(parents=True)
    signed = {"files": [
        dict(relative="segment/payload", kind="payload", signed_bytes=8, signed_sha256="sha256:"+"a"*64),
        dict(relative="segment/index", kind="index", signed_bytes=2, signed_sha256="sha256:"+"b"*64),
        dict(relative="segment/manifest", kind="manifest", signed_bytes=2, signed_sha256="sha256:"+"c"*64),
    ]}
    for name in ("index", "manifest"):
        (segment/name).write_bytes(b"{}")
    return root, segment, signed


def test_readiness_never_opens_a_payload_or_a_catalogue(stage, monkeypatch):
    root, segment, signed = stage
    (segment/"payload").write_bytes(b"abc")
    real_open = runner.os.open

    def directory_only(path, flags, *args, **kwargs):
        assert flags & runner.os.O_DIRECTORY
        return real_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(runner.os, "open", directory_only)
    monkeypatch.setattr(Path, "read_bytes", lambda _: pytest.fail("readiness tried reading file data"))
    result = runner.readiness(root, signed)
    assert result["missing_bytes"] == 5 and result["kind_totals"]["payload"]["missing_bytes"] == 5
    assert result["staged_bytes"] == 7 and result["complete_files"] == 2
    assert result["workers_started"] == result["waveform_bytes_read"] == result["catalogue_body_bytes_read"] == 0
    assert not result["ready"]


def test_missing_or_unsafe_member_cannot_start_any_worker(stage, monkeypatch):
    root, segment, signed = stage
    (root/"staging.json").write_text("{}")
    monkeypatch.setattr(runner, "launch_ready", lambda *args: pytest.fail("incomplete stage started the worker"))
    result = runner.launch(root/"output", root, signed)
    assert result["missing_bytes"] == 8 and not result["ready"]
    (segment/"payload").symlink_to("/srv/bulk/must-not-be-opened")
    result = runner.launch(root/"output", root, signed)
    assert any(row["state"] == "unsafe_or_unavailable" for row in result["files"])
    assert not result["ready"] and not (root/"output").exists()


def test_complete_extents_require_custody_and_admit_exactly_one_pair(stage, monkeypatch):
    root, segment, signed = stage
    (segment/"payload").write_bytes(b"abcdefgh")
    assert not runner.readiness(root, signed)["ready"]
    (root/"staging.json").write_text("{}")
    seen = []
    monkeypatch.setattr(runner, "launch_ready", lambda *args: seen.append(args))
    output = root/"output"
    assert runner.launch(output, root, signed) is None
    (called_output, called_root, called_signed, check), = seen
    assert (called_output, called_root, called_signed) == (output, root, signed)
    assert check["ready"] and check["missing_bytes"] == 0 and check["complete_files"] == 3


def test_enrolled_command_binds_original_region_archive_and_current_frozen_solver(tmp_path):
    import exact_named_raw

    request, _, _, _ = runner.references()
    libs = runner.pinned_archive(runner.LIBRARIES)["raw_binding"]["libraries"]
    result = runner.arguments(tmp_path, request, Path("/opt/leo-algo08/algo08v3/run"), Path("/opt/release/python"), libs)
    a, b = (result[mode] for mode in runner.ORDER)
    for flag, value in (("--recording", str(runner.RECORDING)), ("--region", request["region"]),
                        ("--archive", request["archive"]["root"])):
        assert a[a.index(flag)+1] == b[b.index(flag)+1] == value
    assert a[a.index("--archive-sha256")+1] == request["archive"]["snapshots_sha256"]
    assert "--history-risk-route" in a and "--history-risk-route" not in b
    assert "--portable-orbit-index" not in a
    candidate = exact_named_raw.parser().parse_args(a[6:])
    assert candidate.history_risk_route and candidate.eight_ms_native_history and candidate.held_anchor_route
    assert candidate.portable_orbit_index is None and candidate.output == tmp_path/"candidate"
    assert runner.route_options(a)["strict_packed_eight"] is False


def test_only_completed_custody_that_matches_original_extents_is_accepted(stage, monkeypatch):
    root, segment, signed = stage
    signed.update(inventory_sha256="sha256:enrolled", raw_authority="sha256:enrolled-sha")
    monkeypatch.setattr(runner, "SIGNED_BYTES", 12)
    files = runner.stage_files(signed)
    document = dict(recording=str(runner.RECORDING), inventory=signed["inventory_sha256"],
                    raw_authority=signed["raw_authority"], files=files,
                    extents={k: v[0][1] for k,v in files.items()}, copied_bytes=12)
    receipt = root/"staging.json"
    receipt.write_text(json.dumps(document))
    assert len(runner.require_custody(root, signed)) == 64
    document["copied_bytes"] = 9
    receipt.write_text(json.dumps(document))
    with pytest.raises(ValueError, match="does not bind"):
        runner.require_custody(root, signed)


def test_missing_custody_directory_reports_the_full_missing_extent(stage):
    root, _, signed = stage
    status = runner.readiness(root/"absent", signed)
    assert not status["ready"] and status["staged_bytes"] == 0 and status["missing_bytes"] == 12
    assert status["workers_started"] == 0


def test_optional_adapter_source_changes_are_recorded_without_relaxing_active_science(tmp_path):
    def put(path, body):
        (tmp_path/path).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path/path).write_bytes(body)
        return sha256(body).hexdigest()

    scientific = "reports/ALGO08/v3/history_risk_route.py"
    expected = {scientific: put(scientific, b"reviewed earlier-orbit gate")}
    expected.update({path: put(path, b"ordinary entry") for path in runner.ADAPTERS})
    edited = put(runner.ADAPTERS[0], b"ordinary entry plus an unused optional renderer")
    frozen, observed = runner.frozen_sources(tmp_path, expected)
    assert frozen == {scientific: expected[scientific]}
    assert observed[runner.ADAPTERS[0]] == edited != expected[runner.ADAPTERS[0]]
    put(scientific, b"changed signed-model decision")
    with pytest.raises(ValueError, match="Unreviewed"):
        runner.frozen_sources(tmp_path, expected)
