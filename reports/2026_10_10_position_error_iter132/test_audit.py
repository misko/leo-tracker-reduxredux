import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location("audit132_test", Path(__file__).with_name("audit.py"))
audit = importlib.util.module_from_spec(spec)
spec.loader.exec_module(audit)


def fixture(tmp_path):
    projection = {
        "regional": {
            "session_id": "session",
            "input_manifest_sha256": "input",
            "analysis_manifest_sha256": "analysis",
        },
        "archive": {
            "stages": {
                "B7": {
                    arm: {"vector": [1, 2], "clock_coefficients": [3], "objective": 6}
                    for arm in ("fitted-c", "zero-c")
                }
            }
        },
    }
    path = tmp_path / "projection.json"
    path.write_text(json.dumps(projection))
    return {
        "label": "DS16-020",
        "session_id": "session",
        "projection_path": str(path),
        "projection_sha256": audit.digest(path),
        "expected_input_binding": {"physical": "signature"},
    }


def test_clean_loader_and_same_both_arm_endpoints(monkeypatch, tmp_path):
    binding = fixture(tmp_path)
    calls = []
    model = SimpleNamespace(
        evaluate_joint=lambda vector, clock: (float(vector.sum() + clock.sum()),)
    )
    monkeypatch.setattr(
        audit, "module", lambda *args: SimpleNamespace(reconstruct=lambda *args: model)
    )

    def loader(value):
        calls.append(value)
        return {
            "identity": {"input_manifest_sha256": "input", "analysis_manifest_sha256": "analysis"}
        }

    result = audit.check_member(binding, loader, {})
    assert calls == [binding]
    assert result["optimizer_calls"] == 0
    assert set(result["arms"]) == {"fitted-c", "zero-c"}
    assert all(arm["delta"] == 0 for arm in result["arms"].values())
    json.dumps(result, allow_nan=False)


def test_projection_corruption_prevents_public_input_access(tmp_path):
    binding = fixture(tmp_path)
    binding["projection_sha256"] = "changed"
    with pytest.raises(ValueError, match="projection changed"):
        audit.check_member(binding, lambda _: pytest.fail("Must not load inputs"), {})


def test_objective_mismatch_is_failure_not_new_fit(monkeypatch, tmp_path):
    binding = fixture(tmp_path)
    model = SimpleNamespace(evaluate_joint=lambda *args: (7,))
    monkeypatch.setattr(
        audit, "module", lambda *args: SimpleNamespace(reconstruct=lambda *args: model)
    )
    with pytest.raises(ValueError, match="objective mismatch fitted-c"):
        audit.check_member(
            binding,
            lambda _: {
                "identity": {
                    "input_manifest_sha256": "input",
                    "analysis_manifest_sha256": "analysis",
                }
            },
            {},
        )
