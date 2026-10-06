from leo.cli.adaptive_hop_analysis import _run_t1_at_stage


def test_no_association_before_metrics_finish():
    assert _run_t1_at_stage(metrics_complete=False)["state"] == "pending"


def test_completed_metrics_invoke_standard_pipeline_stage(monkeypatch):
    import leo.cli.t1_at as cli

    calls = []

    def run(**kwargs):
        calls.append(kwargs)
        return dict(state="complete", baseline_id="t1_at_v1")

    monkeypatch.setattr(cli, "run", run)
    assert _run_t1_at_stage(metrics_complete=True, session_id="scan-test")["state"] == "complete"
    assert calls == [dict(session_id="scan-test")]


def test_timeout_is_partial_not_complete(monkeypatch):
    import leo.cli.t1_at as cli

    def run(**kwargs):
        raise TimeoutError()

    monkeypatch.setattr(cli, "run", run)
    assert _run_t1_at_stage(metrics_complete=True)["state"] == "partial"


def test_adaptive_cli_routes_discovery_after_metrics(monkeypatch, tmp_path, capsys):
    import json
    import sys

    import leo.cli.adaptive_hop_analysis as cli
    import leo.scanner.adaptive_hop_analysis as detector
    from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell
    from tests.storage.test_adaptive_hop_history import publish_capture

    capture = publish_capture(tmp_path, count=2)
    calls = []

    def stage(**kwargs):
        calls.append(kwargs)
        return dict(state="complete", baseline_id="t1_at_v1")

    monkeypatch.setattr(cli, "_run_t1_at_stage", stage)
    monkeypatch.setattr(cli.os, "nice", lambda _: None)
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    path = tmp_path / "discovery.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "analysis",
            "--bulk-root",
            str(tmp_path),
            "--session-id",
            capture.session_id,
            "--probe-stride-ms",
            "10",
            "--metrics-only",
            "--t1-at-discovery-input",
            str(path),
            "--t1-at-maximum-seconds",
            "300",
        ],
    )
    cli.main()
    result = json.loads(capsys.readouterr().out)
    assert result["t1_at"]["state"] == "complete"
    assert len(calls) == 1 and calls[0]["metrics_complete"] is True
    assert calls[0]["probe_stride_ms"] == 10 and calls[0]["discovery_input"] == path
    assert calls[0]["maximum_seconds"] == 300
