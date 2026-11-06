"""Exact small-batch solve/determinant reuse with a serial NumPy fallback."""

import ctypes as ct
from functools import lru_cache
from pathlib import Path

import numpy as np


@lru_cache(maxsize=1)
def _backend():
    try:
        from leo.analysis import _joint_lu
    except ImportError:
        return None
    libraries = list((Path(np.__file__).resolve().parent.parent / 'numpy.libs').glob(
        'libscipy_openblas64_*.so'))
    if len(libraries) != 1:
        return None
    try:
        library, lapack = ct.CDLL(_joint_lu.__file__), ct.CDLL(str(libraries[0]))
        configuration = lapack.scipy_openblas_get_config64_
        configuration.argtypes, configuration.restype = [], ct.c_char_p
        if b'USE64BITINT' not in (configuration() or b''):
            return None
        address = ct.cast(lapack.scipy_dgesv_64_, ct.c_void_p)
        native = library.batch_lu
    except (OSError, AttributeError):
        return None
    native.argtypes = [ct.c_void_p] * 6 + [ct.c_size_t, ct.c_int]
    native.restype = ct.c_int
    # Keep both libraries alive for the entire lifetime of their C pointers.
    return library, lapack, native, address


def solve_and_slogdet(a, b):
    """Share DGESV's LU only for supported finite float64 batch inputs.

    Unsupported providers, shapes and types retain the original NumPy calls.
    There is no runtime compiler and no alternate LAPACK provider substitution.
    """
    backend = _backend()
    if (backend is None or not isinstance(a, np.ndarray) or not isinstance(b, np.ndarray)
            or a.dtype != np.float64 or b.dtype != np.float64 or a.ndim < 2
            or not 1 <= a.shape[-1] <= 32 or a.shape[-1] != a.shape[-2]
            or b.shape != a.shape[:-1] or not np.isfinite(a).all()
            or not np.isfinite(b).all()):
        coefficient = np.linalg.solve(a, np.asarray(b)[..., None])[..., 0]
        sign, logdet = np.linalg.slogdet(a)
        return coefficient, sign, logdet
    a, b = np.ascontiguousarray(a), np.ascontiguousarray(b)
    coefficient = np.empty_like(b)
    sign, logdet = (np.empty(b.shape[:-1]) for _ in range(2))
    _, _, native, address = backend
    status = native(address, *(v.ctypes.data_as(ct.c_void_p)
                              for v in (a, b, coefficient, sign, logdet)), sign.size, a.shape[-1])
    if status > 0:
        raise np.linalg.LinAlgError('Singular matrix')
    if status < 0:
        raise RuntimeError(f'Private LU backend failed with status {status}')
    return coefficient, sign, logdet
