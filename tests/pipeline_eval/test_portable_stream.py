from copy import deepcopy
from pathlib import Path

import pytest

from tools.pipeline_eval import whole_iq
from tools.pipeline_eval.qualification import portable_stream_results as measured
from tools.pipeline_eval.qualification import portable_stream_trial as trial


def native_packet():
    packet = {
        "source": {
            "input_manifest_sha256": "sha256:" + "3" * 64,
            "probes": [{"receiver_id": 0, "candidates": [{"fractional_margin": 0.5}]}],
        },
        "provenance": {"detector_sha256": "sha256:" + trial.STOCK, "excluded_windows": []},
        "delivery_clocks": [{"monotonic_ns": 4}],
    }
    source, prov = packet["source"], packet["provenance"]
    identity = whole_iq.recording.digest(
        [
            measured.MODE,
            prov["detector_sha256"],
            source["input_manifest_sha256"],
            source["probes"],
            [],
        ]
    )
    source["analysis_manifest_sha256"] = identity
    prov.update(run_id="replay-" + identity[7:39], scope=measured.MODE, detector_mode=measured.MODE)
    return packet


def test_only_policy_identity_may_differ_from_direct_native():
    actual = native_packet()
    historical = deepcopy(actual)
    historical["source"]["analysis_manifest_sha256"] = "different"
    historical["provenance"].update(run_id="old", scope="old", detector_mode="old")
    rows = [dict(visit=0, rf_center_hz=12_000_000_000, primary_receiver=0, partner_required=True)]
    measured.verify_parity(actual, historical, historical, rows, rows)
    with pytest.raises(ValueError, match="strict gate"):
        measured.verify_parity(actual, historical, historical, rows, [])
    historical["delivery_clocks"][0]["monotonic_ns"] += 1
    with pytest.raises(ValueError, match="delivery"):
        measured.verify_parity(actual, historical, historical, rows, rows)


def test_independent_policy_identity_binds_observed_candidate_fields():
    document = native_packet()
    measured.independent_identity(document)
    document["source"]["probes"][0]["candidates"][0]["fractional_margin"] = 0.501
    with pytest.raises(ValueError, match="observed replay"):
        measured.independent_identity(document)


def test_both_worker_counts_request_same_raw_port_and_core_pair(tmp_path):
    paths = tmp_path / "run", tmp_path / "relocated"
    for count in (1, 2):
        command = trial.command_for(*paths, (6, 7), count, "fixture.service", (Path("/build"),))
        assert command[command.index("taskset") + 2] == "6,7"
        assert command[command.index("--cpus") + 1 : command.index("--cpus") + 3] == ["6", "7"]
        assert command[command.index("--visit-workers") + 1] == str(count)
        assert command[command.index("--detector") + 1] == "partner-on-hit"
        assert "--unshare-net" in command
        assert "--property=MemoryMax=536870912" in command
        assert "--property=MemorySwapMax=0" in command
        assert str(paths[0] / "input.json") in command
        assert str(paths[1] / "receive.py") in command


def test_capture_records_merge_even_and_odd_physical_logs(tmp_path):
    template = dict(
        kind="visit",
        visit=1,
        segment=1,
        sequence=0,
        status="processed",
        iq_sha256="digest",
        delivery_clock={"monotonic_ns": 4},
        sample_start=200_000,
        sample_end=400_000,
        reason=None,
    )
    for lane, visits in ((0, [0, 2]), (1, [1])):
        payload = b"".join(measured.encoded(dict(template, visit=v)) + b"\n" for v in visits)
        (tmp_path / f"lane-{lane}.jsonl").write_bytes(payload)
    assert [r["visit"] for r in measured.capture_records(tmp_path)] == [0, 1, 2]


def test_complete_delivery_checks_excluded_visit_and_ordered_iq_authority():
    basic = dict(sample_start=0, sample_end=200_000, reason=None)
    physical = [
        dict(
            basic,
            visit=0,
            segment=0,
            sequence=0,
            status="processed",
            iq_sha256="a",
            delivery_clock={"monotonic_ns": 20},
        ),
        dict(
            basic,
            visit=1,
            segment=1,
            sequence=0,
            status="invalid_capture",
            iq_sha256="b",
            delivery_clock={"monotonic_ns": 30},
        ),
    ]
    exclusion = {
        k: physical[1][k] for k in ("visit", "reason", "iq_sha256", "sample_start", "sample_end")
    }
    native = dict(
        source=dict(
            input_manifest_sha256="manifest",
            raw_recording_authority_digest=(whole_iq.recording.digest(["manifest", ["a", "b"]])),
        ),
        provenance=dict(excluded_windows=[exclusion]),
        delivery_clocks=[row["delivery_clock"] for row in physical],
    )
    measured.check_recording(physical, native, {"invalid_visits": 1}, [1, 1])
    physical[1]["reason"] = "changed"
    with pytest.raises(ValueError, match="exclusion fields"):
        measured.check_recording(physical, native, {"invalid_visits": 1}, [1, 1])
    physical[1]["reason"] = None
    physical[0]["iq_sha256"] = "different"
    with pytest.raises(ValueError, match="does not match independent stock"):
        measured.check_recording(physical, native, {"invalid_visits": 1}, [1, 1])
