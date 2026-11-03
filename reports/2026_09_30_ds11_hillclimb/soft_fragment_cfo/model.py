"""Training-frozen common-identity pairs with optional soft CFO coupling.

This is a profile likelihood.  Candidate weights are conditional retained-bank
weights, not calibrated probabilities of physical identity.
"""
from __future__ import annotations

import hashlib
import itertools
import json
import math
import sys
from pathlib import Path

import numpy as np
from scipy.optimize import brentq, minimize, root
from scipy.special import gammaln, logsumexp

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE = HERE.parent.parent / "2026_09_30_ds11_single10"
AUDIT = HERE.parent / "same_source_cfo_audit" / "results.json"
SIDECAR = HERE.parent / "source_balance" / "catalogue_identities.json"
sys.path.insert(0, str(ROOT / "tools"))
import ds7_fast_baseline_adapter as fast  # noqa: E402

VARIANTS = ("identity_only", "gamma1000")
SCALE_HZ = 100.0
CFO_PRIOR_VARIANCE_HZ2 = 1e12
REFERENCE_RF_HZ = 11.2e9
ALIAS_PERIOD_HZ = 1.0 / 4.4e-6
GAMMA_HZ = 1000.0
LOG_T4_NORMAL = float(
    gammaln(2.5) - gammaln(2.0) - 0.5 * math.log(4.0 * math.pi) - math.log(SCALE_HZ)
)


class ProfileNumericalError(RuntimeError):
    pass


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _track_score(values: np.ndarray, offset: float) -> float:
    centered = values - offset
    return float(
        len(values) * LOG_T4_NORMAL
        - 2.5 * np.log1p(centered * centered / (4.0 * SCALE_HZ**2)).sum()
        - 0.5 * offset * offset / CFO_PRIOR_VARIANCE_HZ2
    )


def _track_gradient(offset: float, values: np.ndarray) -> float:
    centered = values - offset
    return float(
        np.sum(5.0 * centered / (4.0 * SCALE_HZ**2 + centered * centered))
        - offset / CFO_PRIOR_VARIANCE_HZ2
    )


def _track_hessian(offset: float, values: np.ndarray) -> float:
    centered = values - offset
    denominator = 4.0 * SCALE_HZ**2 + centered * centered
    return float(
        np.sum(5.0 * (centered * centered - 4.0 * SCALE_HZ**2) / denominator**2)
        - 1.0 / CFO_PRIOR_VARIANCE_HZ2
    )


def scalar_stationary_modes(values: np.ndarray) -> np.ndarray:
    """Locate all scalar CFO maxima found by the frozen profiler's root audit."""
    values = np.asarray(values, dtype=float)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
        raise ValueError("finite nonempty scalar residual row required")
    center = float(np.median(values))
    y = values - center
    starts = np.unique(np.r_[np.quantile(y, np.linspace(0.0, 1.0, 9)), 0.0])
    guesses = starts.copy()
    for _ in range(100):
        residual = y[None, :] - guesses[:, None]
        weights = 5.0 / (4.0 + (residual / SCALE_HZ) ** 2)
        new = (
            (weights * y).sum(axis=1) - SCALE_HZ**2 * center / CFO_PRIOR_VARIANCE_HZ2
        ) / (weights.sum(axis=1) + SCALE_HZ**2 / CFO_PRIOR_VARIANCE_HZ2)
        if np.max(np.abs(new - guesses)) < 1e-6:
            guesses = new
            break
        guesses = new
    lower, upper = min(float(y.min()), -center), max(float(y.max()), -center)
    if lower == upper:
        return np.asarray([center + lower])
    distances = np.asarray([1e-4, 0.01, 1.0, 10.0, 100.0, 1000.0])
    nodes = np.unique(np.r_[
        lower, upper, y, starts, guesses,
        np.clip(guesses[:, None] - distances, lower, upper).ravel(),
        np.clip(guesses[:, None] + distances, lower, upper).ravel(),
    ])
    actual = center + nodes
    centered = values[None, :] - actual[:, None]
    gradients = np.sum(
        5.0 * centered / (4.0 * SCALE_HZ**2 + centered * centered), axis=1
    ) - actual / CFO_PRIOR_VARIANCE_HZ2
    roots = []
    for index in range(len(nodes) - 1):
        left, right = actual[index:index + 2]
        gl, gr = gradients[index:index + 2]
        if gl == 0.0:
            candidate = float(left)
        elif gl > 0.0 > gr:
            candidate = brentq(
                lambda value: _track_gradient(value, values), left, right,
                xtol=1e-9, rtol=1e-14,
            )
        else:
            continue
        if _track_hessian(candidate, values) < 0.0:
            roots.append(candidate)
    if gradients[-1] == 0.0 and _track_hessian(float(actual[-1]), values) < 0.0:
        roots.append(float(actual[-1]))
    if not roots:
        raise ProfileNumericalError("no scalar CFO stationary maximum located")
    return np.unique(np.round(np.asarray(roots), decimals=9))


def wrapped_terms(native_difference_hz: float, gamma_hz: float):
    """Return log Bayes factor and its first two difference derivatives."""
    if math.isinf(gamma_hz):
        return 0.0, 0.0, 0.0
    if not math.isfinite(gamma_hz) or gamma_hz <= 0.0:
        raise ValueError("gamma must be positive or infinity")
    k = 2.0 * math.pi / ALIAS_PERIOD_HZ
    rho = math.exp(-k * gamma_hz)
    phase = k * native_difference_hz
    denominator = 1.0 + rho * rho - 2.0 * rho * math.cos(phase)
    first_denominator = 2.0 * rho * k * math.sin(phase)
    second_denominator = 2.0 * rho * k * k * math.cos(phase)
    log_factor = math.log1p(-rho * rho) - math.log(denominator)
    first = -first_denominator / denominator
    second = -second_denominator / denominator + (first_denominator / denominator) ** 2
    return log_factor, first, second


def coupling_normalizer(alpha: float, gamma_hz: float,
                        prior_variance_hz2: float = CFO_PRIOR_VARIANCE_HZ2) -> float:
    """Normalize W under the two independent Gaussian canonical-CFO priors."""
    if math.isinf(gamma_hz):
        return 1.0
    if not math.isfinite(alpha) or alpha <= 0.0:
        raise ValueError("positive finite RF conversion required")
    if not math.isfinite(prior_variance_hz2) or prior_variance_hz2 <= 0.0:
        raise ValueError("positive finite CFO prior variance required")
    k = 2.0 * math.pi / ALIAS_PERIOD_HZ
    rho = math.exp(-k * gamma_hz)
    total = 1.0
    for harmonic in range(1, 100001):
        exponent = harmonic * math.log(rho) - (
            harmonic * k * alpha * math.sqrt(prior_variance_hz2)
        ) ** 2
        term = 2.0 * math.exp(exponent) if exponent > -745.0 else 0.0
        total += term
        if term < 1e-16:
            break
    else:
        raise ProfileNumericalError("wrapped-prior normalization series did not converge")
    return total


def pair_objective(offsets, values_a, values_b, alpha, gamma_hz):
    a, b = map(float, offsets)
    wrapped, first, second = wrapped_terms(alpha * (a - b), gamma_hz)
    score = (
        _track_score(values_a, a) + _track_score(values_b, b) + wrapped
        - math.log(coupling_normalizer(alpha, gamma_hz))
    )
    gradient = np.asarray([
        _track_gradient(a, values_a) + alpha * first,
        _track_gradient(b, values_b) - alpha * first,
    ])
    coupling_curvature = alpha * alpha * second
    hessian = np.asarray([
        [_track_hessian(a, values_a) + coupling_curvature, -coupling_curvature],
        [-coupling_curvature, _track_hessian(b, values_b) + coupling_curvature],
    ])
    return score, gradient, hessian


def profile_pair(values_a, values_b, alpha: float, gamma_hz: float = GAMMA_HZ):
    """Return the highest qualified located joint stationary CFO profile."""
    values_a = np.asarray(values_a, dtype=float)
    values_b = np.asarray(values_b, dtype=float)
    modes_a = scalar_stationary_modes(values_a)
    modes_b = scalar_stationary_modes(values_b)
    if math.isinf(gamma_hz):
        a = max(modes_a, key=lambda value: _track_score(values_a, value))
        b = max(modes_b, key=lambda value: _track_score(values_b, value))
        score = _track_score(values_a, a) + _track_score(values_b, b)
        gradient = max(abs(_track_gradient(a, values_a)), abs(_track_gradient(b, values_b)))
        curvature = max(_track_hessian(a, values_a), _track_hessian(b, values_b))
        if gradient >= 1e-7 or curvature >= 0.0:
            raise ProfileNumericalError("free-coupling scalar CFO stationarity failure")
        return score, np.asarray([a, b]), {
            "scalar_modes": [len(modes_a), len(modes_b)], "starts": 0,
            "roots": 1, "gradient": float(gradient),
            "converged": bool(gradient < 1e-7 and curvature < 0.0),
            "max_hessian_eigenvalue": float(curvature),
        }

    combinations = []
    canonical_period = ALIAS_PERIOD_HZ / alpha
    for a, b in itertools.product(modes_a, modes_b):
        independent_score = _track_score(values_a, a) + _track_score(values_b, b)
        feasible_score = independent_score + wrapped_terms(alpha * (a - b), gamma_hz)[0]
        combinations.append((a, b, independent_score, feasible_score))
    lower_bound = max(row[3] for row in combinations)
    maximum_log_factor = wrapped_terms(0.0, gamma_hz)[0]
    retained = [
        row for row in combinations
        if row[2] + maximum_log_factor >= lower_bound - 1e-12
    ]
    starts = []
    for a, b, _, _ in retained:
        starts.append(np.asarray([a, b], dtype=float))
        branch = round((a - b) / canonical_period)
        target = branch * canonical_period
        common = 0.5 * (a + b)
        starts.append(np.asarray([common + 0.5 * target, common - 0.5 * target]))
    distinct_starts = []
    for start in starts:
        if not any(np.max(np.abs(start - old)) < 1e-6 for old in distinct_starts):
            distinct_starts.append(start)

    roots = []
    terminal_failures = []
    for start in distinct_starts:
        def equations(offsets):
            return pair_objective(offsets, values_a, values_b, alpha, gamma_hz)[1]

        def jacobian(offsets):
            return pair_objective(offsets, values_a, values_b, alpha, gamma_hz)[2]

        solved = root(equations, start, jac=jacobian, method="hybr", options={"xtol": 1e-9})
        candidate = np.asarray(solved.x, dtype=float)
        score, gradient, hessian = pair_objective(
            candidate, values_a, values_b, alpha, gamma_hz
        )
        if (not np.isfinite(candidate).all() or not np.isfinite(score)
                or np.max(np.abs(gradient)) >= 1e-7
                or np.max(np.linalg.eigvalsh(hessian)) >= -1e-12):
            # A local maximization fallback helps a start that reached a saddle.
            optimized = minimize(
                lambda value: -pair_objective(value, values_a, values_b, alpha, gamma_hz)[0],
                start, jac=lambda value: -pair_objective(
                    value, values_a, values_b, alpha, gamma_hz
                )[1], method="BFGS", options={"gtol": 1e-9, "maxiter": 100},
            )
            candidate = np.asarray(optimized.x, dtype=float)
            polished = root(equations, candidate, jac=jacobian, method="hybr",
                            options={"xtol": 1e-10})
            candidate = np.asarray(polished.x, dtype=float)
            score, gradient, hessian = pair_objective(
                candidate, values_a, values_b, alpha, gamma_hz
            )
        if (np.isfinite(candidate).all() and np.isfinite(score)
                and np.max(np.abs(gradient)) < 1e-7
                and np.max(np.linalg.eigvalsh(hessian)) < -1e-12):
            if not any(np.max(np.abs(candidate - old[1])) < 1e-4 for old in roots):
                roots.append((float(score), candidate, float(np.max(np.abs(gradient)))))
        else:
            terminal_failures.append(float(np.max(np.abs(gradient))))
    if not roots:
        raise ProfileNumericalError(
            f"no negative-curvature joint CFO root; failures={terminal_failures}"
        )
    best = max(roots, key=lambda row: row[0])
    return best[0], best[1], {
        "scalar_modes": [int(len(modes_a)), int(len(modes_b))],
        "starts": len(distinct_starts), "roots": len(roots),
        "gradient": best[2], "converged": True,
        "max_hessian_eigenvalue": float(np.max(np.linalg.eigvalsh(
            pair_objective(best[1], values_a, values_b, alpha, gamma_hz)[2]
        ))),
        "scalar_mode_combinations": len(combinations),
        "pruned_mode_combinations": len(combinations) - len(retained),
        "failed_starts": len(terminal_failures),
    }


class SoftFragmentCFO:
    def __init__(self, documents, config, candidate_norad, pairs, variant,
                 *, model_factory=None, gamma_hz=None):
        if variant not in VARIANTS:
            raise ValueError(f"unknown soft fragment CFO variant: {variant}")
        factory = model_factory or fast.baseline.Stationary
        self.documents = documents
        self.models = [factory(document, config) for document in documents]
        self.candidate_norad = candidate_norad
        self.pairs = pairs
        self.variant = variant
        self.gamma_hz = (math.inf if variant == "identity_only" else GAMMA_HZ) \
            if gamma_hz is None else float(gamma_hz)
        self._slots = {}
        expected = set()
        for di, document in enumerate(documents):
            mapping = candidate_norad[di]
            if set(mapping) != {track["track_id"] for track in document["tracks"]}:
                raise ValueError("candidate identity track coverage mismatch")
            for ti, track in enumerate(document["tracks"]):
                ids = tuple(map(int, mapping[track["track_id"]]))
                if len(ids) != len(set(ids)):
                    raise ValueError("duplicate physical NORAD in candidate bank")
                self._slots[(di, ti)] = {norad: slot for slot, norad in enumerate(ids)}
                expected.add((di, ti))
        grouped = set()
        for pair in pairs:
            members = tuple(pair["members"])
            if len(members) != 2 or grouped.intersection(members):
                raise ValueError("pairs must contain two unique, unshared tracks")
            if members[0][0] != members[1][0]:
                raise ValueError("paired fragments must belong to one document")
            grouped.update(members)
            support = tuple(pair["candidate_norad"])
            if not support or len(support) != len(set(support)):
                raise ValueError("pair candidate support must be nonempty and unique")
            if not set(support).issubset(self._slots[members[0]]):
                raise ValueError("pair candidate intersection missing from first member")
            if not set(support).issubset(self._slots[members[1]]):
                raise ValueError("pair candidate intersection missing from second member")
            document = documents[members[0][0]]
            track_a = document["tracks"][members[0][1]]
            track_b = document["tracks"][members[1][1]]
            if (int(track_a["receiver_id"]) != int(track_b["receiver_id"])
                    or int(track_a["channel"]) != int(track_b["channel"])
                    or float(track_a["rf_hz"]) != float(track_b["rf_hz"])):
                raise ValueError("paired fragments must share receiver, channel and exact RF")
            times_a = np.asarray(track_a["times_s"])[track_a["mask"]]
            times_b = np.asarray(track_b["times_s"])[track_b["mask"]]
            visits_a = set(np.asarray(track_a["visits"])[track_a["mask"]].tolist())
            visits_b = set(np.asarray(track_b["visits"])[track_b["mask"]].tolist())
            if visits_a & visits_b or not (
                times_a.max() < times_b.min() or times_b.max() < times_a.min()
            ):
                raise ValueError("paired fragments must have disjoint training support")
        if not grouped.issubset(expected):
            raise ValueError("pair member outside document")
        self.singletons = tuple(sorted(expected - grouped))
        self.last_profile_audit = {}

    @staticmethod
    def _add_local(derivative, document_index, local):
        derivative[:2] += local[:2]
        derivative[document_index + 2] += local[2]

    def _prediction_terms(self, x, gradient):
        terms = {}
        for di, (document, engine) in enumerate(zip(self.documents, self.models, strict=True)):
            local = np.asarray(x)[[0, 1, di + 2]]
            for ti, track in enumerate(document["tracks"]):
                prediction, visible = engine.prediction(track, local)
                residual = track["y"][None, :] - prediction
                prediction_gradient = None
                if gradient:
                    prediction_gradient = np.empty((*prediction.shape, 3))
                    for axis in range(3):
                        step = 1e-4 if axis < 2 else 1e-5
                        plus, minus = local.copy(), local.copy()
                        plus[axis] += step
                        minus[axis] -= step
                        if axis == 2:
                            plus[axis], minus[axis] = min(5.0, plus[axis]), max(-5.0, minus[axis])
                        pp, vp = engine.prediction(track, plus)
                        pm, vm = engine.prediction(track, minus)
                        if not np.array_equal(visible, vp) or not np.array_equal(visible, vm):
                            raise ValueError("candidate visibility changed inside gradient stencil")
                        prediction_gradient[:, :, axis] = (pp - pm) / (plus[axis] - minus[axis])
                terms[(di, ti)] = {
                    "track": track, "residual": residual, "visible": visible,
                    "prediction_gradient": prediction_gradient,
                }
        return terms

    def _candidate_gradient(self, term, slot, offset):
        track = term["track"]
        mask = track["mask"]
        centered = term["residual"][slot, mask] - offset
        influence = 5.0 * centered / (4.0 * SCALE_HZ**2 + centered * centered)
        return np.sum(
            influence[:, None] * term["prediction_gradient"][slot, mask, :], axis=0
        )

    def evaluate(self, x, gradient=True):
        x = np.asarray(x, dtype=float)
        terms = self._prediction_terms(x, gradient)
        total = 0.0
        derivative = np.zeros_like(x)
        audit_rows = []
        for member in self.singletons:
            di, _ = member
            term = terms[member]
            track = term["track"]
            score, _, audits, offsets = fast.profile(term["residual"], track["mask"])
            if not all(row["converged"] for row in audits):
                raise ProfileNumericalError("singleton CFO stationarity failure")
            score = np.where(term["visible"], score, -np.inf)
            normal = logsumexp(score)
            if not np.isfinite(normal):
                raise ValueError("no visible singleton candidate")
            total += float(normal - math.log(track["catalogue_size"]))
            if gradient:
                candidate_gradient = np.asarray([
                    self._candidate_gradient(term, slot, offset)
                    for slot, offset in enumerate(offsets)
                ])
                self._add_local(derivative, di, np.exp(score - normal) @ candidate_gradient)

        for pair in self.pairs:
            member_a, member_b = pair["members"]
            term_a, term_b = terms[member_a], terms[member_b]
            track_a, track_b = term_a["track"], term_b["track"]
            if track_a["catalogue_size"] != track_b["catalogue_size"]:
                raise ValueError("paired tracks have different catalogue denominators")
            alpha = float(track_a["rf_hz"]) / REFERENCE_RF_HZ
            candidate_scores, candidate_gradients = [], []
            for norad in pair["candidate_norad"]:
                slot_a = self._slots[member_a][norad]
                slot_b = self._slots[member_b][norad]
                if not term_a["visible"][slot_a] or not term_b["visible"][slot_b]:
                    candidate_scores.append(-np.inf)
                    if gradient:
                        candidate_gradients.append(np.zeros(3))
                    continue
                values_a = term_a["residual"][slot_a, track_a["mask"]]
                values_b = term_b["residual"][slot_b, track_b["mask"]]
                score, offsets, audit = profile_pair(values_a, values_b, alpha, self.gamma_hz)
                audit_rows.append({
                    "tracks": list(pair["track_ids"]), "norad": int(norad),
                    "profile_score": float(score), "offsets_hz": offsets.tolist(),
                    **audit,
                })
                candidate_scores.append(score)
                if gradient:
                    candidate_gradients.append(
                        self._candidate_gradient(term_a, slot_a, offsets[0])
                        + self._candidate_gradient(term_b, slot_b, offsets[1])
                    )
            candidate_scores = np.asarray(candidate_scores)
            normal = logsumexp(candidate_scores)
            if not np.isfinite(normal):
                raise ValueError("no jointly visible common candidate")
            total += float(normal - math.log(track_a["catalogue_size"]))
            if gradient:
                local = np.exp(candidate_scores - normal) @ np.asarray(candidate_gradients)
                self._add_local(derivative, member_a[0], local)
        self.last_profile_audit = {
            "candidate_profiles": len(audit_rows),
            "max_scalar_modes": max((max(row["scalar_modes"]) for row in audit_rows), default=0),
            "max_starts": max((row["starts"] for row in audit_rows), default=0),
            "max_roots": max((row["roots"] for row in audit_rows), default=0),
            "max_gradient": max((row["gradient"] for row in audit_rows), default=0.0),
            "worst_max_hessian_eigenvalue": max(
                (row["max_hessian_eigenvalue"] for row in audit_rows), default=None
            ),
            "failed_starts": sum(row.get("failed_starts", 0) for row in audit_rows),
            "scalar_mode_combinations": sum(
                row.get("scalar_mode_combinations", 1) for row in audit_rows
            ),
            "pruned_mode_combinations": sum(
                row.get("pruned_mode_combinations", 0) for row in audit_rows
            ),
            "rows": audit_rows,
        }
        return {"score": total, "gradient": derivative}

    def held_diagnostics(self, x):
        """Native predictive score with CFO roots and identity weights frozen by training."""
        terms = self._prediction_terms(np.asarray(x, dtype=float), False)
        rows = []
        for member in self.singletons:
            term = terms[member]
            track = term["track"]
            train, joint, audits, _ = fast.profile(term["residual"], track["mask"])
            if not all(row["converged"] for row in audits):
                raise ProfileNumericalError("singleton held CFO stationarity failure")
            train = np.where(term["visible"], train, -np.inf)
            joint = np.where(term["visible"], joint, -np.inf)
            train_normal, joint_normal = logsumexp(train), logsumexp(joint)
            rows.append({
                "kind": "independent", "members": [list(member)],
                "training_score": float(train_normal - math.log(track["catalogue_size"])),
                "held_score": float(joint_normal - train_normal),
            })
        for pair in self.pairs:
            member_a, member_b = pair["members"]
            term_a, term_b = terms[member_a], terms[member_b]
            track_a, track_b = term_a["track"], term_b["track"]
            alpha = float(track_a["rf_hz"]) / REFERENCE_RF_HZ
            train_scores, joint_scores = [], []
            for norad in pair["candidate_norad"]:
                slot_a, slot_b = self._slots[member_a][norad], self._slots[member_b][norad]
                if not term_a["visible"][slot_a] or not term_b["visible"][slot_b]:
                    train_scores.append(-np.inf)
                    joint_scores.append(-np.inf)
                    continue
                training_a = term_a["residual"][slot_a, track_a["mask"]]
                training_b = term_b["residual"][slot_b, track_b["mask"]]
                train_score, offsets, audit = profile_pair(
                    training_a, training_b, alpha, self.gamma_hz
                )
                if not audit["converged"]:
                    raise ProfileNumericalError("paired held CFO stationarity failure")
                joint_score = pair_objective(
                    offsets, term_a["residual"][slot_a], term_b["residual"][slot_b],
                    alpha, self.gamma_hz,
                )[0]
                train_scores.append(train_score)
                joint_scores.append(joint_score)
            train_normal = logsumexp(train_scores)
            joint_normal = logsumexp(joint_scores)
            if not np.isfinite(train_normal) or not np.isfinite(joint_normal):
                raise ValueError("no jointly visible candidate for held diagnostic")
            rows.append({
                "kind": "paired", "members": [list(value) for value in pair["members"]],
                "training_score": float(train_normal - math.log(track_a["catalogue_size"])),
                "held_score": float(joint_normal - train_normal),
            })
        return {"held_score": float(sum(row["held_score"] for row in rows)), "rows": rows}


def _load_resources(index, documents):
    if index is None or len(documents) != 1:
        raise ValueError("one immutable single-scan index is required")
    plan_path = BASE / "plan.json"
    plan = json.loads(plan_path.read_text())
    sidecar = json.loads(SIDECAR.read_text())
    audit = json.loads(AUDIT.read_text())
    if sidecar.get("schema") != "ds11-source-balance-identities/v1":
        raise ValueError("identity sidecar schema mismatch")
    if audit.get("schema") != "ds11-same-source-cfo-audit/v1":
        raise ValueError("fragment audit schema mismatch")
    if sidecar.get("plan_sha256") != _digest(plan_path):
        raise ValueError("identity sidecar plan binding mismatch")
    for name, path in (("plan", plan_path), ("identity_sidecar", SIDECAR)):
        binding = audit["source_sha256"][name]
        if Path(binding["path"]).resolve() != path.resolve():
            raise ValueError(f"fragment audit {name} path binding mismatch")
        if "sha256:" + _digest(path) != binding["sha256"]:
            raise ValueError(f"fragment audit {name} digest binding mismatch")
    expected_audit = audit["source_sha256"]["audit_script"]
    if "sha256:" + _digest(Path(expected_audit["path"])) != expected_audit["sha256"]:
        raise ValueError("fragment audit script binding mismatch")
    for name, path in (
        ("fast_adapter", ROOT / "tools" / "ds7_fast_baseline_adapter.py"),
        ("baseline_adapter", ROOT / "tools" / "ds7_baseline_adapter.py"),
    ):
        binding = audit["source_sha256"][name]
        if (Path(binding["path"]).resolve() != path.resolve()
                or "sha256:" + _digest(path) != binding["sha256"]):
            raise ValueError(f"fragment audit {name} binding mismatch")
    entry = plan["inputs"][index]
    scan = sidecar["scans"][str(index)]
    if (documents[0]["session_id"] != entry["session_id"]
            or scan["session_id"] != entry["session_id"]):
        raise ValueError("session/index binding mismatch")
    for artifact in entry["artifacts"]:
        if "sha256:" + _digest(Path(artifact["path"])) != artifact["sha256"]:
            raise ValueError("plan artifact digest mismatch")
    result_binding = audit["source_sha256"]["original_iid_results"][index]
    expected_result = BASE / "runs" / f"{index:02d}_iid.json"
    if Path(result_binding["path"]).resolve() != expected_result.resolve():
        raise ValueError("original IID result path binding mismatch")
    if "sha256:" + _digest(Path(result_binding["path"])) != result_binding["sha256"]:
        raise ValueError("original IID result binding mismatch")
    mapping = {track_id: row["candidate_norad"] for track_id, row in scan["tracks"].items()}
    by_id = {track["track_id"]: ti for ti, track in enumerate(documents[0]["tracks"])}
    pairs = []
    used = set()
    audit_tracks = {row["track_id"]: row for row in audit["track_rows"]
                    if row["scan_index"] == index}
    for row in audit["same_receiver_pair_rows"]:
        if row["scan_index"] != index or row["support"] != "disjoint":
            continue
        if row["receiver_a"] != row["receiver_b"] or row["norad_a"] != row["norad_b"]:
            raise ValueError("frozen pair is not same-receiver/same-identity")
        a, b = row["track_a"], row["track_b"]
        if a not in by_id or b not in by_id or used.intersection((a, b)):
            raise ValueError("frozen pair coverage mismatch")
        used.update((a, b))
        track_a, track_b = documents[0]["tracks"][by_id[a]], documents[0]["tracks"][by_id[b]]
        frozen_a, frozen_b = audit_tracks.get(a), audit_tracks.get(b)
        if (frozen_a is None or frozen_b is None or not frozen_a["unambiguous"]
                or not frozen_b["unambiguous"]
                or int(frozen_a["norad"]) != int(row["norad_a"])
                or int(frozen_b["norad"]) != int(row["norad_b"])):
            raise ValueError("frozen pair confidence or identity mismatch")
        if (float(track_a["rf_hz"]) != float(track_b["rf_hz"])
                or float(track_a["rf_hz"]) != row["rf_hz"]
                or int(track_a["receiver_id"]) != int(row["receiver_a"])
                or int(track_b["receiver_id"]) != int(row["receiver_b"])
                or int(track_a["channel"]) != int(track_b["channel"])
                or not row["same_channel"]):
            raise ValueError("frozen pair exact RF mismatch")
        times_a = np.asarray(track_a["times_s"])[track_a["mask"]]
        times_b = np.asarray(track_b["times_s"])[track_b["mask"]]
        visits_a = set(np.asarray(track_a["visits"])[track_a["mask"]].tolist())
        visits_b = set(np.asarray(track_b["visits"])[track_b["mask"]].tolist())
        if visits_a & visits_b or not (
            times_a.max() < times_b.min() or times_b.max() < times_a.min()
        ):
            raise ValueError("frozen disjoint pair now overlaps")
        common = tuple(sorted(set(map(int, mapping[a])) & set(map(int, mapping[b]))))
        if int(row["norad_a"]) not in common or len(common) < 2:
            raise ValueError("frozen identity absent or candidate uncertainty collapsed")
        pairs.append({
            "members": ((0, by_id[a]), (0, by_id[b])),
            "track_ids": (a, b), "frozen_norad": int(row["norad_a"]),
            "candidate_norad": common, "rf_hz": float(row["rf_hz"]),
        })
    return [mapping], pairs, {
        "plan": _digest(plan_path), "sidecar": _digest(SIDECAR),
        "fragment_audit": _digest(AUDIT),
        "incumbent": _digest(Path(result_binding["path"])),
    }


def build_model(documents, config, variant, index=None):
    candidate_norad, pairs, resources = _load_resources(index, documents)
    model = SoftFragmentCFO(documents, config, candidate_norad, pairs, variant)
    model.metadata = {
        "variant": variant,
        "objective": "conditional retained-bank profile likelihood",
        "candidate_probabilities": "conditional weights, not calibrated physical probabilities",
        "pair_freeze": (
            "original IID training-selected same NORAD, confidence>=0.90, "
            "disjoint training support"
        ),
        "paired_groups": len(pairs), "paired_tracks": 2 * len(pairs),
        "independent_tracks": len(model.singletons),
        "candidate_support": "full common-NORAD intersection for each frozen pair",
        "cfo": (
            "weak 1MHz individual priors; identity_only independent or "
            "gamma1000 wrapped coupling"
        ),
        "coupling_normalization": (
            "exact wrapped factor normalizer under independent Gaussian CFO priors"
        ),
        "native_gamma_hz": None if variant == "identity_only" else GAMMA_HZ,
        "native_alias_period_hz": ALIAS_PERIOD_HZ,
        "resource_sha256": resources,
    }
    return model
