"""Only a canary of the installed runtime authorizes the ALGO02 handoff."""

import activate_algo02_runtime as activation
import pytest
from activate_algo02_runtime import OVERRIDE, check_canary, configuration


def test_configuration_preserves_interpreter_and_whole_job_budget():
    assert OVERRIDE.name > "release.conf"
    text = configuration(dict(release="/opt/candidate", runtime_manifest_sha256="pin",
                              python="/opt/original/venv/bin/python"))
    assert "--maximum-seconds 1200" in text
    assert "ExecStart=/opt/original/venv/bin/python -B -m leo.cli.fast_graph_position" in text
    assert "Environment=PYTHONPATH=/opt/candidate/src:/opt/candidate/tools" in text
    assert "verify --root /opt/candidate --pin pin" in text


@pytest.mark.parametrize("field,value", [(None, None), ("exact", False),
    ("runtime_root", "/research/prototype"), ("runtime_manifest_sha256", "wrong"),
    ("both_calibration_arms_required", False), ("difference_count", 1)])
def test_installed_canary_identity_and_science_required(field, value):
    stage = dict(release="/opt/candidate", runtime_manifest_sha256="pin")
    parity = dict(exact=True, tolerance=0, files=6, difference_count=0,
                  both_calibration_arms_required=True, frozen_inputs_verified=True,
                  read_audit={"verified": True}, runtime_root=stage["release"],
                  runtime_manifest_sha256="pin")
    if field is None:
        check_canary(stage, parity)
    else:
        parity[field] = value
        with pytest.raises(ValueError, match="installed ALGO02 canary"):
            check_canary(stage, parity)


@pytest.mark.parametrize("busy", [dict(children=[100], job_owner_files=[]),
                                  dict(children=[], job_owner_files=["job/owner.lock"])])
def test_busy_watcher_is_not_signalled(monkeypatch, busy):
    monkeypatch.setattr(activation, "check_canary", lambda *args: None)
    monkeypatch.setattr(activation, "property_value", lambda name: "42")
    monkeypatch.setattr(activation, "activity", lambda pid: dict(busy, idle=False))

    def forbidden(*args):
        raise AssertionError("Busy watcher must not be opened for signals")

    monkeypatch.setattr(activation.os, "pidfd_open", forbidden)
    stage = dict(release="/opt/leo-fast-graph-runtime-algo02/qualified",
                 runtime_manifest_sha256="pin")
    monkeypatch.setattr(activation, "verify", lambda *args: stage)
    assert not activation.activate(stage, {}, execute=True)["activated"]


@pytest.mark.parametrize("field,value", [(None, None), ("exact", False),
    ("candidate_runtime_manifest_sha256", "wrong"), ("candidate_source_sha256", "wrong"),
    ("fixture_sha256", "wrong"), ("cases", 1), ("changed_states_hidden", True)])
def test_discovery_canary_binds_installed_bytes_and_full_inventory(field, value):
    stage = dict(qualification="discovery", release="/opt/candidate", discovery_cases=897,
                 discovery_fixture_sha256="fixture", discovery_store_sha256="store",
                 runtime_manifest_sha256="pin", numerical_changes=[])
    parity = dict(exact=True, cases=897, fixture_sha256="fixture",
                  candidate_source_sha256="store", candidate_runtime="/opt/candidate",
                  candidate_runtime_manifest_sha256="pin", changed_states_hidden=False)
    if field is None:
        check_canary(stage, parity)
        stage["numerical_changes"] = ["scientific.py"]
    else:
        parity[field] = value
    with pytest.raises(ValueError, match="discovery canary"):
        check_canary(stage, parity)
