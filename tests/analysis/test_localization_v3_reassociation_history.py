from copy import deepcopy
from hashlib import sha256
from types import SimpleNamespace

import numpy as np
import pytest

from leo.analysis.localization_v3 import reassociation_history as history
from leo.sky.propagation import parse_element_sets
from tests.operations.test_causal_tle_catalogue import at_day


def context(day=232, old_day=231):
    text = at_day(old_day)
    element = parse_element_sets(at_day(day))
    epoch = element.element_epoch_utc_ns()[0]
    old_epoch = parse_element_sets(text).element_epoch_utc_ns()[0]
    cutoff = epoch + 10**9
    lines = [line for line in at_day(day).splitlines() if line.startswith(("1 ", "2 "))]
    scan = SimpleNamespace(
        previous_tle=text,
        previous_tle_sha256=sha256(text.encode()).hexdigest(),
        previous_sources={"44714": dict(epoch_utc_ns=old_epoch, collected_utc_ns=cutoff - 1)},
        elements={"44714": dict(lines=lines, provenance=dict(collected_utc_ns=cutoff - 1))},
        norads=np.array([44714]),
        previous_shape_cache={"original": True},
        diagnostic_phase_width_cache={"original": True},
        causal_uncertainty_modes={"old": True},
        reference_motion_derivatives={"old": True},
        mean_motion_derivatives={"old": True},
    )
    problem = SimpleNamespace(labels=[0], reference=np.array([3.0]))
    return dict(
        scan=scan,
        problems={arm: (problem, np.array([1.0, 2.0])) for arm in ("c0", "fitted_c")},
        families=[],
        means=np.array([7.0]),
        model=dict(shrinkage=0.5),
    ), dict(cutoff_utc_ns=cutoff)


def fail_collect(_):
    pytest.fail("Unnecessary history collection")


def test_existing_valid_history_is_not_swapped():
    d, receipt = context()
    out, info = history.complete_history(d, [44714, 44714], {}, receipt, fail_collect)
    assert out is d
    assert info == dict(requested=[], available=[], missing=[], changed=False)


@pytest.mark.parametrize("fault", ["bytes", "future_nominal", "unknown", "no_sources"])
def test_invalid_input_is_rejected_before_collection(fault):
    d, receipt = context()
    ids = [44714]
    if fault == "bytes":
        d["scan"].previous_tle += " "
    elif fault == "future_nominal":
        d["scan"].elements["44714"]["provenance"]["collected_utc_ns"] = receipt["cutoff_utc_ns"] + 1
    elif fault == "no_sources":
        d["scan"].previous_sources = None
    else:
        ids = [99999]
    with pytest.raises(ValueError):
        history.complete_history(d, ids, {}, receipt, fail_collect)


def test_missing_export_preserves_incumbent():
    d, receipt = context(old_day=232)
    calls = []

    def collect(request):
        calls.append(request)
        return dict(chosen={})

    out, info = history.complete_history(d, [44714], {}, receipt, collect)
    assert out is d and not info["changed"]
    assert info["missing"] == [44714] and info["requested"] == ["44714"]
    assert list(calls[0]["latest"]) == ["44714"]


def test_completion_isolated_and_rebuilds_both_arms(monkeypatch):
    d, receipt = context(old_day=232)
    original_sources = deepcopy(d["scan"].previous_sources)
    lines = [line for line in at_day(231).splitlines() if line.startswith(("1 ", "2 "))]
    row = dict(
        lines=lines,
        epoch_utc_ns=parse_element_sets(at_day(231)).element_epoch_utc_ns()[0],
        collected_utc_ns=receipt["cutoff_utc_ns"] - 10,
        digest="test",
    )
    monkeypatch.setattr(history, "phase_widths", lambda scan, labels: (None, []))
    monkeypatch.setattr(history, "forecast_phase_mean", lambda receipts, shrinkage: np.array([2.0]))
    rebuilt = []

    def build(ctx, arm, reference):
        assert ctx["scan"] is not d["scan"]
        assert not hasattr(ctx["scan"], "previous_shape_cache")
        rebuilt.append(arm)
        return SimpleNamespace(reference=reference.copy()), ctx

    monkeypatch.setattr(history, "build", build)
    out, info = history.complete_history(
        d, [44714], {}, receipt, lambda _: dict(chosen={"44714": row})
    )
    assert rebuilt == ["c0", "fitted_c"] and info["changed"]
    assert out["means"].tolist() == [2.0] and d["means"].tolist() == [7.0]
    assert d["scan"].previous_sources == original_sources
    assert d["scan"].previous_shape_cache == {"original": True}
    assert out["scan"].previous_tle == "\n".join(lines) + "\n"
    assert info["new_sha256"] == sha256(out["scan"].previous_tle.encode()).hexdigest()
    row["digest"] = "mutated"
    assert out["scan"].previous_sources["44714"]["digest"] == "test"


@pytest.mark.parametrize("fault", ["future", "old_collection", "same_epoch", "unrequested"])
def test_bad_exports_cannot_change_priors(fault):
    d, receipt = context(old_day=232)
    cutoff = receipt["cutoff_utc_ns"]
    row = dict(collected_utc_ns=cutoff, epoch_utc_ns=cutoff - 2 * 10**9)
    number = "44714"
    if fault == "future":
        row["collected_utc_ns"] += 1
    elif fault == "old_collection":
        row["collected_utc_ns"] -= 72 * 3600 * 10**9 + 1
    elif fault == "same_epoch":
        row["epoch_utc_ns"] = cutoff - 10**9
    else:
        number = "99999"
    with pytest.raises(ValueError, match="Invalid causal history export"):
        history.complete_history(d, [44714], {}, receipt, lambda _: dict(chosen={number: row}))


def test_select_history_preserves_first_equal_epoch_and_rejects_wrong_cutoff():
    rows = [
        dict(epoch_utc_ns=20, collected_utc_ns=30, digest="first"),
        dict(epoch_utc_ns=20, collected_utc_ns=31, digest="second"),
        dict(epoch_utc_ns=19, collected_utc_ns=29),
    ]
    bank = dict(cutoff_utc_ns=3 * 10**9, versions={"1": rows}, snapshot_count=3)
    request = dict(cutoff=3 * 10**9, latest={"1": 2 * 10**9, "2": 2 * 10**9})
    result = history.select_history(bank, request)
    assert result["chosen"]["1"]["digest"] == "first" and len(result["chosen"]) == 1
    result["chosen"]["1"]["digest"] = "changed"
    assert rows[0]["digest"] == "first"
    with pytest.raises(ValueError, match="cutoff mismatch"):
        history.select_history(bank, dict(request, cutoff=0))
