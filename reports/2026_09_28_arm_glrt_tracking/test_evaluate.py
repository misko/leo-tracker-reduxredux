import importlib.util
from pathlib import Path

S = importlib.util.spec_from_file_location("e", Path(__file__).with_name("evaluate.py"))
e = importlib.util.module_from_spec(S)
S.loader.exec_module(e)


def b(epoch=4, cfo=1, margin=0.1):
    return {"epoch_sample": epoch, "tracking_cfo_hz": cfo, "margin": margin}


def n(epoch=4, cfo=1, margin=0.1):
    return {"epoch": epoch, "tracking_cfo_hz": cfo, "margin": margin}


def test_one_to_one_prevents_many_to_one():
    r = [{"receiver_id": 0, "probe_index": 0, "candidates": [b(), b(cfo=2)]}]
    x = [
        {
            "receiver_id": 0,
            "probe_index": 0,
            "candidates": [n()],
            "candidate_eval_attempts": 1,
            "timings_ms": {"total_cpu": 1},
        }
    ]
    assert e.score(x, r)["counts"]["matched_positive"] == 1


def test_matching_reassigns_an_earlier_pair_to_recover_both():
    # First reference can use either native candidate; the second can use only
    # the first. Greedy matching would undercount recovery.
    reference = [b(epoch=2), b(epoch=0)]
    native = [n(epoch=1), n(epoch=4)]
    assert len(e.match(reference, native)) == 2


def test_missing_window_stays_denominator_and_new_positive_counts_added():
    r = [
        {"receiver_id": 0, "probe_index": 0, "candidates": [b()]},
        {"receiver_id": 1, "probe_index": 0, "candidates": [b()]},
    ]
    x = [
        {
            "receiver_id": 0,
            "probe_index": 0,
            "candidates": [n(), n(epoch=99)],
            "candidate_eval_attempts": 2,
            "timings_ms": {"total_cpu": 1},
        }
    ]
    q = e.score(x, r)
    assert (
        q["counts"]["baseline_positive"] == 2
        and q["counts"]["missed_positive"] == 1
        and q["counts"]["added_positive"] == 1
    )
