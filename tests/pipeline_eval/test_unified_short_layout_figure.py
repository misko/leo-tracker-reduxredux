import gzip
import json
from pathlib import Path
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"
sys.path.insert(0, str(ROOT))
import unified_short_layout_figure as chart


def test_plot_uses_both_matched_clocks_and_only_returned_positions(tmp_path, monkeypatch):
    receipt = json.loads(gzip.decompress((ROOT / "measurements/unified-short-layout.json.gz").read_bytes()))
    saved = []
    close = chart.plt.close
    monkeypatch.setattr(chart.plt, "close", saved.append)
    output = tmp_path / "figure.png"
    chart.draw(receipt, output)
    figure = saved[-1]
    try:
        timing, error = figure.axes
        for series, name in enumerate(("stock", "candidate")):
            rows = [receipt["observations"][case]["rows"][name] for case in ("weak", "tiny")]
            assert [bar.get_width() for bar in timing.containers[series]] == [r["clock"]["elapsed_s"] for r in rows]
            assert [bar.get_width() for bar in error.containers[series]] == [
                rows[0]["errors_km"][k] for k in ("c0", "fitted_c")]
        assert [line.get_xdata()[0] for line in timing.lines] == pytest.approx(
            [bar.get_width() / 2 for bar in timing.containers[0]])
        assert output.read_bytes().startswith(b"\x89PNG")
    finally:
        close(figure)
