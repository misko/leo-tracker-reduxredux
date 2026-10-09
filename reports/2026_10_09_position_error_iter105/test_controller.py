"""No numerical process is launched by controller tests."""

import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "pilot_controller105", Path(__file__).with_name("controller.py")
)
controller = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(controller)


@pytest.fixture(autouse=True)
def frozen_protocol(tmp_path):
    (tmp_path / "protocol.json").write_text("{}")


def marker(folder, phase, status):
    (folder / f"{phase}.json").write_text(
        json.dumps({"status": status, "protocol_sha256": hashlib.sha256(b"{}").hexdigest()})
    )


def test_resume_counts_existing_claims_and_runs_phases_serially(tmp_path):
    folder = tmp_path / "results" / "member"
    claims = folder / "slices"
    claims.mkdir(parents=True)
    (claims / "baseline-01.started.json").write_text("{}")
    called = []

    def invoke(command, **options):
        phase = command[-1]
        called.append(phase)
        count = len(list(claims.glob(f"{phase}-*.started.json")))
        (claims / f"{phase}-{count + 1:02}.started.json").write_text("{}")
        marker(folder, phase, "complete")
        return SimpleNamespace(returncode=0)

    assert controller.run_member("member", here=tmp_path, invoke=invoke) == {
        "baseline": "complete",
        "candidate": "complete",
    }
    assert called == ["baseline", "candidate"]
    assert len(list(claims.glob("baseline-*.started.json"))) == 2


def test_budget_finalization_does_not_start_candidate(tmp_path):
    folder = tmp_path / "results" / "member"
    claims = folder / "slices"
    claims.mkdir(parents=True)
    called = []

    def invoke(command, **options):
        phase = command[-1]
        called.append(phase)
        count = len(list(claims.glob(f"{phase}-*.started.json")))
        if count < 6:
            (claims / f"{phase}-{count + 1:02}.started.json").write_text("{}")
        else:
            marker(folder, phase, "budget-exhausted")
        return SimpleNamespace(returncode=0)

    assert controller.run_member("member", here=tmp_path, invoke=invoke) == {
        "baseline": "budget-exhausted"
    }
    assert called == ["baseline"] * 7


def test_nonzero_child_and_idle_child_stop_without_retry(tmp_path):
    for code, message in ((2, "exited"), (0, "No new slice")):
        calls = []

        def invoke(*args, calls=calls, code=code, **kwargs):
            calls.append(1)
            return SimpleNamespace(returncode=code)

        with pytest.raises(RuntimeError, match=message):
            controller.run_member("member", here=tmp_path, invoke=invoke)
        assert calls == [1]


def test_completed_member_reuses_receipts_without_process(tmp_path):
    folder = tmp_path / "results" / "member"
    folder.mkdir(parents=True)
    for phase in ("baseline", "candidate"):
        marker(folder, phase, "complete")
    assert controller.run_member(
        "member", here=tmp_path, invoke=lambda *a, **k: pytest.fail("unexpected child")
    ) == {"baseline": "complete", "candidate": "complete"}


def test_stale_terminal_receipt_is_not_reused(tmp_path):
    folder = tmp_path / "results" / "member"
    folder.mkdir(parents=True)
    (folder / "baseline.json").write_text('{"status":"complete","protocol_sha256":"old"}')
    with pytest.raises(ValueError, match="different frozen protocol"):
        controller.run_member(
            "member", here=tmp_path, invoke=lambda *a, **k: pytest.fail("unexpected child")
        )
