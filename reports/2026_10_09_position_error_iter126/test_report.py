import hashlib
import json
import runpy
from pathlib import Path


def test_full_coverage_plot_and_json(tmp_path, monkeypatch):
    api = runpy.run_path(str(Path(__file__).with_name("report.py")))
    members = [{"member": {"inventory_label": f"test{i}"}} for i in range(12)]
    (tmp_path / "protocol.json").write_text(json.dumps({"members": members}))
    digest = hashlib.sha256((tmp_path / "protocol.json").read_bytes()).hexdigest()
    (tmp_path / "results").mkdir()
    for member in members:
        arm = {
            "original_score_parity_delta": 0.0,
            "nll_delta": 1.0,
            "normalizer_delta": 0.0,
            "prediction_delta_rms_hz": 2.0,
            "visibility_changed": 0,
        }
        row = {
            "member": member["member"],
            "protocol_sha256": digest,
            "status": "complete",
            "elapsed_s": 1.0,
            "arms": {a: arm for a in ("fitted-c", "zero-c")},
        }
        (tmp_path / "results" / f"{member['member']['inventory_label']}.json").write_text(
            json.dumps(row)
        )
    monkeypatch.setitem(api["main"].__globals__, "HERE", tmp_path)
    api["main"]()
    summary = json.loads((tmp_path / "summary.json").read_text())
    assert summary["coverage"]["complete"] == 12
    assert summary["full12_metrics"]["fitted-c"]["nll_delta"]["median"] == 1.0
    assert (tmp_path / "comparison.png").stat().st_size > 1000
