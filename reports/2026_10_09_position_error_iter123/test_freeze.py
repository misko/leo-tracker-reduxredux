import json

import freeze
import pytest


def test_freezer_binds_exact_retained_coarse_native_fit(tmp_path, monkeypatch):
    search = tmp_path / "search"
    here = tmp_path / "pilot"
    points = search / "results/DS18-022/points"
    points.mkdir(parents=True)
    here.mkdir()
    (here / "README.md").write_text("synthetic")
    seed = dict(satellite_indices=[0, 1], vector=[0.0, 0.0] + [0.0] * 7)
    records, regions = [], []
    for i in range(3):
        vector = [float(i), 0.0] + [0.0] * 7
        bootstrap = dict(seed, vector=vector)
        fitted = dict(vector=vector, objective=10.0 + i, converged=True)
        records.append(dict(point=vector[:2], receipt=dict(result=dict(bootstrap=bootstrap))))
        regions.append(dict(east_km=float(i), north_km=0.0, score=100.0 + i, spacing_km=5.0))
        (points / f"{i}.json").write_text(
            json.dumps(
                dict(
                    key=["point", float(i), 0.0, "fitted-c"],
                    status="complete",
                    protocol_sha256="digest",
                    value=dict(fit=fitted, scores={"native": {"objective": 10.0 + i}}),
                )
            )
        )
    (search / "coarse-import.json").write_text(
        json.dumps(dict(bank_numbers=[10, 20], records=records))
    )
    (search / "protocol.json").write_text(
        json.dumps(dict(source_sha256={}, input_sha256={}, binding={}, identity={}))
    )
    (points.parent / "result.json").write_text(
        json.dumps(
            dict(
                status="complete",
                point_failure_count=0,
                protocol_sha256="digest",
                searches={f"fitted-c:{p}": dict(regions=regions) for p in ("native", "fixed")},
            )
        )
    )
    monkeypatch.setattr(freeze, "ROOT", tmp_path)
    monkeypatch.setattr(freeze, "SEARCH", search)
    monkeypatch.setattr(freeze, "HERE", here)
    result = freeze.prepare()
    assert result["branches"]["native"] == result["branches"]["fixed"]
    assert result["branches"]["native"][0]["discovery_score"] == 100.0
    assert result["branches"]["native"][0]["original"]["fits"]["V16"]["fit"]["objective"] == 10.0
    assert len(result["input_sha256"]) == 5
    assert result["policy"]["fallback"] == "none"
    path = points / "0.json"
    bad = json.loads(path.read_text())
    bad["value"]["scores"]["native"]["objective"] = 1000.0
    path.write_text(json.dumps(bad))
    with pytest.raises(ValueError, match="native objective"):
        freeze.prepare()
