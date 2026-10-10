from dataclasses import asdict
from types import SimpleNamespace as NS

import numpy as np
import pytest
from adapter import Window
from controller import launch
from run import execute, write_new


def fixture():
    window = Window("a", 0, 0, 0, 0, 0, 0, 0, 1, 0, True, probe_count=50000)
    row = {**asdict(window), "status": "metadata-ready"}
    metadata = dict(
        session_id="s",
        input_manifest_sha256="hash",
        sample_rate_hz=2500000,
        receiver_ids=[0],
        window_ids=["a"],
        windows=[row],
        visits={"0": {"sample_count": 50000, "valid_start_counter": 42}},
    )
    capture = NS(
        manifest_sha256="hash",
        manifest=NS(
            receipt=NS(plan=NS(geometry=NS(sample_rate_hz=2500000, receiver_ids=[0]))),
            chunks=[NS(uncompressed_bytes=200000)],
        ),
    )

    class Reader:
        session = capture
        reads = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read_visit_ci16(self, index):
            self.reads += 1
            return NS(event=NS(valid_start_counter=42), valid_sample_count=50000), np.zeros(
                (50000, 1, 2), dtype=np.int16
            )

    reader = Reader()
    store = NS(reader=lambda session: reader)
    plan = dict(
        maximum_chunk_bytes=64 * 1024**2,
        maximum_visit_bytes=32 * 1024**2,
        maximum_case_seconds=1200,
    )
    return metadata, plan, store, reader


def test_actual_adapter_driver_success_and_callback_failure():
    metadata, plan, store, reader = fixture()
    result = list(
        execute(metadata, plan, store=store, evaluator=lambda *args: {"parity": "passed"})
    )
    assert result == [{"window_id": "a", "status": "complete", "result": {"parity": "passed"}}]
    assert reader.reads == 1

    def failure(*args):
        raise ValueError("parity mismatch")

    result = list(execute(metadata, plan, store=store, evaluator=failure))
    assert result[0]["status"] == "parity-or-window-failed"


@pytest.mark.parametrize("change", ["digest", "chunk", "budget"])
def test_no_iq_read_on_identity_resource_or_deadline(change):
    metadata, plan, store, reader = fixture()
    if change == "digest":
        metadata["input_manifest_sha256"] = "wrong"
    if change == "chunk":
        plan["maximum_chunk_bytes"] = 1
    if change == "budget":
        plan["maximum_case_seconds"] = 0
    result = list(execute(metadata, plan, store=store))
    assert reader.reads == 0
    assert len(result) == 1 and result[0]["status"] != "complete"


def test_controller_crash_claim_never_retries(tmp_path):
    plan = {"members": [{"label": "a"}]}
    calls = []

    def failed(*args, **kwargs):
        calls.append(1)
        return NS(returncode=1)

    with pytest.raises(RuntimeError):
        launch(["a"], plan, "p", here=tmp_path, call=failed)
    with pytest.raises(FileExistsError):
        launch(["a"], plan, "p", here=tmp_path, call=failed)
    assert len(calls) == 1


def test_controller_terminal_identity_and_membership(tmp_path):
    plan = {"members": [{"label": "a"}]}
    with pytest.raises(ValueError):
        launch(["other"], plan, "p", here=tmp_path)
    write_new(
        tmp_path / "results/a/result.json",
        {"label": "a", "protocol_sha256": "stale", "status": "complete"},
    )
    with pytest.raises(ValueError, match="stale"):
        launch(["a"], plan, "p", here=tmp_path)


def test_circular_boundary_keeps_local_step():
    from evaluate import circular_change, refinement

    p = 512 * refinement.DELTA_HZ
    values = np.exp(2j * np.pi * 255.8 / 512 * np.arange(64))[None, :]
    result = refinement.refine(values, native_bin=256)
    change = circular_change(result["newton_hz"], result["coarse_hz"])
    assert abs(change["circular_hz"]) < refinement.DELTA_HZ / 2
    assert change["raw_hz"] == pytest.approx(change["circular_hz"] + change["wrap_count"] * p)
    assert abs(change["wrap_count"]) == 1
