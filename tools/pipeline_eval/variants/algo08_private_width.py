"""Research-only wider private Schur blocks for stock layout fallbacks."""

import json
import re
import subprocess
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants.algo08_posterior_handoff import SOURCE_SHA256, replace


def expanded_source():
    if native_bound.digest(native_bound.SOURCE) != SOURCE_SHA256:
        raise ValueError("Expected the exact installed likelihood source")
    original = native_bound.SOURCE.read_text()
    header = Path(__file__).with_suffix(".h").read_text()
    source = replace(original, "typedef struct {", header + "\ntypedef struct {")
    source = replace(source, "if(d>=2)", "if(d>=NB_PRIVATE)")
    source = replace(source, "malloc(2*k*sizeof(int))", "malloc(NB_PRIVATE*k*sizeof(int))")
    source = replace(
        source, "6*(size_t)k*sz+13*(size_t)k",
        "3*NB_PRIVATE*(size_t)k*sz+(2*NB_PRIVATE_SQUARE+NB_PRIVATE+3)*(size_t)k",
    )
    source = replace(source, "double z[2]={b[2*g],b[2*g+1]};", """double z[NB_PRIVATE];
            memcpy(z,b+NB_PRIVATE*g,sizeof(z));""")
    for old, new in (
        (r"\b2\*\(size_t\)k\*sz", "NB_PRIVATE*(size_t)k*sz"),
        (r"\b4\*([gk])\b", r"NB_PRIVATE_SQUARE*\1"),
        (r"\b2\*([gk])\b", r"NB_PRIVATE*\1"),
        (r"\b2\*(dj|j|h|c)\b", r"NB_PRIVATE*\1"),
        (r"\b2\*l->private_index\[cj\]", r"NB_PRIVATE*l->private_index[cj]"),
    ):
        source = re.sub(old, new, source)
    for array in ("dd", "iv"):
        source = source.replace(f"{array}[3]", f"{array}[NB_PRIVATE+1]")
        source = source.replace(f"{array}[2]", f"{array}[NB_PRIVATE]")
    source = replace(source, "memset(iv,0,4*sizeof(double))",
                     "memset(iv,0,NB_PRIVATE_SQUARE*sizeof(double))")
    source = replace(source, "double local[4]", "double local[NB_PRIVATE_SQUARE]")
    source = replace(source, "local[3*c]", "local[(NB_PRIVATE+1)*c]")
    return replace(source, "                logdet+=log(det);\n            }", """
                logdet+=log(det);
            } else if (nd > 2) {
                code=inverse_private(nd,dd,iv,&logdet,min_rcond,potrf,potri,pocon);
                if(code!=NB_OK)goto done;
            }""")


def build(directory):
    directory.mkdir(parents=True, exist_ok=False)
    source, output = directory / "private_width.c", directory / "private_width.so"
    source.write_text(expanded_source())
    command = ["cc", *native_bound.FLAGS, "-Wall", "-Wextra", "-Werror", str(source),
               "-lm", "-o", str(output)]
    subprocess.run(command, timeout=30, check=True)
    (directory / "manifest.json").write_text(json.dumps(dict(
        binary_sha256=native_bound.digest(output), source_sha256=native_bound.digest(source),
        parent_source_sha256=SOURCE_SHA256, command=command,
    )))
    return output


@contextmanager
def expand_unsupported_layout(library):
    """Try the wider backend only after the stock library rejects a layout."""
    original = native_bound.NativeBound.__call__
    second = native_bound.NativeBound(library)

    def call(owner, *args, **kwargs):
        before = owner.counts["fallback_unsupported"]
        fallback = owner.original

        def try_wider(*values, **options):
            if owner.counts["fallback_unsupported"] == before + 1:
                second.min_rcond = owner.min_rcond
                return original(second, *values, **options)
            return fallback(*values, **options)

        with patch.object(owner, "original", try_wider):
            return original(owner, *args, **kwargs)

    try:
        with patch.object(native_bound.NativeBound, "__call__", call):
            yield second.counts
    finally:
        second.clear()
