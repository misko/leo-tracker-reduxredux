import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
from test_adapter import fixture

SPEC = importlib.util.spec_from_file_location(
    "entrypoint116_test", Path(__file__).with_name("entrypoint.py")
)
E = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E)


def specification(tmp_path):
    paths = dict(loader_source=E.LOADER, document_path="document.json", imports_path="imports.json")
    hashes = {}
    for name in paths.values():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("synthetic-bound-file")
        hashes[name] = hashlib.sha256(p.read_bytes()).hexdigest()
    return dict(
        mode="preflight",
        binding=dict(
            paths,
            session_id=E.PILOT,
            loader_sha256=hashes[paths["loader_source"]],
            document_sha256=hashes[paths["document_path"]],
            imports_sha256=hashes[paths["imports_path"]],
        ),
        source_sha256={paths["loader_source"]: hashes[paths["loader_source"]]},
        input_sha256={paths[k]: hashes[paths[k]] for k in ("document_path", "imports_path")},
    )


def test_preflight_claim_identity_cost_and_idempotence(tmp_path):
    spec = specification(tmp_path)
    output = tmp_path / "preflight"
    obs, bank, model, _ = fixture()

    def factory(root, binding):
        assert (output / "claim.json").exists()
        return lambda binding: dict(
            observations=obs,
            bank=bank,
            prior=model.prior,
            tracks=[],
            identity={"input_manifest_sha256": "synthetic"},
        )

    ticks = iter([10.0, 12.0])
    row = E.preflight(spec, tmp_path, output, loader_factory=factory, clock=lambda: next(ticks))
    assert row["status"] == "complete" and row["elapsed_s"] == 2
    assert row["bank_count"] == 4 and row["observations_count"] == 8
    assert "bank_sha256" in row["identity"]
    assert (
        E.preflight(spec, tmp_path, output, loader_factory=lambda *a: pytest.fail("reloaded"))
        == row
    )


def test_crashed_preflight_claim_is_not_retried(tmp_path):
    spec = specification(tmp_path)
    output = tmp_path / "preflight"

    def interrupted(*args):
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        E.preflight(spec, tmp_path, output, loader_factory=interrupted)
    with pytest.raises(E.ClaimedWithoutReceipt):
        E.preflight(spec, tmp_path, output, loader_factory=lambda *a: pytest.fail("retried"))


def test_preflight_source_mismatch_stops_before_claim(tmp_path):
    spec = specification(tmp_path)
    (tmp_path / "document.json").write_text("changed")
    with pytest.raises(ValueError, match="source/input mismatch"):
        E.preflight(
            spec, tmp_path, tmp_path / "out", loader_factory=lambda *a: pytest.fail("loaded")
        )
    assert not (tmp_path / "out").exists()


def test_failed_preflight_is_terminal(tmp_path):
    spec = specification(tmp_path)

    def fail(*args):
        raise ValueError("bad public input")

    row = E.preflight(spec, tmp_path, tmp_path / "out", loader_factory=fail)
    assert row["status"] == "failed" and "bad public input" in row["error"]
    assert (
        E.preflight(
            spec, tmp_path, tmp_path / "out", loader_factory=lambda *a: pytest.fail("retried")
        )
        == row
    )


def test_run_cli_validates_then_delegates_one_slice(tmp_path, monkeypatch):
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(name, "1")
    plan = dict(mode="search", binding=dict(session_id=E.PILOT), preflight_runtime=E.runtime())
    monkeypatch.setattr(E, "read", lambda p: plan)
    calls = []
    monkeypatch.setattr(E, "verify_plan", lambda p, r: calls.append("verified"))

    def run(p, r, o, loader):
        assert calls == ["verified"]
        calls.append("one-slice")
        return dict(status="pending", slices=1)

    monkeypatch.setattr(E, "run_slice", run)
    monkeypatch.setattr(E, "make_loader", lambda *a: pytest.fail("eager reconstruction"))
    assert (
        E.main(
            [
                "run",
                "--protocol",
                str(tmp_path / "protocol.json"),
                "--output",
                str(tmp_path / "out"),
            ]
        )
        == 0
    )
    assert calls == ["verified", "one-slice"]


def test_cli_rejects_unbounded_thread_count_before_loading(monkeypatch):
    monkeypatch.setenv("OPENBLAS_NUM_THREADS", "2")
    monkeypatch.setattr(E, "read", lambda p: pytest.fail("read before thread guard"))
    with pytest.raises(ValueError, match="must all equal 1"):
        E.main(["preflight", "--protocol", "unused", "--output", "unused"])
