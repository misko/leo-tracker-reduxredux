import ctypes as ct
from pathlib import Path
import subprocess

import pytest


NATIVE = Path(__file__).resolve().parents[2] / "reports" / "ALGO08" / "v3"


@pytest.mark.parametrize("matrix_size", [5, 14])
def test_jacobi_columns_preserve_scalar_rotations(tmp_path, matrix_size):
    wrapper = tmp_path / "rotate.c"
    wrapper.write_text("""
#include <complex.h>
#include <math.h>
#include <string.h>
enum { count = MATRIX_SIZE };
#include "receiver_jacobi_columns.inc"

static void original(double complex covariance[count][count], double complex axis[count][count],
                     int p, int q, double cosine, double complex sine)
{
    for (int k = 0; k < count; ++k) {
        if (k == p || k == q) continue;
        double complex x = covariance[k][p], y = covariance[k][q];
        covariance[k][p] = cosine * x - conj(sine) * y;
        covariance[p][k] = conj(covariance[k][p]);
        covariance[k][q] = sine * x + cosine * y;
        covariance[q][k] = conj(covariance[k][q]);
    }
    for (int k = 0; k < count; ++k) {
        double complex x = axis[k][p], y = axis[k][q];
        axis[k][p] = cosine * x - conj(sine) * y;
        axis[k][q] = sine * x + cosine * y;
    }
}

int check(int vector_mode)
{
    double complex covariance[count][count], axis[count][count];
    double complex equivalent[count][count], columns[count][count];
    for (int p = 0; p < count; ++p) {
        for (int q = p; q < count; ++q) {
            double real = (1 + p + 3 * q) * 0.13;
            double imag = p == q ? 0 : (1 + 5 * p - q) * 0.29;
            covariance[p][q] = CMPLX(real, imag);
            covariance[q][p] = conj(covariance[p][q]);
        }
        for (int q = 0; q < count; ++q)
            axis[p][q] = CMPLX((1 + 2 * p + q) * 0.071, (2 + p - 3 * q) * 0.09);
    }
    memcpy(equivalent, covariance, sizeof(equivalent));
    memcpy(columns, axis, sizeof(columns));
    int active = receiver_jacobi_columns_mode(vector_mode, 0);
    if (jacobi_columns_eligible(equivalent) != (active == 1)) return 1;
    equivalent[0][0] = CMPLX(NAN, 0);
    if (jacobi_columns_eligible(equivalent)) return 2;
    equivalent[0][0] = covariance[0][0];
    if (active == 1) jacobi_restore_axis(columns);

    const int pivots[][2] = {{0, 1}, {1, 4}, {0, count - 1}, {2, 3}, {1, count - 2}};
    for (unsigned i = 0; i < sizeof(pivots) / sizeof(pivots[0]); ++i) {
        int p = pivots[i][0], q = pivots[i][1];
        double cosine = 0.731 + 0.007 * i;
        double complex sine = CMPLX(0.327 - 0.017 * i, -0.281 + 0.013 * i);
        original(covariance, axis, p, q, cosine, sine);
        if (active == 1)
            jacobi_rotate_columns(equivalent, columns, p, q, cosine, sine);
        else
            original(equivalent, columns, p, q, cosine, sine);
    }
    if (active == 1) jacobi_restore_axis(columns);
    if (memcmp(covariance, equivalent, sizeof(equivalent))) return 3;
    if (memcmp(axis, columns, sizeof(columns))) return 4;
    return 0;
}
""")
    library = tmp_path / "rotate.so"
    subprocess.run(
        [
            "cc", "-O3", "-fPIC", "-shared", "-ffp-contract=off", "-fno-strict-aliasing",
            "-D_POSIX_C_SOURCE=200809L", f"-DMATRIX_SIZE={matrix_size}", "-I", NATIVE,
            wrapper, "-o", library,
        ],
        check=True,
    )
    check = ct.CDLL(str(library)).check
    check.argtypes = [ct.c_int]
    check.restype = ct.c_int
    assert check(0) == 0
    assert check(1) == 0
