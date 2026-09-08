import pytest

from tools.evaluate_presence_dwell import summarize


def test_dwell_summary_uses_measured_prefixes_and_preserves_misses():
    row = {
        "rate_hz": 5000000,
        "bins": 4096,
        "mode": "seeded",
        "reference_positive": [True, False, True, False, False, False],
        "result": {
            "rank": {"order": [1, 2, 0, 3, 4, 5]},
            "prefix_cpu_ms": [1.5, 2.5, 3.5, 4.5, 5.5, 6.5],
        },
        "observations": [
            {"detected": True, "associated": False},
            {"detected": True, "associated": True},
            *[{"detected": False, "associated": False} for _ in range(4)],
        ],
    }
    result = summarize([row])["5000000:4096:seeded"]
    assert result["reference_positive_visits"] == 1
    assert result["policies"]["1"]["reference_selected"] == 0
    assert result["policies"]["1"]["associated"] == 0
    assert result["policies"]["1"]["flagged_without_association"] == 1
    assert result["policies"]["2"]["associated"] == 1
    assert result["policies"]["2"]["desktop_prefix_cpu_p50_p99_max_ms"] == pytest.approx([2.5] * 3)
