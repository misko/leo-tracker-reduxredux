"""Complete the shifted authentic request after a sandbox-only import failure."""

import argparse
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from ..__main__ import local_output, save_json
from . import compact_transfer as trial
from .fresh_scenes import _destination, _read, _sha


def replay(output):
    primary = _read(trial.REPORT / "prediction-lock.json")
    if any(_sha(trial.REPORT / path) != digest for path, digest in primary["files"].items()):
        raise ValueError("primary compact transfer changed after seal")
    frozen = _read(trial.REPORT / "source-lock.json")
    if frozen["compact_transfer_worker.py"] != _sha(trial.WORKER):
        raise ValueError("the numerical solve wrapper changed")
    if frozen["v5_secant_fit.py"] != _sha(Path(trial.v5_secant_fit.__file__)):
        raise ValueError("the bounded secant optimizer changed")
    plan = next(r for r in _read(trial.REPORT / "requests.json") if r["id"] == trial.ROOF)
    document, original, stamps, objects, _, _ = trial.portable.authentic_roof()
    tile = dict(
        original, id=trial.ROOF, center=_destination(original["center"], 7.0, 1.5707963267948966)
    )
    row, data, objects = trial.bound_job(plan, document, tile, stamps, objects)
    if row != plan:
        raise ValueError("the corrected sandbox plumbing must replay the exact original request")

    package = Path(trial.v5_secant_fit.__file__).parent.parent
    with TemporaryDirectory(prefix="compact-measured-transfer.") as folder:
        scratch = Path(folder)
        support = ("__main__.py", "scoring.py", "corpus.py")
        for name in support:
            (scratch / name).write_bytes((package / name).read_bytes())

        def invocation(args, payload, timeout):
            # Bind immutable CLI support sources after trial.run_one assembles its sandbox.
            for name in support:
                args[-4:-4] = (
                    "--ro-bind",
                    str(scratch / name),
                    f"/worker/tools/pipeline_eval/{name}",
                )
            return original_invoke(args, payload, timeout)

        lock = dict(
            primary_sha256=_sha(trial.REPORT / "prediction-lock.json"),
            executable_sha256=_sha(Path(__file__)),
            support={name: _sha(scratch / name) for name in support},
            worker_input_sha256=plan["worker_input_sha256"],
        )
        save_json(output / "source-lock.json", lock)
        kernel = scratch / "projector.so"
        trial.orbit_projector.compile_kernel(kernel)
        original_invoke = trial.invoke
        with patch.object(trial, "invoke", invocation):
            result = trial.run_one(row, data, objects, kernel, 13)
    save_json(output / "prediction.json", result)
    save_json(
        output / "prediction-lock.json",
        {name: _sha(output / name) for name in ("source-lock.json", "prediction.json")},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=trial.REPORT / "measured-retry")
    opts = parser.parse_args()
    replay(local_output(opts.out))
