"""Review contiguous column-norm accumulation with the frozen likelihood."""

import ctypes
import subprocess
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff


def column_norm_source(source):
    header = Path(__file__).with_suffix(".h").read_text()
    source = handoff.replace(source, "/* All work belongs", header + "\n/* All work belongs")
    for norm, dense, private in (("full_norm", "a", "e"),
                                 ("inverse_norm", "cov", "cross")):
        original = f"""        double {norm}=0.;
        for(int j=0;j<s;j++) {{
            double z=0.;for(int h=0;h<s;h++)z+=fabs({dense}[j*s+h]);
            for(int g=0;g<k;g++)for(int c=0;c<l->width[g];c++)z+=fabs({private}[(2*g+c)*sz+j]);
            if(z>{norm}){norm}=z;
        }}"""
        # xg is written by the factor solve after the first norm. The inverse
        # norm still needs it, so use the untouched shared Gram storage there.
        scratch = "xg" if norm == "full_norm" else "a"
        updated = f"        double {norm}=shared_column_norms(l,{dense},{private},{scratch});"
        source = handoff.replace(source, original, updated)
    return source


def build(output):
    if native_bound.digest(native_bound.SOURCE) != handoff.SOURCE_SHA256:
        raise ValueError("Expected the reviewed native likelihood source")
    output.mkdir(parents=True, exist_ok=False)
    reference_grid = output / "reference-grid.so"
    handoff.build(reference_grid)
    sources = (("bound", native_bound.SOURCE), ("grid", reference_grid.with_suffix(".c")))
    for name, source in sources:
        generated = output / f"column-norms-{name}.c"
        generated.write_text(column_norm_source(source.read_text()))
        subprocess.run(["cc", *native_bound.FLAGS, "-Wall", "-Wextra", "-Werror",
                        str(generated), "-lm", "-o", str(generated.with_suffix(".so"))],
                       timeout=30, check=True)


@contextmanager
def column_norms(binary, grid):
    operation = ctypes.CDLL(str(binary)).nb_run
    initialize = native_bound.NativeBound.__init__
    original_handoff = handoff.grid_handoff

    def initialize_with_column_norms(self, *args, **kwargs):
        initialize(self, *args, **kwargs)
        operation.argtypes = self.run.argtypes
        operation.restype = self.run.restype
        self.run = operation

    def grid_with_column_norms(port, _reviewed_library, in_grid):
        return original_handoff(port, grid, in_grid)

    with (patch.object(native_bound.NativeBound, "__init__", initialize_with_column_norms),
          patch.object(handoff, "grid_handoff", grid_with_column_norms)):
        yield
