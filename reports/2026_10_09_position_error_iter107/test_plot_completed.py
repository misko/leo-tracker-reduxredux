import runpy
from pathlib import Path

import pytest

PLOT = runpy.run_path(str(Path(__file__).with_name("plot_completed.py")))


def fixture_data(withheld=False):
    return {
        "metrics": {"full_census_position_metrics_withheld": withheld},
        "rows": [
            {
                "label": f"DS16-{i:03d}",
                "arms": {
                    arm: {phase: {"error_km": i / 10} for phase in ("baseline", "candidate")}
                    for arm in ("fitted-c", "zero-c")
                },
            }
            for i in range(1, 64)
        ],
    }


def test_complete_plot(tmp_path):
    output = tmp_path / "complete.png"
    PLOT["plot"](fixture_data(), output)
    assert output.read_bytes().startswith(b"\x89PNG\r\n\x1a\n")


def test_withheld_has_no_plot(tmp_path):
    output = tmp_path / "missing.png"
    with pytest.raises(ValueError, match="withheld"):
        PLOT["plot"](fixture_data(True), output)
    assert not output.exists()
