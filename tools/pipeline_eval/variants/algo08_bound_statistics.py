"""Build and bind an experimental group-statistics variational kernel."""

import ctypes
from contextlib import contextmanager
from pathlib import Path
import subprocess
from unittest.mock import patch

from leo.analysis.localization_v4 import native_bound


SOURCE_SHA256 = "40888d6143f385c2146e5e2cb28ea99a96b2f1bb791fab4c22b5afaaa2b3a23b"
ENERGY = Path(__file__).with_suffix(".h")


def replace(source, anchor, replacement):
    if source.count(anchor) != 1:
        raise ValueError("Expected exactly one qualified native source anchor")
    return source.replace(anchor, replacement)


def build(output):
    """Specialize the release kernel at explicit contraction sites."""
    source_path = native_bound.SOURCE
    if native_bound.digest(source_path) != SOURCE_SHA256:
        raise ValueError("Incompatible native bound source")
    source = source_path.read_text()
    source = replace(source, "/* All work belongs", ENERGY.read_text() + "\n/* All work belongs")
    source = replace(source, "13*(size_t)k", "17*(size_t)k+l->total")
    source = replace(source, "double *row_f=row+(l->qmax?l->qmax:1);", """
    double *row_f=row+(l->qmax?l->qmax:1);
    double *responses=row_f+sz,*row_counts=responses+k;
    double *anchor=row_counts+k,*replay=anchor+k,*shift_rhs=replay+k;
    """)
    source = replace(source, "double r=y[i]/sigma[i];", """
        double r=y[i]/sigma[i];
        int pivot=l->width[g] ? l->private_cols[2*g] : -1;
        double pivot_value=pivot>=0 ? u[(size_t)i*p+pivot] : 0.;
        if (row_counts[g]==0. && pivot_value!=0.) anchor[g]=y[i]/pivot_value;
        double shifted=(y[i]-anchor[g]*pivot_value)/sigma[i];
        responses[g]+=shifted*shifted;
        row_counts[g]+=1.;
    """)
    source = replace(source, "rhs[off+j]+=row[j]*r;", """
            rhs[off+j]+=row[j]*r;
            shift_rhs[off+j]+=row[j]*shifted;
    """)
    start = "        memset(energy,0,k*sizeof(double));\n        for(int i=0;i<n;i++) {"
    stop = "        if(final)break;\n"
    if source.count(start) != 1 or source.count(stop) != 1:
        raise ValueError("Changed native residual contract")
    first, last = source.index(start), source.index(stop)
    rows = source[first:last].split("        for(int i=0;i<n;i++) {", 1)[1]
    rows = replace(rows, "int g=(int)groups[i];double val=0.;", """
            int g=(int)groups[i];
            if (!final && !replay[g]) continue;
            double val=0.;
    """)
    source = source[:first] + """
        bstats_calls++;
        if (final) memset(energy,0,k*sizeof(double));
        int need_rows=final || group_energy(l, matrix, shift_rhs, responses, row_counts,
                                           anchor, mean, row, energy, replay)>0;
        if (need_rows) for (int i=0;i<n;i++) {
    """ + rows + source[last:]
    output = Path(output)
    generated = output.with_suffix(".c")
    generated.write_text(source)
    subprocess.run(["cc", *native_bound.FLAGS, str(generated), "-lm", "-o", str(output)],
                   check=True, timeout=30)


@contextmanager
def group_statistics(algo08_position, library):
    """Keep the deployed ABI validation and change the numerical kernel in a worker."""
    candidate = ctypes.CDLL(str(library))
    backend = algo08_position.NativeBound
    instances = []
    get = candidate.group_statistics_counts
    get.argtypes, get.restype = [ctypes.POINTER(ctypes.c_uint64)], None

    def read_counts():
        values = (ctypes.c_uint64 * 4)()
        get(values)
        return values

    def factory(*args, **kwargs):
        bound = backend(*args, **kwargs)
        for attr, symbol in (("run", "nb_run"), ("layout", "nb_layout"), ("free", "nb_free")):
            old = getattr(bound, attr)
            operation = getattr(candidate, symbol)
            operation.argtypes, operation.restype = old.argtypes, old.restype
            setattr(bound, attr, operation)
        instances.append(bound)
        return bound

    stats, before = {}, read_counts()
    try:
        with patch.object(algo08_position, "NativeBound", factory):
            yield stats
    finally:
        values = [new - old for new, old in zip(read_counts(), before, strict=True)]
        stats.update(zip(("updates_including_final", "group_fallbacks", "rows_avoided",
                          "nonterminal_group_updates"), values, strict=True))
        for bound in instances:
            for key, value in bound.counts.items():
                stats[key] = stats.get(key, 0) + value
            bound.clear()
