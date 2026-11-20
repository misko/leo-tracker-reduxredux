"""Count repository-owned Python functions entered by a measured position worker."""

import argparse
import gzip
import json
import os
import sys
import tempfile
from pathlib import Path

from tools.pipeline_eval.__main__ import (
    DEFAULT_OUT,
    encoded,
    local_output,
    public_cases,
    references,
    write,
)
from tools.pipeline_eval.variants import orbit_projector, v5_core, v5_lean


def trace_worker(request, result):
    method = os.environ["LEO_PREFIX_TRACE_METHOD"]
    if method == "orbit_projector":
        library = Path(request).parent / "orbit_projector.so"
        orbit_projector.compile_kernel(library)

        def entry(source, target):
            return orbit_projector.worker(source, target, library)
    else:
        entry = {"v5_core": v5_core.worker, "v5_lean": v5_lean._worker}[method]
    own = {v5_core.__file__: "variants/v5_core.py", v5_lean.__file__: "variants/v5_lean.py"}
    own[orbit_projector.__file__] = "variants/orbit_projector.py"
    prefix = str(v5_lean.SOURCE) + "/"
    trace = Path(request).parent / "functions.jsonl"
    fd = os.open(trace, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_APPEND, 0o600)
    monitor = sys.monitoring

    def entered(code, offset):
        filename = code.co_filename
        name = filename.removeprefix(prefix) if filename.startswith(prefix) else own.get(filename)
        if name is not None and not code.co_name.startswith("<"):
            row = [name, code.co_qualname, code.co_firstlineno]
            # A forked numerical worker keeps this descriptor. One atomic append captures its call.
            os.write(fd, encoded(row) + b"\n")
        return monitor.DISABLE

    tool = monitor.PROFILER_ID
    monitor.use_tool_id(tool, "v5-footprint")
    monitor.register_callback(tool, monitor.events.PY_START, entered)
    monitor.set_events(tool, monitor.events.PY_START)
    try:
        entry(request, result)
    finally:
        monitor.set_events(tool, 0)
        monitor.free_tool_id(tool)
        os.close(fd)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--method", choices=("v5_core", "v5_lean", "orbit_projector"), required=True
    )
    parser.add_argument("--case", choices=("DS26-0036", "DS29-0082"), required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    source, refs = references("smoke", [args.case])
    (case,) = public_cases(source, refs, DEFAULT_OUT / "inputs")
    out = local_output(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    os.environ["LEO_PREFIX_TRACE_METHOD"] = args.method
    with tempfile.TemporaryDirectory(dir=out.parent) as work:
        result = v5_lean.run_bound_worker(case, Path(work), Path(__file__))
        if result["status"] != "ok":
            raise ValueError(f"traced worker did not return a position: {result.get('reason')}")
        with (Path(work) / "functions.jsonl").open() as stream:
            calls = sorted({tuple(row) for row in map(json.loads, stream)})
    data = dict(recording=args.case, method=args.method, functions=calls, arms=result["arms"])
    write(out, gzip.compress(encoded(data) + b"\n", mtime=0))
    print(f"{len(calls)} named functions in {len({f[0] for f in calls})} source files")


if __name__ == "__main__":
    if len(sys.argv) == 3 and not sys.argv[1].startswith("--"):
        trace_worker(*sys.argv[1:])
    else:
        main()
