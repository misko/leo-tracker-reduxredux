import ctypes as ct
from pathlib import Path
import subprocess

import numpy as np
import pytest


@pytest.fixture()
def lower_bound(tmp_path):
    source = tmp_path / "test.c"
    binary = tmp_path / "test.so"
    include = Path(__file__).resolve().parents[2] / "reports/ALGO08/v3/conditioned_factor.inc"
    source.write_text(
        "#include <stdint.h>\n#include <string.h>\n#include <math.h>\n"
        "typedef int32_t (*pocon_fn)(int32_t,char,int32_t,const double*,int32_t,double,double*);\n"
        f'#include "{include}"\n'
        "static int mocked_reject;\n"
        "static int32_t mocked(int32_t l,char u,int32_t n,const double *a,int32_t m,double an,double *cond) {\n"
        "    (void)l; (void)u; (void)n; (void)a; (void)m; (void)an;"
        " *cond=mocked_reject ? 0. : 1.; return 0;\n}\n"
        "int probe(int n,const double *root,double norm,double threshold,int reject) {\n"
        "    mocked_reject=reject; return schur_condition(mocked,n,root,norm,threshold);\n}\n"
    )
    subprocess.run(["cc", "-std=c11", "-O3", "-shared", "-fPIC", "-ffp-contract=off",
                    "-DLEO_CONDITION_CERT=1",
                    str(source), "-lm", "-o", str(binary)], check=True, timeout=20)
    library = ct.CDLL(str(binary))
    function = library.nb_schur_reciprocal_floor
    function.argtypes = [ct.c_int, ct.c_void_p, ct.c_double]
    function.restype = ct.c_double

    def evaluate(root, norm=None):
        n = len(root)
        lower = np.asfortranarray(root, dtype=np.float64)
        if norm is None:
            norm = np.linalg.norm(lower @ lower.T, ord=1)
        return function(n, lower.ctypes.data, norm)

    probe = library.probe
    probe.argtypes = [ct.c_int, ct.c_void_p, ct.c_double, ct.c_double, ct.c_int]
    probe.restype = ct.c_int

    def gate(root):
        lower = np.asfortranarray(root, dtype=np.float64)
        return probe(len(lower), lower.ctypes.data, 1., 1e-12, 1)

    return evaluate, gate


@pytest.mark.parametrize("n", [1, 3, 15, 40])
def test_comparison_bound_is_conservative_on_ordered_lower_factor(lower_bound, n):
    evaluate, _ = lower_bound
    rng = np.random.default_rng(17+n)
    for trial in range(12):
        root = np.tril(rng.normal(0, .015*(trial+1), size=(n, n)), k=-1)
        root += np.diag(1+rng.uniform(0., 1., size=n))
        exact = 1/np.linalg.cond(root @ root.T, p=1)
        assert 0 < evaluate(root) <= exact


def test_degenerate_or_ill_conditioned_factors_do_not_clear_the_gate(lower_bound):
    evaluate, gate = lower_bound
    assert evaluate(np.diag([1., 0.]), 1.) == 0.
    assert evaluate(np.array([[1., 0.], [float("nan"), 1.]]), 1.) == 0.
    assert evaluate(np.eye(2), float("inf")) == 0.
    assert evaluate(np.diag([1., 1e-7])) <= 8e-12
    assert gate(np.diag([1., 1e-7])) == 1
    assert gate(np.eye(2)) == 0
