"""Warm the native Gamma updates within one fully specified marginal model."""

from collections import Counter, OrderedDict
from contextlib import contextmanager
import ctypes as ct
from pathlib import Path
import subprocess
from time import process_time
from unittest.mock import patch

from leo.analysis.localization_v3 import marginal
from leo.analysis.localization_v4 import native_bound
from tools.pipeline_eval.variants.algo08_bound_statistics import SOURCE_SHA256, replace


def build(output):
    source = native_bound.SOURCE
    if native_bound.digest(source) != SOURCE_SHA256:
        raise ValueError("Incompatible native bound source")
    text = source.read_text()
    text = replace(text, "/* All work belongs", Path(__file__).with_suffix(".h").read_text()
                   + "\n/* All work belongs")
    text = replace(text, "int nb_run(", "int nb_run_warm(")
    text = replace(text, " int *updates,double *returned_rates) {", """
 int *updates,double *returned_rates,WarmRates *warm,int *warm_hit) {
    *warm_hit=0;
    """)
    text = replace(text, "    double change=INFINITY,logdet=0.;int performed=0;", """
    *warm_hit=matching_rates(warm,l,t,alpha,pa,beta0,pb0,v0);
    if (*warm_hit) {
        memcpy(rate,warm->noise_rate,k*sizeof(double));
        memcpy(prate,warm->prior_rate,t*sizeof(double));
    }
    double change=INFINITY,logdet=0.;int performed=0;
    """)
    text = replace(text, "done:\n    free(work);return code;", """
    if (warm && code==NB_OK && change<1e-5) {
        cache_rates(warm,l,t,alpha,pa,beta0,pb0,v0,rate,prate);
    } else if (warm) {
        warm->valid=0;
    }
done:
    if (warm && code!=NB_OK) warm->valid=0;
    free(work);return code;
    """)
    output = Path(output)
    generated = output.with_suffix(".c")
    generated.write_text(text)
    subprocess.run(["cc", *native_bound.FLAGS, "-Wall", "-Wextra", "-Werror", str(generated),
                    "-lm", "-o", str(output)], check=True, timeout=30)


class MeasuredBound:
    def __init__(self, original, metrics, library, *, accelerate):
        self.original, self.metrics = original, metrics
        self.pending = self.active = None
        self.states = OrderedDict()
        self.cold = original.run
        self.warm = self.accelerated = None
        if accelerate:
            self.accelerated = library.nb_run
            self.accelerated.argtypes = self.cold.argtypes
            self.accelerated.restype = self.cold.restype
        elif library is not None:
            state_size = library.nb_warm_size
            state_size.argtypes, state_size.restype = [], ct.c_size_t
            self.state_size = state_size()
            self.warm = library.nb_run_warm
            self.warm.argtypes = self.cold.argtypes + [ct.c_void_p, ct.POINTER(ct.c_int)]
            self.warm.restype = self.cold.restype
        original.run = self.run

    def note_model(self, model, geometry):
        if self.warm is not None:
            self.pending = model, geometry

    def __call__(self, *args, **kwargs):
        candidate, self.pending = self.pending, None
        if candidate is not None:
            model, geometry = candidate
            mask = model.keep.tobytes()
            old = self.states.pop(model, None)
            if old is None or old[0] is not geometry or old[1] != mask:
                old = geometry, mask, ct.create_string_buffer(self.state_size)
            self.states[model] = old
            if len(self.states) > 8:
                self.states.popitem(last=False)
            self.active = old[2]
        try:
            return self.original(*args, **kwargs)
        finally:
            self.active = None

    def run(self, *args):
        start = process_time()
        warmed = ct.c_int()
        updates = ct.cast(args[-2], ct.POINTER(ct.c_int))
        scalars = ct.cast(args[-3], ct.POINTER(ct.c_double))
        if self.accelerated is not None:
            error = self.accelerated(*args)
            if error or scalars[1] >= 1e-5:
                self.metrics["acceleration_retries"] += 1
                self.metrics["retry_updates"] += updates[0]
                error = self.cold(*args)
        elif self.active is None:
            error = self.cold(*args)
        else:
            error = self.warm(*args, self.active, ct.byref(warmed))
            if warmed.value and (error or scalars[1] >= 1e-5):
                self.metrics["warm_retries"] += 1
                self.metrics["retry_updates"] += updates[0]
                error = self.cold(*args)
        self.metrics["kernel_cpu_s"] += process_time() - start
        self.metrics["kernel_calls"] += 1
        self.metrics["warm_calls"] += warmed.value
        if not error:
            self.metrics["updates"] += updates[0]
            self.metrics["budget_hits"] += int(scalars[1] >= 1e-5)
        return error


@contextmanager
def binding(port, library=None, *, accelerate=False):
    """Retain release validation and time the selected native update schedule."""
    candidate = None if library is None else ct.CDLL(str(library))
    original, geometry = port.NativeBound, marginal._phase_geometry
    metrics, instances = Counter(), []

    def backend(*args, **kwargs):
        bound = original(*args, **kwargs)
        instances.append(bound)
        return MeasuredBound(bound, metrics, candidate, accelerate=accelerate)

    def phase(model, point):
        result = geometry(model, point)
        bound = model.scan.bound
        if isinstance(bound, MeasuredBound):
            bound.note_model(model, model._fixed_phase_geometry_cache)
        return result

    if accelerate:
        counts = candidate.nb_accel_counts
        counts.argtypes, counts.restype = [ct.POINTER(ct.c_uint64)], None
        before = (ct.c_uint64 * 2)()
        counts(before)
    try:
        with patch.object(port, "NativeBound", backend), patch.object(marginal, "_phase_geometry", phase):
            yield metrics
    finally:
        if accelerate:
            after = (ct.c_uint64 * 2)()
            counts(after)
            for name, old, new in zip(("extrapolations", "rejected_extrapolations"), before, after,
                                      strict=True):
                metrics[name] = new - old
        for bound in instances:
            metrics.update(bound.counts)
            bound.clear()
