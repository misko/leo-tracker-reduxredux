"""Default-off profiled Gamma for the checked posterior factor in a research grid."""

from contextlib import contextmanager
import ctypes as ct
from hashlib import sha256
from pathlib import Path
import subprocess
from unittest.mock import patch

import numpy as np

from tools.pipeline_eval.variants import algo08_posterior_handoff as handoff


EXPORT = """int *updates,double *returned_rates,int export_width,double *lower,int32_t *order,int *exported) {
    *exported=0;"""
FULL_CONDITION_GUARD = """if(p && (!isfinite(inverse_norm) || inverse_norm<=0 || 1./full_norm/inverse_norm<min_rcond)) {
            code=NB_CONDITION;goto done;"""
STOCK_PREFIX_REFUSAL = -2
ILL_CONDITIONED = handoff.native_bound.STATUS.index("ill_conditioned")
STOCK_POSTERIOR_SHA256 = "5a6e5627844a07a3bf2291b248520949f8b10e41d0421b6d6dc0da2b19d430b5"


def export_source(*, prefix_proof=False):
    from tools.pipeline_eval.variants import algo08_profiled_gamma as gamma

    source, _ = gamma.profiled_source().split("\nint nb_profiled_gamma(", 1)
    header = Path(handoff.__file__).with_suffix(".h").read_text()
    source = handoff.replace(source, "/* All work belongs", header + "\n/* All work belongs")
    source = handoff.replace(source, "static int gamma_run(", "int nb_profiled_posterior(")
    source = handoff.replace(source, "int *updates,double *returned_rates) {", EXPORT)
    if prefix_proof:
        # Both modes still use the ordinary recurrence at iteration < GAMMA_WARMUP.
        # Carry this particular refusal as evidence, never as a usable factor.
        proof = f"if(iteration<GAMMA_WARMUP) *exported={STOCK_PREFIX_REFUSAL};\n            code=NB_CONDITION;"
        source = handoff.replace(source, FULL_CONDITION_GUARD,
                                 FULL_CONDITION_GUARD.replace("code=NB_CONDITION;", proof))
    return handoff.replace(source, "        if(final)break;", """        if(final) {
            if (p==export_width && lower && order)
                *exported=export_posterior(l,d,e,root,precision,lower,order);
            break;
        }""")


def build(output, *, prefix_proof=False, source=None):
    output = Path(output)
    with output.with_suffix(".c").open("x") as generated:
        generated.write(export_source(prefix_proof=prefix_proof) if source is None else source)
    subprocess.run(["cc", *handoff.native_bound.FLAGS, "-Wall", "-Wextra", "-Werror",
                    str(output.with_suffix(".c")), "-lm", "-o", str(output)],
                   check=True, timeout=30)
    return sha256(output.read_bytes()).hexdigest()


def exported(capture):
    """Check the returned factor before committing the changed grid arithmetic."""
    return (capture.exported.value == 1 and np.isfinite(capture.lower).all()
            and np.all(capture.lower.diagonal() > 0)
            and np.array_equal(np.sort(capture.order), np.arange(capture.width)))


def checked_symbol(path, digest, name):
    path = Path(path)
    if sha256(path.read_bytes()).hexdigest() != digest:
        raise ValueError("Unexpected posterior binary")
    return getattr(ct.CDLL(str(path)), name)


def same_stock_refusal(proven, stock, status, capture):
    return (proven is not None and status == ILL_CONDITIONED
            and capture.exported.value == STOCK_PREFIX_REFUSAL
            and ct.cast(proven, ct.c_void_p).value == ct.cast(stock, ct.c_void_p).value)


@contextmanager
def profiled_exports(binary, expected_sha256, audit, *, proof_stock=None):
    """Attach before checked handoff during a research-only solve or point replay."""
    try:
        changed = checked_symbol(binary, expected_sha256, "nb_profiled_posterior")
    except (AttributeError, OSError, ValueError):
        audit["unsupported_library"] += 1
        yield
        return
    proven = None
    if proof_stock is not None:
        try:
            proven = checked_symbol(proof_stock, STOCK_POSTERIOR_SHA256, "nb_run_posterior")
        except (AttributeError, OSError, ValueError):
            audit["proof_stock_refused"] += 1
    ordinary = handoff.Capture.run

    def calculate(capture, owner, stock, args):
        changed.argtypes, changed.restype = stock.argtypes, stock.restype
        audit["attempted"] += 1
        status = ordinary(capture, owner, changed, args)
        if same_stock_refusal(proven, stock, status, capture):
            capture.exported.value = 0
            audit["certified_stock_refusal"] += 1
            return status
        if status or not exported(capture):
            audit["stock_replay"] += 1
            return ordinary(capture, owner, stock, args)
        audit["profiled_completed"] += 1
        return status

    with patch.object(handoff.Capture, "run", calculate):
        yield


@contextmanager
def profiled_grid(binary, expected_sha256, audit, *, proof=False):
    """Bind the proof to the stock asset received by the normal grid port."""
    original = handoff.grid_handoff

    @contextmanager
    def grid(port, library, in_grid):
        with original(port, library, in_grid) as counts:
            with profiled_exports(binary, expected_sha256, audit, proof_stock=library if proof else None):
                yield counts

    with patch.object(handoff, "grid_handoff", grid):
        yield
