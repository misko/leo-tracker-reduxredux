import json
from collections import Counter

import pytest

from tools.pipeline_eval.qualification import upper_primary as trial


def pair(signature):
    return tuple(
        {"candidates": [{"passed_fractional_margin_gate": passing}]} for passing in signature
    )


def test_control_selection_covers_no_retry_and_both_retry_receivers():
    signatures = ((False, False), (True, True), (True, False), (False, True))
    probes = {i: pair(signatures[i % len(signatures)]) for i in range(100)}
    retry = {i for i in probes if i % 4 >= 2}
    actual = trial.choose_controls(probes, retry)
    assert actual == trial.choose_controls(dict(reversed(list(probes.items()))), retry)
    assert len(set(actual)) == 15
    assert Counter((tuple(map(trial.assay.positive, probes[i])), i in retry) for i in actual) == {
        ((False, False), False): 7,
        ((True, True), False): 4,
        ((True, False), True): 2,
        ((False, True), True): 2,
    }
    with pytest.raises(ValueError, match="preflight strata"):
        trial.choose_controls(probes, {i for i in retry if i % 4 == 2})


def test_coarse_trace_rejects_changed_visit_and_work(tmp_path, monkeypatch):
    lock = dict(workers=[(12, 2, [(1, 30, 32, 100)])])
    grid = {130: (2, 0), 131: (2, 2)}
    log = tmp_path / "cpu-12.log"
    trace = [
        dict(
            ordinal=i,
            calls=p + w,
            inverse_ffts=p * 104_286 + w * 191_037,
            input_ffts=(p + w) * 427,
            coarse_cpu_ns=40,
            spans=(p + w) * 21 * 13_333,
        )
        for i, (p, w) in enumerate(grid.values())
    ]
    log.write_text("".join(trial.lower.TRACE + json.dumps(r) + "\n" for r in trace))
    monkeypatch.setattr(trial, "parent_path", lambda _lock, _name: log)
    csv_rows = [dict(r, cpu=12, visit=v) for v, r in zip(grid, trace, strict=True)]

    trial.verify_traces(lock, csv_rows, grid)
    csv_rows[1]["visit"] = 132
    with pytest.raises(ValueError, match="measured trace"):
        trial.verify_traces(lock, csv_rows, grid)
    csv_rows[1].update(visit=131, inverse_ffts=417_144)
    with pytest.raises(ValueError, match="measured trace"):
        trial.verify_traces(lock, csv_rows, grid)
