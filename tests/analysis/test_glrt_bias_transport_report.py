import hashlib
import json

from tools.report_glrt_bias_transport import compact_receipts, diagnostic_summary


def test_reference_only_fit_cannot_pass_a_spatial_accuracy_gate():
    result = dict(
        completed=True,
        candidate_scope="conditional",
        search_plan=dict(random_points=0, refinement_rounds=0),
    )
    rows = [
        dict(
            east_m=0,
            north_m=0,
            distance_m=0,
            kind="reference",
            arms={"zero-c": dict(score=12, log_ratio=15)},
        )
    ]
    summary = diagnostic_summary(result, rows, "zero-c")
    assert summary["best_distance_m"] == 0
    assert summary["conditional_gate_met"] is None
    result["search_plan"] = dict(random_points=12, refinement_rounds=3)
    result["completed"] = False
    assert diagnostic_summary(result, rows, "zero-c")["conditional_gate_met"] is False


def test_publication_compaction_preserves_values_and_original_receipt_digest(tmp_path):
    path = tmp_path / "result.json"
    values = dict(score=4337.287622678174, phase_s=[0.0, -0.0, 1e-12], input_digest="unchanged")
    original = (json.dumps(values, indent=2) + "\n").encode()
    path.write_bytes(original)
    compact_receipts(tmp_path)
    assert json.loads(path.read_bytes()) == values
    receipt = json.loads((tmp_path / "receipt-serialization.json").read_bytes())
    hashes = receipt["files"]["result.json"]
    assert hashes["original_sha256"] == hashlib.sha256(original).hexdigest()
    assert hashes["published_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
