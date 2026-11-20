"""Replay saved IQ with an opt-in same-window differential hint in each RX."""

from types import SimpleNamespace
from unittest.mock import patch

from .. import whole_iq
from . import differential_runtime_raw, whole_memory_chain_worker

MODULE = "tools.pipeline_eval.qualification.differential_runtime"
HINTED_SHA256 = "418e6d7569e73e2eb8b5107b50edf803d4d7271f1e863ffbba9c6b3c08380bd1"
STOCK_EVALUATE = whole_iq.evaluate
STOCK_WORKER = whole_iq.worker
CLOSURE = (
    "tools/pipeline_eval/qualification/differential_runtime.py",
    "tools/pipeline_eval/qualification/differential_runtime_raw.py",
    "tools/pipeline_eval/qualification/whole_memory_chain_worker.py",
    "tools/pipeline_eval/qualification/recording_to_v5.py",
    "tools/pipeline_eval/variants/differential_runtime.py",
    "tools/pipeline_eval/variants/differential_pilot.py",
    "tools/pipeline_eval/variants/frame_coherence.py",
    "tools/pipeline_eval/variants/hinted_glrt.py",
    "tools/pipeline_eval/variants/hinted_glrt.h",
    "tools/pipeline_eval/whole_iq.py",
)


def source_identity():
    return {name: whole_iq._sha(whole_iq.ROOT / name) for name in CLOSURE}


def evaluate(ident, detector, detector_sha256, receiver, out, cpus, limit_s):
    if detector_sha256.removeprefix("sha256:") != HINTED_SHA256:
        raise ValueError("the differential run requires the qualified hinted wide library")
    save = whole_iq.save_json
    sources = source_identity()

    def save_bound_plan(path, value):
        if path == out / "plan.json":
            value = {**value, "differential_sources": sources}
        save(path, value)

    with (
        patch.object(whole_iq, "MODULE", MODULE),
        patch.object(whole_iq.iq_service, "MODULE", MODULE),
        patch.object(whole_iq, "save_json", save_bound_plan),
    ):
        return STOCK_EVALUATE(ident, detector, detector_sha256, receiver, out, cpus, limit_s)


def worker(attempt):
    plan = whole_iq.read(attempt / "plan.json")
    if (
        plan.get("differential_sources") != source_identity()
        or plan.get("detector_sha256") != HINTED_SHA256
    ):
        raise ValueError("the differential source or hinted library binding changed")
    raw = SimpleNamespace(
        __name__=differential_runtime_raw.__name__, mark=whole_memory_chain_worker.mark
    )
    with patch.object(whole_iq, "raw", raw):
        STOCK_WORKER(attempt)


def main():
    with patch.multiple(whole_iq, evaluate=evaluate, worker=worker):
        # The CLI dispatcher references these patched names. evaluate and worker call
        # the saved stock functions below so this context cannot recurse into itself.
        whole_iq.main()


if __name__ == "__main__":
    main()
