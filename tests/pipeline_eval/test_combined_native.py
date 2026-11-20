import json
from pathlib import Path

import pytest

from tools.pipeline_eval.qualification import combined_native_build as build
from tools.pipeline_eval.qualification import combined_native_eval as replay
from tools.pipeline_eval.qualification import combined_native_pace as pace
from tools.pipeline_eval.qualification.combined_native_position import typed_request


def test_parity_gate_covers_hints_support_and_candidates():
    rows = [{"receiver_id": 0, "candidates": [{"epoch": 735}]}]
    full = {"rows": rows, "gates": [True], "hints": [735], "support": [734, 735, 736]}

    def fingerprint(x):
        return {"sha256": replay.fingerprint(x)}

    roles = {role: fingerprint(full) for role in replay.ROLES}
    assert replay.same_roles(roles)
    for key in full:
        changed = roles | {"fused": fingerprint(full | {key: None})}
        assert not replay.same_roles(changed)


def test_pace_uses_one_declared_case_with_helper_cpu():
    assert (pace.MAIN, pace.HELPER) == replay.PINS
    original = pace.pace.CPUS.copy()
    with pace.raw_configuration():
        assert pace.pace.CPUS == {pace.CASE: pace.MAIN}
        assert pace.pace.MODES == (pace.MODE,)
        assert pace.pace.MODULE == pace.MODULE
    assert original == pace.pace.CPUS


def test_stage_manifest_uses_measured_native_inputs_and_output():
    report = build.REPORT
    stage = json.loads((report / "stage-figure.json").read_bytes())
    assert stage["version"] == 1
    seal = json.loads((report / stage["seal"]).read_bytes())
    for field in ("image", "pdf", "csv"):
        file = report / stage[field]
        assert replay._sha(Path(file)) == seal["files"][stage[field]]


def test_compact_runner_receives_the_same_digest_under_its_existing_field():
    entry = {"request_sha256": "request", "native_sha256": "native"}
    assert typed_request(entry) == entry | {"prepared_request_sha256": "request"}
    with pytest.raises(ValueError, match="digest fields disagree"):
        typed_request(entry | {"prepared_request_sha256": "different"})
