"""Only a canary of the installed runtime authorizes the ALGO02 handoff."""

import pytest
from activate_algo02_runtime import check_canary, configuration


def test_configuration_preserves_interpreter_and_whole_job_budget():
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
