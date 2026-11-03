from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace as Obj

import pytest

ROOT = Path(__file__).parents[2]
SPEC = importlib.util.spec_from_file_location(
    "capture_pose_tool", ROOT / "tools/bind_adaptive_capture_pose.py"
)
assert SPEC is not None and SPEC.loader is not None
tool = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = tool
SPEC.loader.exec_module(tool)


@pytest.fixture
def authority():
    return tool.CapturePoseAuthority.model_validate_json(
        (ROOT / "deploy/station/gauss-r20-roof-20260926-v1.json").read_bytes()
    )


def session(a, *, start=None, qualified=True, serial=None):
    start = a.valid_from_utc_ns + 100 if start is None else start
    return Obj(
        session_id="scan-fw-test",
        manifest_sha256="sha256:" + "a" * 64,
        manifest=Obj(
            receipt=Obj(
                radio_id=a.radio_id,
                radio_serial=serial or a.radio_serial,
                plan=Obj(geometry=Obj(receiver_ids=(0, 1))),
            ),
            timing=Obj(
                first_sample_earliest_utc_ns=start,
                terminal_realtime_ns=start + 100,
                qualified=qualified,
            ),
        ),
    )


def test_new_capture_preserves_unknowns_and_mapping_evidence(authority):
    result = tool.bind(session(authority), authority)
    assert result["pose_authority"]["altitude_m"] is None
    assert result["pose_authority"]["phase_center_baseline_enu_m"] is None
    assert [r["azimuth_deg"] for r in result["pose_authority"]["receivers"]] == [270, 90]
    assert all(r["mapping_status"] == "provisional" for r in result["pose_authority"]["receivers"])


def test_excludes_overlap_other_radio_and_unqualified_time(authority):
    assert tool.bind(session(authority, start=authority.valid_from_utc_ns - 1), authority) is None
    assert tool.bind(session(authority, serial="other-radio"), authority) is None
    assert tool.bind(session(authority, qualified=False), authority) is None
    missing = session(authority)
    missing.manifest.timing = None
    assert tool.bind(missing, authority) is None


def test_interval_end_and_publication_time_are_not_confused(authority):
    end = authority.model_copy(update={"valid_until_utc_ns": authority.valid_from_utc_ns + 150})
    assert tool.bind(session(end), end) is None
    old = session(authority, start=authority.valid_from_utc_ns - 1000)
    old.manifest.created_utc_ns = authority.valid_from_utc_ns + 999999
    assert tool.bind(old, authority) is None


def test_idempotent_immutable_companion(tmp_path, authority):
    doc = tool.bind(session(authority), authority)
    assert tool.publish(tmp_path, doc)
    assert not tool.publish(tmp_path, doc)
    assert json.loads((tmp_path / "scan-fw-test.json").read_bytes()) == doc
    with pytest.raises(ValueError, match="differs"):
        tool.publish(tmp_path, {**doc, "manifest_sha256": "changed"})
    with pytest.raises(ValueError, match="unsafe"):
        tool.publish(tmp_path, {**doc, "session_id": "../escape"})


def test_authority_rejects_ambiguous_receiver_mapping(authority):
    value = authority.model_dump(mode="json")
    value["receivers"][1]["receiver_id"] = 0
    with pytest.raises(ValueError, match="distinct"):
        tool.CapturePoseAuthority.model_validate(value)


def test_nominal_fixture_matches_existing_design(authority):
    import math

    reference = json.loads(
        (ROOT / "deploy/station/gauss-r21-lt3d-001a-20260920-v1.json").read_bytes()
    )["fixtures"][0]
    assert reference["fixture_digest"] == authority.fixture_digest
    left, right = reference["slots"]
    separation = right["mount_reference_position_m"]["x"] - left["mount_reference_position_m"]["x"]
    assert separation == pytest.approx(authority.nominal_mount_separation_m)
    tilt = math.degrees(math.acos(right["mount_axis_unit"]["z"]))
    assert tilt == pytest.approx(authority.nominal_outward_tilt_deg)


def test_lt3d_004b_preserves_orientation_and_binds_printable_design(authority):
    new = tool.CapturePoseAuthority.model_validate_json(
        (ROOT / "deploy/station/gauss-r20-lt3d-004b-20261001-v1.json").read_bytes()
    )
    assert new.receivers == authority.receivers
    assert (new.latitude_deg, new.longitude_deg) == (authority.latitude_deg, authority.longitude_deg)
    assert new.fixture_part_id == "LT3D-004B"
    stl = ROOT / "3d_prints/LT3D-004-opposite-side-lnbf-snap-stand/LT3D-004B-40deg-snap-stand.stl"
    assert new.fixture_digest == tool.digest(stl.read_bytes())
    measured = json.loads((stl.parent / "verification.json").read_bytes())["variants"]["LT3D-004B"]
    assert new.nominal_mount_separation_m == pytest.approx(measured["spacing_mm"] / 1000)
    assert 2 * new.nominal_outward_tilt_deg == measured["included_angle_deg"]
    assert new.phase_center_baseline_enu_m is None
    assert all(r.elevation_deg is None for r in new.receivers)


def test_lt3d_004b_is_prospective_and_companion_carries_full_authority(authority):
    new = tool.CapturePoseAuthority.model_validate_json(
        (ROOT / "deploy/station/gauss-r20-lt3d-004b-20261001-v1.json").read_bytes()
    )
    assert tool.bind(session(authority), new) is None
    assert tool.bind(session(new, start=new.valid_from_utc_ns - 1), new) is None
    bound = tool.bind(session(new, start=new.valid_from_utc_ns), new)
    assert bound["pose_authority"] == new.model_dump(mode="json")
    assert bound["pose_authority_digest"] == tool.digest(tool.canonical(bound["pose_authority"]))
