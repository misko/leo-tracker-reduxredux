import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

spec = importlib.util.spec_from_file_location("run135_test", Path(__file__).with_name("run.py"))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def setup(monkeypatch, tmp_path):
    monkeypatch.setattr(run, "HERE", tmp_path)
    monkeypatch.setattr(run, "ROOT", tmp_path)
    monkeypatch.setattr(run.sys, "argv", ["run.py", "--label", "member-0"])
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(name, "1")
    plan = dict(
        maximum_fit_calls=48,
        maximum_seconds_per_fit=90,
        maximum_iterations_per_fit=600,
        qualification_threshold=0.001,
        variants=["timestamp", "phase"],
        sources={"loader": "hash"},
        inputs={},
        members=[
            dict(label=f"member-{i}", parity_receipt="parity.json", case_binding={})
            for i in range(12)
        ],
    )
    plan["sources"] = {}
    (tmp_path / "protocol.json").write_text(json.dumps(plan))
    (tmp_path / "parity.json").write_text(json.dumps(dict(label="member-0", status="complete")))
    return plan


def test_import_failure_terminal_and_no_crash_retry(monkeypatch, tmp_path):
    setup(monkeypatch, tmp_path)

    def fail(*args):
        raise ImportError("synthetic failure")

    monkeypatch.setattr(run.runpy, "run_path", fail)
    run.main()
    receipt = json.loads((tmp_path / "results/member-0.json").read_text())
    assert receipt["status"] == "failed" and receipt["attempts"] == {}
    with pytest.raises(FileExistsError):
        run.main()


def test_actual_driver_uses_clean_ports_only(monkeypatch, tmp_path):
    plan = setup(monkeypatch, tmp_path)
    plan["sources"] = {"loader": "hash"}
    (tmp_path / "protocol.json").write_text(json.dumps(plan))
    actual_sha = run.sha
    monkeypatch.setattr(
        run, "sha", lambda path: "hash" if Path(path).name == "loader" else actual_sha(path)
    )
    calls = []

    def write(path, value):
        with path.open("x") as stream:
            json.dump(value, stream)

    monkeypatch.setattr(
        run.runpy, "run_path", lambda path: {"run_attempt": "fitter", "write": write}
    )

    def module(name, path):
        calls.append(Path(path).name)
        if "clean132" in name:
            return NS(
                build_model=lambda binding, loader, components: (
                    "model",
                    {"archive": "archive"},
                    {},
                ),
                numerical_components=lambda: {},
            )
        if "clean131" in name:
            return NS(InferenceLoader=lambda root, load: "clean")
        return NS(LOADER="loader", make_loader=lambda *args: NS(load_case="backend"))

    monkeypatch.setattr(run, "module", module)
    monkeypatch.setattr(
        run,
        "compare",
        lambda model, archive, fit: {
            "status": "complete",
            "attempts": {},
            "checked": [model, archive, fit],
        },
    )
    run.main()
    result = json.loads((tmp_path / "results/member-0.json").read_text())
    assert result["checked"] == ["model", "archive", "fitter"]
    assert calls == ["audit.py", "inference_loader.py", "entrypoint.py"]
