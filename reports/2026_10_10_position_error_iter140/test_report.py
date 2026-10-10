import json

import pytest
from report import load_receipts, plot, summarize


def test_full_terminal_gate_and_explicit_fallback(tmp_path):
    members = [dict(label=f"case-{i:03}") for i in range(193)]
    with pytest.raises(ValueError, match="Not terminal"):
        load_receipts(dict(members=members), "fixed", tmp_path)
    rows = [
        dict(
            label="one",
            dataset="DS16",
            arms={
                a: dict(
                    archive=dict(qualified=True, error_km=2),
                    timestamp=None,
                    phase=dict(qualified=True, error_km=1),
                )
                for a in ("fitted-c", "zero-c")
            },
        )
    ]
    output = summarize(rows)
    arm = output["full"]["fitted-c"]
    assert arm["metrics"]["timestamp"]["position_metrics_withheld"]
    assert arm["archive_fallback_sensitivity"]["timestamp"]["mean_km"] == 2
    assert arm["archive_fallback_sensitivity"]["timestamp"]["archive_fallbacks"] == 1
    json.dumps(output, allow_nan=False)
    path = tmp_path / "synthetic.png"
    plot(rows, path)
    assert path.read_bytes().startswith(b"\x89PNG")


def test_all193_terminal_foreign_last_claim_blocks_evaluation_port(tmp_path, monkeypatch):
    import hashlib

    import report

    members = [dict(label=f"case-{i:03}") for i in range(193)]
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps(dict(members=members, sources={}, inputs={})))
    digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
    results = tmp_path / "results"
    results.mkdir()
    for binding in members:
        label = binding["label"]
        (results / (label + ".json")).write_text(
            json.dumps(dict(label=label, protocol_sha256=digest, status="failed"))
        )
        (results / (label + ".claim.json")).write_text(
            json.dumps(dict(label=label, protocol_sha256=digest))
        )
    (results / "case-192.claim.json").write_text(
        json.dumps(dict(label="foreign", protocol_sha256=digest))
    )
    monkeypatch.setattr(report, "HERE", tmp_path)
    monkeypatch.setattr(
        report.runpy,
        "run_path",
        lambda *a, **k: pytest.fail(
            "Evaluation authority must remain unopened before all bindings seal"
        ),
    )
    with pytest.raises(ValueError, match="Foreign claim"):
        report.main()
