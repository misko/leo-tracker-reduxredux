import json
import sys

import pytest

import leo.cli.adaptive_hop_analysis as cli
import leo.scanner.adaptive_hop_analysis as detector
from leo.storage.persistent_hop_analysis import PersistentHopAnalysisStore
from leo.storage.persistent_hop_analysis_v2 import PersistentHopAnalysisStoreV2
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell
from tests.storage.test_adaptive_hop_history import publish_capture


@pytest.mark.parametrize("rate", [2_500_000, 5_000_000])
@pytest.mark.parametrize("mode", ["adaptive", "shadow"])
def test_cli_persists_resumes_and_never_calls_radio(monkeypatch, tmp_path, capsys, rate, mode):
    capture = publish_capture(tmp_path, rate=rate, mode=mode, count=3)
    priorities = []
    monkeypatch.setattr(cli.os, "nice", priorities.append)
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "leo-adaptive-hop-analysis",
            "--bulk-root",
            str(tmp_path),
            "--session-id",
            capture.session_id,
            "--maximum-visits",
            "1",
        ],
    )
    cli.main()
    first = json.loads(capsys.readouterr().out)
    assert first["state"] == "partial" and first["newly_analyzed_visits"] == 1
    cli.main()
    second = json.loads(capsys.readouterr().out)
    assert second["state"] == "metrics_complete" and second["newly_analyzed_visits"] == 1
    cli.main()
    third = json.loads(capsys.readouterr().out)
    assert third["newly_analyzed_visits"] == 0 and priorities == [10, 10, 10]


@pytest.mark.parametrize("store_type", [PersistentHopAnalysisStore, PersistentHopAnalysisStoreV2])
def test_cli_obeys_existing_fixed_worker_lock_without_analyzing(
    monkeypatch, tmp_path, capsys, store_type
):
    coordinator = store_type(tmp_path)
    monkeypatch.setattr(cli.os, "nice", lambda _: None)
    monkeypatch.setattr(
        sys, "argv", ["analysis", "--bulk-root", str(tmp_path), "--session-id", "absent"]
    )
    with coordinator.worker_lock() as acquired:
        assert acquired
        cli.main()
    assert json.loads(capsys.readouterr().out)["state"] == "busy"
    assert not (tmp_path / "scanner-adaptive-analysis").exists()


@pytest.mark.parametrize(
    "option,value",
    [
        ("--maximum-visits", "0"),
        ("--maximum-seconds", "nan"),
        ("--maximum-seconds", "1801"),
        ("--probe-stride-ms", "9"),
        ("--session-id", "../unsafe"),
    ],
)
def test_cli_invalid_arguments_create_nothing(monkeypatch, tmp_path, option, value):
    args = ["analysis", "--bulk-root", str(tmp_path), "--session-id", "safe", option, value]
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2 and list(tmp_path.iterdir()) == []


def test_cli_failure_is_nonzero_and_does_not_claim_completion(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(cli.os, "nice", lambda _: None)
    monkeypatch.setattr(
        sys, "argv", ["analysis", "--bulk-root", str(tmp_path), "--session-id", "missing"]
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == "" and json.loads(output.err)["state"] == "failed"
