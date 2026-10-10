import json

import pytest
from project import read_selected


def fixture():
    return dict(
        protocol_sha256="fixed",
        label="DS16-001",
        phase="candidate",
        status="complete",
        input_binding={"input_digest": "physical"},
        regions={"reference": {"latitude": 999}},
        operational={
            a: dict(
                accepted_stage="B7",
                satellites=[1, 2],
                fit=dict(
                    vector=[1],
                    clock_coefficients=[2],
                    objective=3,
                    converged=True,
                    joint_state={"clock_nodes_s": [0, 1]},
                ),
            )
            for a in ("fitted-c", "zero-c")
        },
        reference_errors=[99],
        attempts={"unused": [0]},
    )


def test_reference_perturbation_never_changes_inference_projection(tmp_path):
    value = fixture()
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(value, indent=2) + "\n")
    before = read_selected(path)
    value["reference_errors"] = [-900]
    value["regions"] = {"reference": "poisoned"}
    path.write_text(json.dumps(value, indent=2) + "\n")
    after = read_selected(path)
    before.pop("preparation_source_sha256")
    after.pop("preparation_source_sha256")
    assert before == after
    assert "reference_errors" not in after


def test_nonterminal_source_rejected(tmp_path):
    value = fixture()
    value["status"] = "failed"
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(value, indent=2))
    with pytest.raises(ValueError, match="Incomplete"):
        read_selected(path)
