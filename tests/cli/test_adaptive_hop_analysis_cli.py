import json
import sys
from types import SimpleNamespace

import pytest

import leo.cli.adaptive_hop_analysis as cli
import leo.scanner.adaptive_hop_analysis as detector
from leo.storage.persistent_hop_analysis import PersistentHopAnalysisStore
from leo.storage.persistent_hop_analysis_v2 import PersistentHopAnalysisStoreV2
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell
from tests.storage.test_adaptive_hop_history import publish_capture


def test_pending_selection_resumes_then_orders_oldest_without_reading_iq():
    states = {
        "new": "not_started",
        "partial": "partial",
        "metrics": "metrics_complete",
        "done": "figures_ready",
    }
    captures = SimpleNamespace(
        iter_sessions=lambda: (
            SimpleNamespace(session_id=name, manifest=SimpleNamespace(created_utc_ns=i))
            for i, name in enumerate(states)
        )
    )
    presentation = SimpleNamespace(status=lambda name, **kw: SimpleNamespace(state=states[name]))
    assert cli.next_pending(captures, presentation, probe_stride_ms=10) == "metrics"
    states["metrics"] = "figures_ready"
    assert cli.next_pending(captures, presentation, probe_stride_ms=10) == "partial"
    states["partial"] = "figures_ready"
    assert cli.next_pending(captures, presentation, probe_stride_ms=10) == "new"
    states["new"] = "figures_ready"
    assert cli.next_pending(captures, presentation, probe_stride_ms=10) is None


@pytest.mark.parametrize("stride", [10, 120])
def test_pending_cli_publishes_figures_then_is_idle(monkeypatch, tmp_path, capsys, stride):
    capture = publish_capture(tmp_path, count=3)
    monkeypatch.setattr(cli.os, "nice", lambda _: None)
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analysis",
            "--bulk-root",
            str(tmp_path),
            "--pending",
            "--maximum-workers",
            "2",
            "--probe-stride-ms",
            str(stride),
        ],
    )
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["session_id"] == capture.session_id and result["overview_state"] == "ready"
    monkeypatch.setattr(
        detector, "analyze_glrt64_dwell", lambda *a, **k: pytest.fail("reanalyzed ready capture")
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)["state"] == "idle"


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
    assert first["overview_state"] == "not_ready"
    cli.main()
    second = json.loads(capsys.readouterr().out)
    assert second["state"] == "metrics_complete" and second["newly_analyzed_visits"] == 1
    assert second["overview_state"] == "ready"
    cli.main()
    third = json.loads(capsys.readouterr().out)
    assert third["newly_analyzed_visits"] == 0 and priorities == [10, 10, 10]
    assert third["overview_state"] == "ready"
    assert third["overview_metrics_manifest_sha256"] == second["overview_metrics_manifest_sha256"]


def test_cli_metrics_only_then_failed_render_can_resume_without_reanalyzing(
    monkeypatch, tmp_path, capsys
):
    from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore

    capture = publish_capture(tmp_path, count=2)
    monkeypatch.setattr(cli.os, "nice", lambda _: None)
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    args = ["analysis", "--bulk-root", str(tmp_path), "--session-id", capture.session_id]
    monkeypatch.setattr(sys, "argv", [*args, "--metrics-only"])
    cli.main()
    first = json.loads(capsys.readouterr().out)
    assert first["state"] == "metrics_complete" and first["overview_state"] == "not_ready"
    renderer = cli.render_adaptive_hop_overview

    def broken(*args):
        raise RuntimeError("injected renderer failure")

    monkeypatch.setattr(detector, "analyze_glrt64_dwell", lambda *a, **k: pytest.fail("reanalyzed"))
    monkeypatch.setattr(cli, "render_adaptive_hop_overview", broken)
    monkeypatch.setattr(sys, "argv", args)
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 1
    assert json.loads(capsys.readouterr().err)["error_type"] == "RuntimeError"
    assert AdaptiveHopAnalysisPresentationStore(tmp_path).status(capture.session_id).state == (
        "metrics_complete"
    )
    monkeypatch.setattr(cli, "render_adaptive_hop_overview", renderer)
    cli.main()
    final = json.loads(capsys.readouterr().out)
    assert final["overview_state"] == "ready" and final["newly_analyzed_visits"] == 0


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
        ("--maximum-workers", "3"),
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
