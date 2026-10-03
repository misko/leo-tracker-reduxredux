from types import SimpleNamespace as NS

from leo.cli import partial_band_backfill as subject
from leo.storage.errors import BundleCorruptionError


def test_backfill_all_dates_and_idempotent_admission(monkeypatch):
    calls, rows = [], []
    captures = NS(
        publication_index=lambda: [(1, s) for s in ("wide", "ready", "new", "owned", "bad")],
        inspect=lambda s: NS(
            session_id=s,
            manifest_sha256=s,
            manifest=NS(
                receipt=NS(plan=NS(geometry=NS(sample_rate_hz=2500000 if s == "wide" else 1250000)))
            ),
        ),
    )

    def binding(capture):
        if capture.session_id == "bad":
            raise ValueError("unsupported geometry")
        return NS(digest="binding-" + capture.session_id)

    monkeypatch.setattr(subject, "binding_for_capture", binding)
    products = NS(
        status=lambda s, d: NS(
            state="figures_ready" if s == "ready" else "partial", completed_visits=3
        )
    )

    def enqueue(**kwargs):
        calls.append(kwargs)
        return kwargs["session_id"] == "new"

    result = subject.backfill(
        captures=captures,
        products=products,
        catalog=NS(enqueue_adaptive_analysis_job=enqueue),
        report=rows.append,
    )
    assert result == dict(
        inspected=5, low_rate=4, ready=1, queued=1, existing_job=1, pending=0, errors=1
    )
    assert [c["session_id"] for c in calls] == ["new", "owned"]
    assert all(c["priority"] == 0 and c["resource_class"] == "heavy" for c in calls)
    assert rows[-1]["outcome"] == "error"
    calls.clear()
    result = subject.backfill(captures=captures, products=products, report=rows.append)
    assert result["pending"] == 2
    assert result["queued"] == 0
    assert calls == []


def test_capture_store_error_is_reported_and_does_not_abort_inventory():
    rows = []

    def inspect(session_id):
        if session_id == "corrupt":
            raise BundleCorruptionError("invalid manifest seal")
        return NS(manifest=NS(receipt=NS(plan=NS(geometry=NS(sample_rate_hz=2500000)))))

    captures = NS(publication_index=lambda: [(1, "corrupt"), (0, "wide")], inspect=inspect)
    result = subject.backfill(captures=captures, products=NS(), report=rows.append)
    assert result["inspected"] == 2
    assert result["errors"] == 1
    assert rows == [dict(session_id="corrupt", outcome="error", error="invalid manifest seal")]
