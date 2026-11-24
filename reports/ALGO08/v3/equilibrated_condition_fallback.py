"""Checked numerical experiments at the original dense/fallback boundary."""

from collections import Counter, OrderedDict
from hashlib import sha256
from inspect import getsource
from pathlib import Path
from textwrap import dedent

import numpy as np
from scipy.linalg.lapack import dgetrf, dgetrs, dpotrf, dpotri, dpotrs


DENSE_SOURCE = "c906a5992ca3428c29b5c44326264549e18dc4206653b3d6f2fd12b48638607e"
DISPATCH_SOURCE = "fa7b67e0e539be9971ee1a530c2d1d941c7940701d40dae7cc6744cbc20de6a2"
STOP = 1e-5
MARGIN = 5e-10


class UncertainArithmetic(ArithmeticError):
    """The alternative could not certify this original numerical state."""


def infnorm(a):
    return float(np.linalg.norm(a, ord=np.inf))


def same_source(original, expected):
    path = Path(original.__code__.co_filename)
    if sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError(f"Unreviewed installed source: {path}")
    return path


def positive_diagonal(gram):
    diagonal = np.diag(gram)
    if not np.isfinite(diagonal).all() or np.any(diagonal <= 0):
        raise UncertainArithmetic("invalid diagonal")
    _, exponent = np.frexp(diagonal)
    return -(exponent // 2)


def equilibrated(gram, rhs, precision, covariance):
    exponent = positive_diagonal(gram)
    scaling = exponent[:, None] + exponent
    balanced = np.ldexp(gram, scaling)
    balanced_rhs = np.ldexp(rhs, exponent)
    if (not np.isfinite(balanced).all() or not np.isfinite(balanced_rhs).all()
            or not np.array_equal(np.ldexp(balanced, -scaling), gram)
            or not np.array_equal(np.ldexp(balanced_rhs, -exponent), rhs)):
        raise UncertainArithmetic("nonexact scaling")
    root, info = dpotrf(balanced, lower=1, clean=1)
    if info:
        raise UncertainArithmetic("nonpositive factor")
    fit, info = dpotrs(root, balanced_rhs, lower=1)
    if info:
        raise UncertainArithmetic("mean solve failed")
    mean = np.ldexp(fit, exponent)
    logdet = float(2 * (np.log(np.diag(root)).sum() - np.log(2.) * exponent.sum()))
    if not np.isfinite(mean).all() or not np.isfinite(logdet):
        raise UncertainArithmetic("nonfinite posterior")

    norm = infnorm(gram)
    unscaled_root = np.ldexp(root, -exponent[:, None])
    factor_error = infnorm(gram - unscaled_root @ unscaled_root.T) / norm
    denominator = abs(gram) @ abs(mean) + abs(rhs)
    defect = abs(gram @ mean - rhs)
    if np.any((denominator == 0) & (defect != 0)):
        raise UncertainArithmetic("mean defect on an empty coordinate")
    mean_error = float(np.max(np.divide(defect, denominator, out=np.zeros_like(defect), where=denominator > 0)))
    errors = dict(factor_error=factor_error, mean_error=mean_error,
                  diagonal_rcond_upper=float(np.min(np.diag(gram))) / norm)
    cov = None
    if covariance:
        lower, code = dpotri(root, lower=1)
        if code:
            raise UncertainArithmetic("covariance solve failed")
        cov = np.ldexp(np.tril(lower) + np.tril(lower, -1).T, scaling)
        defect = gram @ cov - np.eye(len(precision))
        covariance_error = infnorm(defect) / (norm * infnorm(cov) + 1)
        backward = np.ldexp(defect, exponent[:, None] - exponent)
        if (not np.isfinite(cov).all() or np.any(np.diag(cov) <= 0)
                or not np.isfinite(backward).all() or infnorm(backward) > 1e-6):
            raise UncertainArithmetic("covariance error")
        errors.update(covariance_error=covariance_error, scaled_inverse_defect=infnorm(backward),
                      unscaled_reciprocal_condition=1 / (norm * infnorm(cov)))
    tolerance = 128 * np.finfo(np.float64).eps * len(precision)
    checks = [value for name, value in errors.items() if name.endswith("_error")]
    if not all(np.isfinite(value) and value <= tolerance for value in checks):
        raise UncertainArithmetic("unscaled backward error")
    volume = None if covariance else max(0., logdet - np.log(precision).sum())
    return (mean, cov, volume), errors, logdet


def original_factor(gram, rhs, covariance):
    """Independent reference using each original triangular LU operation."""
    size = len(rhs)
    root, code = dpotrf(gram, lower=1, clean=1)
    if code:
        raise ValueError("Original dense Cholesky rejected the certified matrix")
    contiguous = np.ascontiguousarray(root)
    lu, pivots, code = dgetrf(contiguous)
    first, c1 = dgetrs(lu, pivots, rhs)
    mean, c2 = dgetrs(contiguous.T, np.arange(size, dtype=np.int32), first)
    if code or c1 or c2:
        raise ValueError("Unexpected original dense mean failure")
    cov = None
    if covariance:
        inv, code = dgetrs(lu, pivots, np.eye(size, order="F"), overwrite_b=1)
        if code:
            raise ValueError("Unexpected original dense covariance failure")
        cov = inv.T @ inv
    return mean, cov, float(2 * np.log(np.diag(root)).sum())


class DenseAlternative:
    def __init__(self, original, *, verify=False):
        path = same_source(original, DENSE_SOURCE)
        self.original = original
        self.verify = verify
        self.counts = Counter()
        self.error = {}
        self.events = []
        source = getsource(original)
        entry = "        root = _cholesky(gram)\n"
        convergence = "        history.append(change)\n"
        if source.count(entry) != 1 or source.count(convergence) != 1:
            raise ValueError("Dense dual-factor boundary changed")
        source = source.replace(entry, "        if width:\n            return _factor(gram, rhs, precision, covariance)\n" + entry)
        source = source.replace(convergence, "        _stop(change)\n" + convergence)
        scope = dict(original.__globals__, _factor=self.factor, _stop=self.stop)
        exec(compile(source, str(path), "exec"), scope)
        self.candidate = scope[original.__name__]

    def factor(self, gram, rhs, precision, covariance):
        result, errors, logdet = equilibrated(gram, rhs, precision, covariance)
        self.counts["factor"] += 1
        if self.verify:
            mean, cov, expected_logdet = original_factor(gram, rhs, covariance)
            errors.update(mean_difference=float(np.max(abs(mean - result[0]))),
                          covariance_difference=float(np.max(abs(cov - result[1]))) if covariance else 0.,
                          logdet_difference=abs(expected_logdet - logdet))
            if max(value for name, value in errors.items() if name.endswith("_difference")) > 1e-6:
                raise UncertainArithmetic("released dense operand comparison")
            self.events.append(errors)
        return result

    def stop(self, change):
        if not np.isfinite(change) or abs(change - STOP) <= MARGIN:
            raise UncertainArithmetic("original convergence boundary")

    def __call__(self, *args, **kwargs):
        self.counts["entered"] += 1
        try:
            result = self.candidate(*args, **kwargs)
            if not all(np.isfinite(value).all() for value in result.values()):
                raise UncertainArithmetic("nonfinite final state")
        except UncertainArithmetic as exc:
            self.counts["retry_original"] += 1
            self.error[str(exc)] = self.error.get(str(exc), 0) + 1
            return self.original(*args, **kwargs)
        self.counts["accepted_dense_alternative"] += 1
        return result


def exact_unsupported_layout(original, *, size=4):
    """Remember a deterministic NB_UNSUPPORTED layout on only this bound owner."""
    path = same_source(original.__func__, DISPATCH_SOURCE)
    source = dedent(getsource(original))
    lookup = "    owned = False\n"
    decision = "        if not layout:\n"
    if source.count(lookup) != 1 or source.count(decision) != 1:
        raise ValueError("Original cache/validation boundary changed")
    memo = OrderedDict()
    hits = Counter()

    def recall(key):
        if key in memo:
            memo.move_to_end(key)
            hits["hits"] += 1
            return True
        return False

    def remember(key, status):
        if status == 1:
            memo[key] = None
            if len(memo) > size:
                memo.popitem(last=False)
            hits["remembered"] += 1

    source = source.replace(lookup, "    if _recall(key):\n        self.counts['fallback_unsupported'] += 1\n"
                            "        return self.original(*args,**kwargs)\n" + lookup)
    source = source.replace(decision, decision + "            _remember(key, code.value)\n")
    scope = dict(original.__func__.__globals__, _recall=recall, _remember=remember)
    exec(compile(source, str(path), "exec"), scope)
    return scope[original.__name__].__get__(original.__self__, type(original.__self__)), hits
