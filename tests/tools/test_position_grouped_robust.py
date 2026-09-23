import importlib.util
from pathlib import Path


def subject():
    path = Path(__file__).parents[2] / "tools/research/position_grouped_robust.py"
    spec = importlib.util.spec_from_file_location("position_grouped_robust", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_equal_scan_weighting_prevents_track_rich_scan_domination():
    module = subject()
    rows = [{"session_id": "many", "weight_s": 1, "score": {"rms": 0.0}} for _ in range(9)] + [
        {"session_id": "one", "weight_s": 1, "score": {"rms": 100.0}}
    ]
    duration = module.aggregate(rows, "rms", "uncapped", "duration")
    equal_scan = module.aggregate(rows, "rms", "uncapped", "equal_scan")
    assert round(duration, 6) == round(100 / (10**0.5), 6)
    assert round(equal_scan, 6) == round(100 / (2**0.5), 6)


def test_robust_term_is_monotone_and_subquadratic_for_large_residuals():
    module = subject()
    assert module.track_term(10, "pseudo_huber_150hz") < module.track_term(20, "pseudo_huber_150hz")
    assert module.track_term(1000, "pseudo_huber_150hz") < 1000**2
