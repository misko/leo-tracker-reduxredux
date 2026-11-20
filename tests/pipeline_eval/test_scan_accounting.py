import pytest

from tools.pipeline_eval.qualification import scan_accounting_results as results
from tools.pipeline_eval.qualification import scan_accounting_trial as trial
from tools.pipeline_eval.qualification.scan_accounting_worker import public_collection


def test_public_payload_round_trip_keeps_key_order_and_terminal_facts():
    chunk = {"start": 16, "end": 32}
    visits = [{"status": "processed", "probes": [{"gate": False}]}]
    shards = {(3, 16): (chunk, visits), (0, 0): ({"start": 0, "end": 16}, [])}
    terminal = {"1": {"exit_code": 0, "terminal": {"count": 1}, "output_sha256": "abc"}}
    encoded = public_collection(shards, terminal, 9.01)
    assert list(trial.restore_shards(encoded)) == list(shards)
    assert trial.restore_shards(encoded) == shards
    assert encoded["workers"] == terminal
    assert encoded["raw_wall_s"] == 9.01
    encoded["shards"].append(encoded["shards"][0])
    with pytest.raises(ValueError, match="duplicate chunk"):
        trial.restore_shards(encoded)


def test_scientific_equality_can_ignore_only_execution_identity():
    original = dict(
        source=dict(probes=[{"gate": False}], analysis_manifest_sha256="before"),
        provenance=dict(scope="one", detector_sha256="x", run_id="y", invalid_capture=0),
        delivery_clocks=[123],
    )
    same = dict(
        original,
        source=dict(original["source"], analysis_manifest_sha256="after"),
        provenance=dict(original["provenance"], scope="two", detector_sha256="a", run_id="b"),
    )
    assert trial.scientific(original) == trial.scientific(same)
    same["source"]["probes"] = [{"gate": True}]
    assert trial.scientific(original) != trial.scientific(same)


def test_pairing_counts_each_cpu_observation_once_and_rejects_wrong_order():
    plan = dict(cpu=13, pairs=[["baseline", "candidate"], ["candidate", "baseline"]])
    receipts = {
        "recording": [
            dict(
                pair=i,
                order=j,
                mode=mode,
                cpu=13,
                collection_sha256="same",
                cpu_ns=500 if mode == "baseline" else 200,
                wall_ns=600 if mode == "baseline" else 230,
            )
            for i, modes in enumerate(plan["pairs"])
            for j, mode in enumerate(modes)
        ]
    }
    rows, stats = results.samples(receipts, plan)
    assert [row["order"] for row in rows] == ["baseline/candidate", "candidate/baseline"]
    assert stats["recording"]["cpu_saved_ms"]["n"] == 2
    assert stats["recording"]["cpu_saved_ms"]["p50"] == 300 / 1e6
    receipts["recording"][2]["order"] = 2
    with pytest.raises(ValueError, match="subprocess receipt"):
        results.samples(receipts, plan)
