"""Comparison reports must not present missing restarts as completed maps."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
import compare_dsx01_radial_figures as figures  # noqa: E402


def test_gallery_keeps_missing_configuration_pending(tmp_path, monkeypatch):
    output, original = tmp_path / "new", tmp_path / "old"
    output.mkdir()
    (output / "protocol.json").write_text(json.dumps(dict(
        methods=["ready", "waiting"], cases=["S01"], starts=list(range(13)),
    )))
    (output / "restart_summary.json").write_text(json.dumps([
        dict(case="S01", method="ready", arm=arm, start_id=0)
        for arm in ("c0", "fitted_c")
    ]))
    for method in ("ready", "waiting"):
        p = original / "S01" / "surfaces" / method / "loss_gradient.png"
        p.parent.mkdir(parents=True)
        p.write_bytes(b"original unchanged")
    p = output / "S01/ready/restart_basins.png"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"new")
    generated = []

    def draw(old, new, destination, title):
        generated.append(title)
        destination.write_bytes(b"paired")

    monkeypatch.setattr(figures, "paired_figure", draw)
    assert figures.generate(output, original)["comparisons"] == 1
    gallery = output / "comparisons/S01"
    assert "partial" in (gallery / "ready.md").read_text()
    assert "1/13" in (gallery / "ready.md").read_text()
    assert "**Pending:**" in (gallery / "waiting.md").read_text()
    assert "![New" not in (gallery / "waiting.md").read_text()
    assert "0/13" in (gallery / "README.md").read_text()
    assert (original / "S01/surfaces/ready/loss_gradient.png").read_bytes() == b"original unchanged"
    figures.generate(output, original)
    assert len(generated) == 1


def test_completion_requires_both_c_arms_to_cover_every_start(tmp_path):
    (tmp_path / "protocol.json").write_text(json.dumps(dict(
        methods=["method"], cases=["S01"], starts=[0, 1],
    )))
    (tmp_path / "restart_summary.json").write_text(json.dumps([
        dict(case="S01", method="method", arm=arm, start_id=start)
        for arm, start in [("c0", 0), ("c0", 1), ("fitted_c", 0)]
    ]))
    p = tmp_path / "S01/method/restart_basins.png"
    p.parent.mkdir(parents=True)
    p.write_bytes(b"figure")
    figures.generate(tmp_path, tmp_path / "original")
    rows = json.loads((tmp_path / "comparisons/availability.json").read_text())
    assert rows[0]["status"] == "partial"
