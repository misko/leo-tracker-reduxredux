"""Reuse unchanged numeric track Gram entries in the native ALGO08v2 fit."""

import argparse
import ctypes as ct
import subprocess
from contextlib import contextmanager
from pathlib import Path
from time import process_time
from unittest.mock import patch

from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants.algo08_bound_statistics import SOURCE_SHA256, replace

COUNTERS = (
    "gram_calls", "gram_cpu_ns", "gram_cold", "gram_reused", "gram_fallback",
    "original_products", "replayed_products", "reused_group_columns",
    "assembly_calls", "assembly_cpu_ns", "assembly_mapped",
)


def build(output):
    original = native_bound.SOURCE
    if native_bound.digest(original) != SOURCE_SHA256:
        raise ValueError("Incompatible native bound source")
    source = "#define _POSIX_C_SOURCE 200809L\n" + original.read_text()
    source = replace(source, "} Layout;", """
    struct GramReuse *gram_reuse;
    struct PosteriorMap *posterior;
} Layout;
""" + Path(__file__).with_suffix(".h").read_text())
    source = replace(source, "free(l->width);free(l);",
                     "free(l->width);gram_free(l->gram_reuse);posterior_free(l->posterior);free(l);")
    source = replace(source, "free(active);free(support);*status=NB_OK;return l;", """
    l->gram_reuse=gram_allocate(l,groups);
    l->posterior=posterior_map(l);
    free(active);free(support);*status=NB_OK;return l;
""")
    start = "    /* Current group Gram/RHS, fused over actual active columns. */\n"
    stop = "    for(int g=0;g<k;g++)rate[g]=alpha[g];"
    source = replace(source, start, """
    uint64_t gram_started = gram_clock();
    ++gram_counts[gram_calls];
    int reused = atomic_load_explicit(&gram_reuse_enabled, memory_order_relaxed) == 1;
    if (!reused || !cache_gram(l,y,u,sigma,groups,matrix,rhs)) {
    if (reused) ++gram_counts[gram_fallback];
""" + start)
    source = replace(source, stop, """
    }
    gram_counts[gram_cpu_ns] += gram_clock() - gram_started;
""" + stop)
    assembly = (
        "        for(int g=0;g<k;g++) {\n"
        "            int off=l->offset[g],q=l->offset[g+1]-off,nd=l->width[g];"
        "double w=power[g]*weight[g];"
    )
    condition = "        /* Exact full-Gram 1-norm, before destructive Schur elimination. */"
    source = replace(source, assembly, """
        uint64_t assembly_started = gram_clock();
        ++assembled;
        if (l->posterior) {
            ++mapped;
            assemble_posterior(l,matrix,rhs,power,weight,precision,a,e,d,bg,b);
        } else {
""" + assembly)
    source = replace(source, condition, """
        }
        assembly_time += gram_clock() - assembly_started;
""" + condition)
    source = replace(source, "    for(int iteration=0;iteration<=budget;iteration++) {", """
    uint64_t assembled = 0, mapped = 0, assembly_time = 0;
    for(int iteration=0;iteration<=budget;iteration++) {
""")
    source = replace(source, "done:\n    free(work);return code;", """
done:
    gram_counts[assembly_calls] += assembled;
    gram_counts[assembly_cpu_ns] += assembly_time;
    gram_counts[assembly_mapped] += mapped;
    free(work);return code;
""")
    output = Path(output)
    generated = output.with_suffix(".c")
    generated.write_text(source)
    subprocess.run(["cc", *native_bound.FLAGS, "-Wall", "-Wextra", "-Werror", str(generated),
                    "-lm", "-o", str(output)], check=True, timeout=30)


@contextmanager
def measured_backend(port, binary, *, mode):
    library = ct.CDLL(str(binary))
    configure, read = library.nb_configure_fixed_gram, library.nb_fixed_gram_counts
    configure.argtypes, configure.restype = [ct.c_int], None
    read.argtypes, read.restype = [ct.POINTER(ct.c_uint64)], None

    def counters():
        values = (ct.c_uint64 * len(COUNTERS))()
        read(values)
        return dict(zip(COUNTERS, values, strict=True))

    original, instances, initial = port.NativeBound, [], counters()
    receipt = dict(kernel_cpu_s=0.0, kernel_calls=0)

    def create(*args, **kwargs):
        bound = original(*args, **kwargs)
        for attr, symbol in (("run", "nb_run"), ("layout", "nb_layout"), ("free", "nb_free")):
            prior = getattr(bound, attr)
            method = getattr(library, symbol)
            method.argtypes, method.restype = prior.argtypes, prior.restype
            setattr(bound, attr, method)
        operation = bound.run

        def timed(*values):
            start = process_time()
            try:
                return operation(*values)
            finally:
                receipt["kernel_calls"] += 1
                receipt["kernel_cpu_s"] += process_time() - start

        bound.run = timed
        instances.append(bound)
        return bound

    configure({"control": 0, "fixed": 1, "mapped": 2}[mode])
    try:
        with patch.object(port, "NativeBound", create):
            yield receipt
    finally:
        for bound in instances:
            for key, value in bound.counts.items():
                receipt[key] = receipt.get(key, 0) + value
            bound.clear()
        receipt.update({k: v - initial[k] for k, v in counters().items()})
        configure(False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)
