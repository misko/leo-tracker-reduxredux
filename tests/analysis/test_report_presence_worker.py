import json
from pathlib import Path

from tools.qualify_native_presence import digest
from tools.qualify_presence_worker import verify
from tools.report_presence_worker import render
from tools.summarize_presence_holdout import metrics

EVIDENCE = Path(__file__).resolve().parents[2] / "reports/figures/2026_09_08_arm_presence_worker"


def test_checkpoint_accounting_reproduces_from_saved_evidence():
    holdout = json.loads((EVIDENCE / "holdout-summary.json").read_text())
    assert metrics(json.loads((EVIDENCE / "results.json").read_text())) == holdout["rates"]
    assert holdout["results_sha256"] == digest(EVIDENCE / "results.json")
    for rate in (2500000, 5000000):
        raw = EVIDENCE / f"paced-{rate}.txt"
        manifest = EVIDENCE / f"pack-{rate}-manifest.json"
        checked = verify(raw.read_text(), json.loads(manifest.read_text()), 300000)
        saved = json.loads((EVIDENCE / f"paced-{rate}-summary.json").read_text())
        assert all(saved[key] == value for key, value in checked.items())
        assert saved["raw_sha256"] == digest(raw)
        assert saved["manifest_sha256"] == digest(manifest)
        assert saved["executions"] == 2381
    assert saved["timings"]["total_cpu_ms"]["p99"] > 100  # Do not round a failed gate into a pass.


def test_checkpoint_figure_renders_from_verified_summaries(tmp_path):
    output = tmp_path / "figure.png"
    render(
        json.loads((EVIDENCE / "holdout-summary.json").read_text()),
        {
            str(rate): json.loads((EVIDENCE / f"paced-{rate}-summary.json").read_text())
            for rate in (2500000, 5000000)
        },
        output,
    )
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")
    assert output.stat().st_size > 30000
