import json
import runpy
import sys
from copy import deepcopy
from pathlib import Path

import pytest

from tools.pipeline_eval.qualification import portable_conditional_build as package
from tools.pipeline_eval.qualification import portable_conditional_results as results
from tools.pipeline_eval.variants import second_on_miss


def test_new_bundle_preserves_public_stock_default_and_binary_inventory(tmp_path, monkeypatch):
    root = package.build(tmp_path / "different install")
    old, _ = results.old_package(package.BASE_TAR)
    new = json.loads((root / "files.json").read_bytes())["files"]
    assert {k: v for k, v in old.items() if ".so" in Path(k).name} == {
        k: v for k, v in new.items() if ".so" in Path(k).name
    }
    assert {k for k, v in old.items() if new[k] != v} == {"receive.py", "capture/native_bridge.py"}
    entry = runpy.run_path(str(root / "receive.py"))
    assert entry["verify_package"]()["files"] == new
    request = tmp_path / "request.json"
    request.write_text("{}")
    called = []
    namespace = entry["main"].__globals__
    monkeypatch.setitem(namespace, "replay", lambda *args: called.append(args))
    args = [str(root / "receive.py"), str(request), "--out", str(tmp_path / "positions")]
    monkeypatch.setattr(sys, "argv", args)
    entry["main"]()
    monkeypatch.setattr(sys, "argv", [*args, "--detector", "second-on-miss"])
    entry["main"]()
    assert [value[-1] for value in called] == ["stock", "second-on-miss"]
    assert called[0][:-1] == called[1][:-1]


def test_parity_keeps_invalid_slots_and_rejects_changed_physical_partner():
    stock = {
        "delivery_clocks": [0, 1, 2, 3],
        "source": {"input_manifest_sha256": "fixture", "probes": []},
        "provenance": {
            "excluded_windows": [{"visit": 1}],
            "invalid_capture": 1,
            "processed_windows": 3,
            "window_count": 4,
            "detector_sha256": "stock",
        },
    }
    positives = {(0, 0), (2, 0), (3, 0)}
    for visit in (0, 2, 3):
        for lane in (0, 1):
            stock["source"]["probes"].append(
                dict(
                    visit_index=visit,
                    receiver_id=lane,
                    channel=4,
                    edge="lower",
                    candidates=[
                        {
                            "passed_fractional_margin_gate": (visit, lane) in positives,
                        }
                    ],
                )
            )
    rf = {(4, "lower"): 10_930_000_000}
    actual, ledger = second_on_miss.project(stock, rf)
    assert [(r["visit"], r["primary_receiver"], r["partner_required"]) for r in ledger] == [
        (0, 0, False),
        (2, 1, True),
        (3, 0, False),
    ]
    assert results.parity(stock, actual, rf, ledger) == (3, 2)
    corrupted = deepcopy(actual)
    corrupted["source"]["probes"][1]["candidates"] = stock["source"]["probes"][1]["candidates"]
    with pytest.raises(ValueError, match="full-stock projection"):
        results.parity(stock, corrupted, rf, ledger)
    with pytest.raises(ValueError, match="dispatch differ"):
        results.parity(stock, actual, rf, [ledger[0], ledger[2], ledger[1]])
