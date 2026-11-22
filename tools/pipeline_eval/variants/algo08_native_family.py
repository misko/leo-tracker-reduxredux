"""Time a second family-level Schur factor inside the native ALGO08v2 bound."""

import ctypes
from contextlib import contextmanager
from pathlib import Path
import subprocess
from time import process_time
from unittest.mock import patch

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants.algo08_bound_statistics import SOURCE_SHA256, replace


def build(output):
    source_path = native_bound.SOURCE
    if native_bound.digest(source_path) != SOURCE_SHA256:
        raise ValueError("Incompatible native bound source")
    source = source_path.read_text()
    source = replace(source, "} Layout;", """
    struct FamilyLayout *families;
} Layout;
""" + Path(__file__).with_suffix(".h").read_text())
    source = replace(source, "free(l->width);free(l);", "free(l->width);free(l->families);free(l);")
    source = replace(source, "free(active);free(support);*status=NB_OK;return l;", """
    free(active);free(support);l->families=family_layout(l);*status=NB_OK;return l;
    """)
    source = replace(source, "3*sz+(l->qmax?l->qmax:1);", """
        3*sz+(l->qmax?l->qmax:1)+(l->families ? (size_t)sz*sz : 0);
    """)
    source = replace(source, "    /* Current group Gram/RHS", """
    double *schur_work=row_f+sz;
    /* Current group Gram/RHS""")
    source = replace(source, "            memcpy(root,a,(size_t)s*s*sizeof(double));", """
            if (!family_factor(l->families,s,a,bg,norm,min_rcond,potrf,potrs,potri,pocon,
                               root,cov,xg,schur_work,&logdet)) {
            memcpy(root,a,(size_t)s*s*sizeof(double));
    """)
    source = replace(source, "        /* T=QF,", "            }\n        /* T=QF,")
    output = Path(output)
    c_file = output.with_suffix(".c")
    c_file.write_text(source)
    subprocess.run(["cc", *native_bound.FLAGS, "-Wall", "-Wextra", "-Werror", str(c_file),
                    "-lm", "-o", str(output)], check=True, timeout=30)


@contextmanager
def measured_backend(port, binary=None):
    """Keep release validation and fallbacks around the instrumented C call."""
    backend, instances = port.NativeBound, []
    usage = dict(kernel_cpu_s=0., kernel_calls=0)
    library = None if binary is None else ctypes.CDLL(str(binary))
    keys = ("family_attempts", "family_activated", "original_width_sum", "radio_width_sum",
            "original_width_cube_sum", "radio_width_cube_sum")
    if library is not None:
        get = library.nb_family_counts
        get.argtypes, get.restype = [ctypes.POINTER(ctypes.c_uint64)], None
        set_gemm = library.nb_family_gemm
        set_gemm.argtypes, set_gemm.restype = [ctypes.c_void_p], None

        def read_counts():
            values = (ctypes.c_uint64 * len(keys))()
            get(values)
            return list(values)

        before = read_counts()

    def factory(*args, **kwargs):
        bound = backend(*args, **kwargs)
        if library is not None:
            set_gemm(ctypes.cast(bound.provider.scipy_cblas_dgemm, ctypes.c_void_p))
            for attr, symbol in (("run", "nb_run"), ("layout", "nb_layout"), ("free", "nb_free")):
                original = getattr(bound, attr)
                operation = getattr(library, symbol)
                operation.argtypes, operation.restype = original.argtypes, original.restype
                setattr(bound, attr, operation)
        kernel = bound.run

        def run(*args):
            start = process_time()
            try:
                return kernel(*args)
            finally:
                usage["kernel_cpu_s"] += process_time() - start
                usage["kernel_calls"] += 1

        bound.run = run
        instances.append(bound)
        return bound

    try:
        with patch.object(port, "NativeBound", factory):
            yield usage
    finally:
        for bound in instances:
            for key, value in bound.counts.items():
                usage[key] = usage.get(key, 0) + value
            bound.clear()
        if library is not None:
            usage.update({key: b-a for key, a, b in zip(keys, before, read_counts(), strict=True)})
            set_gemm(None)
