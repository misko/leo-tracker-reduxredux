from types import SimpleNamespace

import pytest

from leo.cli import adaptive_processing_queue as subject


@pytest.mark.parametrize("old", [False, True])
def test_policy_migration_enqueues_before_finishing_old_identity(monkeypatch, tmp_path, old):
    capture = SimpleNamespace(manifest_sha256="input")
    monkeypatch.setattr(
        subject,
        "AdaptiveHopIqStore",
        lambda *a, **k: SimpleNamespace(inspect=lambda _: capture, close=lambda: None),
    )
    monkeypatch.setattr(
        subject,
        "AdaptiveHopAnalysisPresentationStore",
        lambda *a: SimpleNamespace(
            status_for_capture=lambda *a, **k: SimpleNamespace(metrics_manifest_sha256="metrics")
        ),
    )
    monkeypatch.setattr(subject, "_tracking_digest", lambda **_: "new")
    calls = []
    catalog = SimpleNamespace(
        enqueue_adaptive_tracking_job=lambda **k: calls.append(("enqueue", k)),
        complete_job=lambda **k: calls.append(("complete", k)),
    )
    lease = SimpleNamespace(
        session_id="scan-1",
        input_manifest_digest="input",
        job_id=1,
        configuration_digest="old" if old else "new",
    )
    changed = subject._supersede_tracking_policy(
        bulk_root=tmp_path, worker_id="worker", catalog=catalog, site="site", lease=lease
    )
    assert changed == old
    assert [c[0] for c in calls] == (["enqueue", "complete"] if old else [])
    if old:
        assert calls[0][1]["configuration_digest"] == "new"
        assert calls[1][1]["outcome"] == "superseded-by-current-tracking-policy"
