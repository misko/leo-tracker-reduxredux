"""Research overlay for exact, row-parallel native likelihood residuals."""

import ctypes
import subprocess
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff

STOCK_ROWS = ("        for(int i=0;i<n;i++) {\n"
              "            int g=(int)groups[i];double val=0.;\n"
              "            for(int z=l->offset[g];z<l->offset[g+1];z++)"
              "{int j=l->columns[z];val+=u[(size_t)i*p+j]*mean[j];}\n"
              "            native[i]=y[i]-val;double r=native[i]/sigma[i];energy[g]+=r*r;\n"
              "            if(!isfinite(native[i])){code=NB_NONFINITE;goto done;}\n"
              "        }")


def replace_rows(source):
    helper = Path(__file__).with_suffix(".h").read_text()
    source = handoff.replace(source, "/* All work belongs", helper + "\n/* All work belongs")
    source = handoff.replace(source, "    double change=INFINITY,", """
    ResidualRows packed_rows = prepare_residual_rows(l, groups, u);
    double change=INFINITY,""")
    source = handoff.replace(source, STOCK_ROWS, """
        code = residual_energy(l, &packed_rows, groups, y, u, sigma, mean, native, energy);
        if (code != NB_OK) goto done;""")
    return handoff.replace(source, "    free(work);return code;", """    free(packed_rows.blocks);
    free(packed_rows.values);
    free(work);return code;""")


def build(output):
    if native_bound.digest(native_bound.SOURCE) != handoff.SOURCE_SHA256:
        raise ValueError("Expected the reviewed native likelihood source")
    output.mkdir(parents=True, exist_ok=False)
    reference_grid = output / "reference-grid.so"
    handoff.build(reference_grid)
    sources = (("bound", native_bound.SOURCE), ("grid", reference_grid.with_suffix(".c")))
    for name, source in sources:
        generated = output / f"packed-{name}.c"
        generated.write_text(replace_rows(source.read_text()))
        subprocess.run(["cc", *native_bound.FLAGS, "-Wall", "-Wextra", "-Werror",
                        str(generated), "-lm", "-o", str(generated.with_suffix(".so"))],
                       timeout=30, check=True)


@contextmanager
def packed_residual(bound, grid):
    library = ctypes.CDLL(str(bound))
    operation = library.nb_run
    initialize = native_bound.NativeBound.__init__
    original_handoff = handoff.grid_handoff

    def initialize_with_packed(self, *args, **kwargs):
        initialize(self, *args, **kwargs)
        operation.argtypes = self.run.argtypes
        operation.restype = self.run.restype
        self.run = operation

    def packed_grid(port, _reviewed_library, in_grid):
        return original_handoff(port, grid, in_grid)

    with (
        patch.object(native_bound.NativeBound, "__init__", initialize_with_packed),
        patch.object(handoff, "grid_handoff", packed_grid),
    ):
        yield
