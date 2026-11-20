"""Second independent holdout for the terminal compact tile guard."""

import argparse
import secrets
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from ..__main__ import save_json
from ..variants import compact_tile_interior as edge
from . import transfer_budget as base
from .fresh_scenes import _read, _sha

REPORT = base.REPORT / "interior-guard"
WORKER = Path(__file__).with_name("transfer_edge_worker.py")
METHOD = "v5_secant_transfer_interior"
ROLES = ("original", "near-inside", "near-outside")


def replay(scratch):
    files = (
        Path(__file__),
        WORKER,
        Path(edge.__file__),
        base.WORKER,
        Path(base.__file__),
        Path(base.scenes.__file__),
        REPORT / "PROTOCOL.md",
        base.REPORT / "prediction-lock.json",
    )
    source = base.compact.portable.source_lock() | {p.name: _sha(p) for p in files}
    save_json(REPORT / "source-lock.json", source)
    with patch.multiple(base.scenes, SITE=(-23.0, 15.0), ROLES=ROLES):
        base.scenes.generate(scratch, secrets.token_bytes(32))
    jobs, history = base.scenes.jobs(scratch)
    manifest_names = (
        "public/cases.json",
        "public/native.json",
        "private/truth.json",
        "private/seed.bin",
    )
    inputs = {name: _sha(scratch / name) for name in manifest_names}
    save_json(REPORT / "input-lock.json", inputs)
    save_json(REPORT / "history.json", history)
    finished = [(job, mode) for job in jobs for mode in ("edge", "gate")]
    save_json(REPORT / "requests.json", [dict(job[0], mode=mode) for job, mode in finished])
    kernel = scratch / "projector.so"
    base.compact.orbit_projector.compile_kernel(kernel)
    original = base.compact.invoke

    def invoke(command, data, timeout):
        if command[-1] == "edge":
            command[-1] = "gate"
            command[-3] = "/trial/edge.py"
            bindings = (
                (WORKER, "/trial/edge.py"),
                (
                    Path(edge.__file__),
                    f"/worker/tools/pipeline_eval/variants/{Path(edge.__file__).name}",
                ),
            )
            for path, target in bindings:
                command[-5:-5] = ("--ro-bind", str(path), target)
        return original(command, data, timeout)

    def lane(cpu, items):
        return [base.run_one(job, kernel, cpu, mode, 105) for job, mode in items]

    methods = base.METHODS | {"edge": METHOD}
    with (
        patch.object(base, "METHODS", methods),
        patch.object(base.compact, "invoke", invoke),
        ThreadPoolExecutor(max_workers=4) as pool,
    ):
        lanes = [pool.submit(lane, cpu, finished[i::4]) for i, cpu in enumerate(base.CPUS)]
        records = [row for lane_result in lanes for row in lane_result.result()]
    save_json(REPORT / "predictions.json", records)
    if any(_sha(scratch / name) != digest for name, digest in inputs.items()):
        raise ValueError("interior holdout inputs changed")
    material = (
        "predictions.json",
        "source-lock.json",
        "requests.json",
        "input-lock.json",
        "history.json",
    )
    save_json(REPORT / "prediction-lock.json", {name: _sha(REPORT / name) for name in material})
    save_json(REPORT / "released-truth.json", _read(scratch / "private/truth.json"))
    save_json(
        REPORT / "released-seed.json",
        dict(seed_hex=(scratch / "private/seed.bin").read_bytes().hex()),
    )
    save_json(REPORT / "fresh-draw.json", _read(scratch / "public/cases.json"))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("scratch", type=Path)
    args = cli.parse_args()
    replay(args.scratch)
