import importlib.util
from pathlib import Path


PATH = Path(__file__).with_name("run.py")
SPEC = importlib.util.spec_from_file_location("same_source_cfo_audit", PATH)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


def track(start, end, visits, *, channel=1):
    return {
        "start_s": start,
        "end_s": end,
        "training_visits": visits,
        "channel": channel,
    }


def test_alias_wrapped_difference_uses_native_glrt_period():
    period = audit.NATIVE_ALIAS_PERIOD_HZ
    assert abs(audit.alias_wrapped_difference_hz(period - 3, 0) + 3) < 1e-9
    assert abs(audit.alias_wrapped_difference_hz(0, period - 3) - 3) < 1e-9


def test_support_classes_distinguish_duplicates_overlap_and_disjoint():
    shared = audit.classify_support(track(0, 4, [1, 2]), track(1, 5, [2, 3]))
    overlap = audit.classify_support(track(0, 4, [1, 2]), track(3, 5, [3, 4]))
    disjoint = audit.classify_support(track(0, 2, [1]), track(5, 7, [3]))
    assert shared["support"] == "shared_visit"
    assert shared["shared_training_visits"] == 1
    assert overlap["support"] == "interval_overlap_no_shared_visit"
    assert overlap["overlap_s"] == 1
    assert disjoint["support"] == "disjoint"
    assert disjoint["gap_s"] == 3


def test_control_matching_requires_support_class_and_is_deterministic():
    target = {"support": "disjoint", "gap_s": 3, "overlap_s": 0, "combined_span_s": 8}
    controls = [
        {"support": "shared_visit", "gap_s": 0, "overlap_s": 1,
         "combined_span_s": 8, "track_a": "a", "track_b": "b"},
        {"support": "disjoint", "gap_s": 4, "overlap_s": 0,
         "combined_span_s": 9, "track_a": "z", "track_b": "z"},
        {"support": "disjoint", "gap_s": 4, "overlap_s": 0,
         "combined_span_s": 9, "track_a": "c", "track_b": "d"},
    ]
    assert audit.match_control(target, controls)["track_a"] == "c"
