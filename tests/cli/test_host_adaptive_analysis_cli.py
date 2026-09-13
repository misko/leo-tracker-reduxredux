import json
import sys

import pytest

import leo.cli.adaptive_hop_analysis as cli
import leo.scanner.adaptive_hop_analysis as detector
from leo.scanner.single_rx import SingleRxHopTimingV2
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_presentation import AdaptiveHopAnalysisPresentationStore
from tests.scanner.adaptive_hop_fixtures import timing_fixture
from tests.scanner.host_adaptive_fixtures import host_receipt
from tests.scanner.test_persistent_hop_standard_analysis import _fake_fractional_dwell
from tests.storage.test_host_adaptive_hop_store import block


@pytest.mark.parametrize("receiver", [0, 1])
def test_native_cli_resumes_metrics_then_publishes_bound_figures(
    monkeypatch, tmp_path, capsys, receiver
):
    receipt = host_receipt(receiver=receiver, count=3)
    captures = AdaptiveHopIqStore(tmp_path)
    writer = captures.begin(receipt.session_id, receipt.plan)
    try:
        for i in range(receipt.complete_visit_count):
            writer.append(block(receipt, i))
        writer.finish(receipt, timing=timing_fixture(receipt, SingleRxHopTimingV2))
    finally:
        writer.abort()
        captures.close()
    monkeypatch.setattr(cli.os, "nice", lambda _: None)
    monkeypatch.setattr(detector, "analyze_glrt64_dwell", _fake_fractional_dwell)
    workers = []
    original = cli.HostAdaptiveAnalysisService.analyze_session

    def analyze(self, session_id, **options):
        workers.append(options["maximum_workers"])
        return original(self, session_id, **options)

    monkeypatch.setattr(cli.HostAdaptiveAnalysisService, "analyze_session", analyze)
    args = ["analysis", "--bulk-root", str(tmp_path), "--pending"]
    monkeypatch.setattr(sys, "argv", [*args, "--maximum-visits", "1", "--metrics-only"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["state"] == "partial"
    cli.main()
    metrics = json.loads(capsys.readouterr().out)
    assert metrics["state"] == "metrics_complete" and metrics["overview_state"] == "not_ready"
    assert workers == [4, 4]
    presentation = AdaptiveHopAnalysisPresentationStore(tmp_path)
    status = presentation.status(receipt.session_id)
    assert status.schema_version == 2 and status.configuration.receiver_ids == (receiver,)
    monkeypatch.setattr(
        detector, "analyze_glrt64_dwell", lambda *a, **k: pytest.fail("reanalyzed metrics")
    )
    monkeypatch.setattr(sys, "argv", args)
    cli.main()
    ready = json.loads(capsys.readouterr().out)
    assert ready["overview_state"] == "ready" and ready["newly_analyzed_visits"] == 0
    status = presentation.status(receipt.session_id)
    assert status.state == "figures_ready"
    for artifact in status.overview.artifacts:
        assert presentation.artifact(
            receipt.session_id,
            artifact.name,
            binding_sha256=status.binding_sha256,
            artifact_sha256=artifact.sha256,
        ).startswith(b"\x89PNG")
    cli.main()
    assert json.loads(capsys.readouterr().out)["state"] == "idle"
