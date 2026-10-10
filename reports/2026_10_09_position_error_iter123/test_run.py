import hashlib
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest
import run


def test_actual_main_full_branch_cached_resume_and_thread_gate(tmp_path, monkeypatch):
    import numpy as np

    plan = dict(
        source_sha256={},
        input_sha256={},
        binding={},
        identity={"physical": "same"},
        branches={
            "native": [dict(point=[float(i), 0.0], original={"source": i}) for i in range(3)]
        },
    )
    protocol = tmp_path / "protocol.json"
    protocol.write_text(json.dumps(plan))
    output = tmp_path / "outputs"
    monkeypatch.setattr(
        sys, "argv", ["run", "native", "--protocol", str(protocol), "--output", str(output)]
    )
    for name in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS"):
        monkeypatch.setenv(name, "1")

    def write(path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x") as stream:
            json.dump(value, stream)

    def digest(value):
        return "sha256:" + hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()

    class Expired(Exception):
        pass

    core = SimpleNamespace(
        canonical_digest=digest,
        json_value=lambda value: value,
        HARD60_SCORE={},
        RegionalSliceExpired=Expired,
    )
    calls = []

    def claim(directory, phase, value, *, maximum):
        assert phase == "baseline" and maximum == 6
        return 1

    def recover(obs, bank, prior, trigger, stage):
        calls.append(trigger["key"])
        return stage(trigger["key"], 90, lambda: dict(finals=[], preserved=trigger["original"]))

    def joint(obs, bank, prior, regions, stage):
        assert len(regions) == 3
        return stage("joint", 90, lambda: {"zero-c": {}, "fitted-c": {}})["result"], [], []

    backend = dict(
        core=core,
        read=lambda path: json.loads(path.read_text()),
        write=write,
        claim_slice=claim,
        recovered_region=recover,
        run_joint_stages=joint,
    )
    namespace = {}
    exec("def load_case(document): return None", namespace)
    namespace.update(backend)
    case = dict(
        observations="obs",
        bank=SimpleNamespace(numbers=np.array([1, 2])),
        prior={},
        identity={"input_manifest_sha256": "input"},
    )
    loader = SimpleNamespace(load_case=namespace["load_case"])

    class Loader:
        load_case = loader.load_case

        def __call__(self, binding):
            return case

    entry = SimpleNamespace(make_loader=lambda root, binding: Loader())
    monkeypatch.setattr(run, "load_search_entrypoint", lambda: entry)
    driver = ModuleType("driver")
    driver.case_identity = lambda case: {"physical": "same"}
    monkeypatch.setitem(sys.modules, "driver", driver)
    run.main()
    result = json.loads((output / "native/result.json").read_text())
    assert result["status"] == "complete" and not result["fallback_available"]
    assert len(calls) == 3
    assert len(list((output / "native/stages").glob("*.claim.json"))) == 4
    run.main()
    assert len(calls) == 3
    monkeypatch.setenv("OMP_NUM_THREADS", "2")
    with pytest.raises(ValueError, match="single-thread"):
        run.main()
