import importlib.util
import sys
from pathlib import Path


def _subject():
    path = Path(__file__).parents[2] / "tools/research/audit_recent_paired_source_authority.py"
    spec = importlib.util.spec_from_file_location("audit_recent_paired_source_authority", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _d(subject, group, visit, receiver, cfo, epoch, margin=1.0):
    return subject.Detection(group, visit, receiver, 2, "lower", float(visit), cfo, epoch, margin)


def test_timing_and_cfo_match_is_mutually_unique_and_shift_control_breaks_it():
    subject = _subject()
    rows = []
    for visit in range(30):
        rows.extend(
            (
                _d(subject, f"left-{visit}", visit, 0, 1000 + visit, 50.0 + 20 * visit),
                _d(subject, f"right-{visit}", visit, 1, 7000 + visit, 50.2 + 20 * visit),
            )
        )
    edges = subject._timing_edges(rows, 2_500_000)
    model = subject._fit_offset([edge for edge in edges if edge[0].visit % 2 == 0])
    held = subject._matches([edge for edge in edges if edge[0].visit % 2], model)
    shifted = subject._matches(
        subject._timing_edges(rows, 2_500_000, visit_shift=17), model
    )

    assert len(held) == 15
    assert shifted == []


def test_ambiguous_cfo_edges_are_not_forced():
    subject = _subject()
    left = _d(subject, "left", 1, 0, 1000, 10)
    right_a = _d(subject, "right-a", 1, 1, 7000, 10)
    right_b = _d(subject, "right-b", 1, 1, 7050, 20)
    matches = subject._matches(
        [(left, right_a, 6000.0, 0.0), (left, right_b, 6050.0, 0.0)],
        (subject.np.asarray([6000.0, 0.0]), 0.0),
    )
    assert matches == []
