from pathlib import Path
import sys


sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "reports/ALGO08/v3"))

from named_shared_cpu import Repeats, family


class Object:
    pass


def test_first_same_stage_and_cross_stage_repeats_are_disjoint():
    repeats = Repeats()
    obj = Object()
    key = (repeats.token(obj), b"exact arguments")
    repeats.record("projection", "rank", key, 12)
    repeats.record("projection", "rank", key, 10)
    repeats.record("projection", "confidence", key, 8)
    by_stage = {item["stage"]: item for item in repeats.report()}
    assert by_stage["rank"]["first"] == by_stage["rank"]["repeats"] == 1
    assert by_stage["rank"]["first_cpu_ns"] == 12
    assert by_stage["rank"]["repeat_cpu_ns"] == 10
    assert by_stage["confidence"]["cross_stage_repeat_cpu_ns"] == 8


def test_distinct_owners_and_exhausted_capacity_do_not_report_hits():
    first, copied = Object(), Object()
    repeats = Repeats(key_bytes=0)
    assert repeats.token(first) != repeats.token(copied)
    repeats.record("projection", "rank", None, 4)
    repeats.record("projection", "rank", (repeats.token(first),), 7)
    repeats.record("projection", "rank", (repeats.token(first),), 3)
    entry, = repeats.report()
    assert entry["unknown"] == 3 and entry["capacity_excluded"] == 2
    assert entry["unknown_cpu_ns"] == entry["inclusive_cpu_ns"] == 14
    assert "repeats" not in entry


def test_exclusive_category_matches_installed_operator_and_not_unrelated_names():
    assert family(("/some/orbit_projector.py", 99, "evaluate")) == "native_stencil_projection"
    assert family(("/some/continuous_curve_fit.py", 14, "paired_phase_states")) == "orbit_interpolation"
    assert family(("/some/implementation.py", 14, "paired_phase_states")) == "other"
    assert family(("~", 0, "<built-in method numpy.asarray>")) == "array_cast_or_copy"
    assert family(("~", 0, "<method 'reduce' of 'numpy.ufunc' objects>")) == "numpy_reduction"
