import importlib.util
from pathlib import Path

SPEC = importlib.util.spec_from_file_location("cohort", Path(__file__).with_name("cohort.py"))
cohort = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cohort)


def test_selection_has_16_per_rate():
    rows = []
    for rate in cohort.RATES:
        for edge in ("lower", "upper"):
            rows += [{"rate_hz": rate, "target": {"edge": edge}, "ordinal": i} for i in range(9)]
    got = cohort.select(rows)
    assert len(got) == 64
    assert all(sum(r["rate_hz"] == rate for r in got) == 16 for rate in cohort.RATES)


def test_all_sealed_selection_preserves_every_input_row():
    rows = [{"ordinal": index} for index in range(704)]
    assert cohort.select(rows, all_sealed=True) == rows


def test_compare_counts_missing_and_duplicate_windows_and_prevents_many_to_one():
    ref = {
        (0, 0): {
            "candidates": [
                {
                    "epoch_sample": 1,
                    "tracking_cfo_hz": 0,
                    "acquired_cfo_hz": 0,
                    "exact_score": 1,
                    "control_score": 0,
                    "margin": 0.5,
                },
                {
                    "epoch_sample": 1,
                    "tracking_cfo_hz": 1,
                    "acquired_cfo_hz": 1,
                    "exact_score": 1,
                    "control_score": 0,
                    "margin": 0.5,
                },
            ]
        },
        (1, 0): {"candidates": []},
    }
    native = [
        {
            "receiver_id": 0,
            "probe_index": 0,
            "candidates": [
                {
                    "epoch": 1,
                    "tracking_cfo_hz": 0,
                    "acquired_cfo_hz": 0,
                    "exact_score": 1,
                    "control_score": 0,
                    "margin": 0.5,
                }
            ],
        },
        {"receiver_id": 0, "probe_index": 0, "candidates": []},
    ]
    got = cohort.compare(native, ref)
    assert got["reference_positive"] == 2 and got["matched_positive"] == 1
    assert {x["error"] for x in got["errors"]} >= {
        "candidate_count",
        "duplicate_native_window",
        "missing_native_window",
    }
