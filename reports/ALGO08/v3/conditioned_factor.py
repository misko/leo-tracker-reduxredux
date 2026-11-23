"""Native matched stock and triangular condition-certificate overlay."""

from collections import Counter
from contextlib import contextmanager
import ctypes as ct
from hashlib import sha256
from pathlib import Path
import subprocess
from time import process_time_ns
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
SOURCE_SHA = "40888d6143f385c2146e5e2cb28ea99a96b2f1bb791fab4c22b5afaaa2b3a23b"


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def adjusted(source):
    from tools.pipeline_eval.variants.algo08_posterior_handoff import replace

    marker = "/* All work belongs"
    source = replace(source, marker, (HERE / "conditioned_factor.inc").read_text() + "\n" + marker)
    return replace(
        source,
        "double rcond=0.;if(pocon(102,'L',s,root,s,norm,&rcond) || !isfinite(rcond) || rcond<min_rcond)",
        "if(schur_condition(pocon,s,root,norm,min_rcond))",
    )


def build(directory, mode):
    from leo.analysis.localization_v4 import native_bound
    from tools.pipeline_eval.variants import algo08_posterior_handoff as posterior

    if mode not in {"stock", "certificate"} or digest(native_bound.SOURCE) != SOURCE_SHA:
        raise ValueError("Expected an authenticated likelihood and a declared build")
    directory.mkdir()
    base = directory / "source-grid.so"
    posterior.build(base)
    common = native_bound.SOURCE.read_text()
    sources = {"ordinary": common, "grid": base.with_suffix(".c").read_text()}
    output = {}
    for name, stock in sources.items():
        source = directory / (name+".c")
        source.write_text(adjusted(stock))
        library = source.with_suffix(".so")
        flags = ["-DLEO_CONDITION_CERT=1"] if mode == "certificate" else []
        command = ["cc", *native_bound.FLAGS, "-Wall", "-Wextra", "-Werror", *flags, str(source),
                   "-lm", "-o", str(library)]
        subprocess.run(command, check=True, timeout=30)
        output[name] = dict(path=str(library), command=command, binary_sha256=digest(library),
                            source_sha256=digest(source))
    return output


@contextmanager
def supplied_kernel(port, compiled):
    from tools.pipeline_eval.variants import algo08_posterior_handoff as posterior

    ordinary = ct.CDLL(compiled["ordinary"]["path"])
    grid = ct.CDLL(compiled["grid"]["path"])
    counts = {name: Counter() for name in (*compiled, "fallback")}
    original_native = port.NativeBound
    original_grid, run_capture = posterior.grid_handoff, posterior.Capture.run

    class MeasuredBound(original_native):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            stock = self.run
            operation = ordinary.nb_run
            operation.argtypes, operation.restype = stock.argtypes, stock.restype

            def run(*args):
                start = process_time_ns()
                code = operation(*args)
                counts["ordinary"]["native_cpu_ns"] += process_time_ns()-start
                counts["ordinary"]["calls"] += 1
                counts["ordinary"][f"status_{code}"] += 1
                return code

            run.argtypes, run.restype = stock.argtypes, stock.restype
            self.run = run

        def __call__(self, *args, **kwargs):
            pre = self.counts.copy()
            result = super().__call__(*args, **kwargs)
            for key, value in self.counts.items():
                if key.startswith("fallback_"):
                    counts["fallback"][key] += value-pre[key]
            return result

    def grid_context(owner, _library, in_grid):
        return original_grid(owner, compiled["grid"]["path"], in_grid)

    def capture(capture, owner, operation, args):
        start = process_time_ns()
        code = run_capture(capture, owner, operation, args)
        counts["grid"]["native_cpu_ns"] += process_time_ns()-start
        counts["grid"]["calls"] += 1
        counts["grid"][f"status_{code}"] += 1
        return code

    with (patch.object(port, "NativeBound", MeasuredBound),
          patch.object(posterior, "grid_handoff", grid_context),
          patch.object(posterior.Capture, "run", capture)):
        yield counts
    for name, library in (("ordinary", ordinary), ("grid", grid)):
        result = (ct.c_uint64*3)()
        library.nb_conditioning_counts.argtypes = [ct.POINTER(ct.c_uint64)]
        library.nb_conditioning_counts.restype = None
        library.nb_conditioning_counts(result)
        counts[name].update(dict(zip(("condition_calls", "skip_calls", "reject_calls"),
                                     map(int, result), strict=True)))
