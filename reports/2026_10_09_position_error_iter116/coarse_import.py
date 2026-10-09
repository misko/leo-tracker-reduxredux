"""Strict receipt-only preparation and runtime import of ordinary coarse fits."""

import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from adapter import Hard60Objective, PointEvaluator

from leo.analysis.regional_position_bootstrap import BootstrapMatch, PositionBootstrap
from leo.analysis.regional_position_fit import PositionFit
from leo.analysis.regional_position_score import zero_sum_basis
from leo.application.hard60_runner import HARD60_SCORE, Hard60Configuration
from leo.application.regional_position_runner import json_value
from leo.contracts.digests import canonical_digest


def validate_receipt(receipt, point, bank_count):
    """No orbit calls: reject lost/extra parameter blocks and nonfinite state."""
    if set(receipt) != {"result", "reason"} or receipt["reason"] is not None:
        raise ValueError("coarse receipt missing or failed")
    payload = receipt["result"]
    if set(payload) != {"bootstrap", "fits"} or set(payload["fits"]) != {"V16"}:
        raise ValueError("unexpected coarse model blocks")
    seed = payload["bootstrap"]
    if set(seed) != {"satellite_indices", "vector", "matches"}:
        raise ValueError("unexpected bootstrap blocks")
    indices = seed["satellite_indices"]
    if (
        len(indices) < 2
        or len(set(indices)) != len(indices)
        or any(type(i) is not int or not 0 <= i < bank_count for i in indices)
    ):
        raise ValueError("invalid coarse satellite indices")
    fit_record = payload["fits"]["V16"]
    if fit_record.get("reason") is not None:
        raise ValueError("coarse fit failed")
    if set(fit_record) - {"fit", "reason", "optimizer"}:
        raise ValueError("unexpected fit blocks")
    fit = fit_record["fit"]
    if set(fit) != set(PositionFit.__dataclass_fields__):
        raise ValueError("fit schema changed or extra clock state present")
    for vector in (seed["vector"], fit["vector"]):
        vector = np.asarray(vector, float)
        if (
            vector.shape != (7 + len(indices),)
            or not np.isfinite(vector).all()
            or not np.array_equal(vector[:2], point)
        ):
            raise ValueError("physical vector/point mismatch")
    for field in ("objective", "signal_windows", "stationarity", "evaluations", "elapsed_s"):
        if not np.isfinite(fit[field]):
            raise ValueError("nonfinite fit metric")
    if seed["vector"][6] != 0 or abs(fit["vector"][6]) > 5000:
        raise ValueError("ordinary seed/fitted RF coefficient policy changed")
    fitted_vector = np.asarray(fit["vector"], float)
    shifts = fitted_vector[7] + zero_sum_basis(len(indices)) @ fitted_vector[8:]
    if (
        np.max(abs(fitted_vector[[3, 5]])) > 60 + 1e-8
        or abs(fitted_vector[7]) > 10 + 1e-8
        or np.max(abs(shifts)) > 20 + 1e-8
    ):
        raise ValueError("imported fit violates physical constraints")
    if fit["posterior_rms_hz"] is not None and not np.isfinite(fit["posterior_rms_hz"]):
        raise ValueError("nonfinite RMS")
    for match in seed["matches"]:
        if (
            set(match) != set(BootstrapMatch.__dataclass_fields__)
            or match["satellite_index"] not in indices
        ):
            raise ValueError("invalid bootstrap match")
        if any(not np.isfinite(match[f]) for f in ("timing_s", "shape_rms_hz", "shape_cost")):
            raise ValueError("nonfinite bootstrap match")
    return seed, fit


def source_check(document, repository):
    """Same sole non-numeric exclusion previously approved for105/107."""
    sources = document["configuration"]["source_digests"]
    required = {
        "application/hard60_runner.py",
        "analysis/hard60_score.py",
        "analysis/regional_position_fit.py",
        "analysis/regional_position_bootstrap.py",
        "application/regional_position_inputs.py",
    }
    if not required.issubset(sources):
        raise ValueError("incomplete historical source identities")
    ignored = []
    for name, digest in sources.items():
        actual = (
            "sha256:"
            + hashlib.sha256((Path(repository) / "src/leo" / name).read_bytes()).hexdigest()
        )
        if actual != digest:
            if name == "application/regional_position_report.py":
                ignored.append(name)
            else:
                raise ValueError("physical source mismatch: " + name)
    if canonical_digest(document["configuration"]["run"]) != canonical_digest(
        json_value(Hard60Configuration())
    ) or canonical_digest(document["configuration"]["scores"]["V16"]) != canonical_digest(
        json_value(HARD60_SCORE)
    ):
        raise ValueError("coarse numerical policy changed")
    return ignored


def overlay_first_getter(public_get, research_get, config_prefix):
    """Match107 exact saved local coarse override, else original public receipt."""
    provenance = {}

    def get(key):
        if not key.startswith(config_prefix + ":point:") or key.count(":") != 4:
            raise ValueError("only ordinary coarse aliases are allowed")
        shared = "b7-shared:" + key.removeprefix(config_prefix + ":")
        value = research_get(shared)
        origin = "verified107-overlay"
        actual_key = shared
        if value is None:
            value, origin, actual_key = public_get(key), "public-original", key
        provenance[key] = dict(port=origin, key=actual_key)
        return value

    return get, provenance


def pre_recovery_trace(regional_result):
    """Undo documented presentation rewrites; do not infer or select locations."""
    trace = copy.deepcopy(regional_result["searches"]["V16"]["evaluations"])
    index = {f"point:{p['east_km']:g}:{p['north_km']:g}": p for p in trace}
    if len(index) != len(trace):
        raise ValueError("duplicate baseline coordinates")
    original_fits, changes = {}, []
    for row in regional_result.get("recovery", {}).get("coarse", []):
        key, original = row["point"], row["original"]
        if key not in index or key in original_fits:
            raise ValueError("recovery provenance point mismatch")
        p = index[key]
        if not np.isfinite(original["objective"]) or original["vector"][:2] != [
            p["east_km"],
            p["north_km"],
        ]:
            raise ValueError("invalid original recovery provenance")
        original_fits[key] = original
        changes.append(
            dict(
                point=key,
                original_queue_score=original["objective"],
                displayed_post_recovery_score=p["score"],
                delta_displayed_minus_original=p["score"] - original["objective"],
                original_fit_sha256=canonical_digest(original),
                displayed_fit_sha256=canonical_digest(
                    regional_result["points"][key]["result"]["fits"]["V16"]["fit"]
                ),
            )
        )
        p["score"] = original["objective"]
    return trace, original_fits, changes


def snapshot(document, checkpoint_get, *, baseline_trace=None, original_fits=None):
    """Public get port only; all ordinary published coarse rows, no rank selection."""
    points = document["methods"][0]["points"]
    if baseline_trace is not None:
        if len(points) != len(baseline_trace) or any(
            any(a[k] != b[k] for k in ("east_km", "north_km", "spacing_km"))
            for a, b in zip(points, baseline_trace, strict=True)
        ):
            raise ValueError("saved baseline trace coordinates differ")
        points = baseline_trace
    if any("score" not in point for point in points):
        raise ValueError("sanitized document lacks scores; exact sealed baseline trace required")
    prefix = canonical_digest(document["configuration"]["run"])
    records, seen = [], set()
    for point in points:
        xy = [point["east_km"], point["north_km"]]
        if tuple(xy) in seen:
            raise ValueError("duplicate published coarse point")
        seen.add(tuple(xy))
        key = prefix + f":point:{xy[0]:g}:{xy[1]:g}"
        receipt = checkpoint_get(key)
        if receipt is None or receipt.get("result") is None:
            records.append(
                dict(
                    point=xy,
                    key=key,
                    receipt=receipt,
                    receipt_sha256=canonical_digest(receipt),
                    status="source-failed",
                    error="missing or failed ordinary checkpoint",
                )
            )
            continue
        seed, fit = validate_receipt(
            receipt, xy, len(document["diagnostics"]["bank"]["retained_numbers"])
        )
        short_key = key.removeprefix(prefix + ":")
        if (
            original_fits
            and short_key in original_fits
            and canonical_digest(fit) != canonical_digest(original_fits[short_key])
        ):
            raise ValueError("original recovery fit does not equal source checkpoint")
        if not np.isfinite(point["score"]) or abs(fit["objective"] - point["score"]) > 1e-6:
            raise ValueError("published native score differs from receipt")
        records.append(
            dict(
                point=xy,
                key=key,
                receipt=receipt,
                receipt_sha256=canonical_digest(receipt),
                seed_vector_sha256=canonical_digest(seed["vector"]),
                fit_vector_sha256=canonical_digest(fit["vector"]),
            )
        )
    return dict(
        session_id=document["session_id"],
        bank_numbers=document["diagnostics"]["bank"]["retained_numbers"],
        native_baseline=points,
        records=records,
    )


class ImportedEvaluator(PointEvaluator):
    """Imported fitted-c endpoint, shared archived seed; other points ordinary."""

    def __init__(self, *args, imported, **kwargs):
        super().__init__(*args, **kwargs)
        if not np.array_equal(self.bank.numbers, imported["bank_numbers"]):
            raise ValueError("whole-bank ID/index mapping changed")
        self.imported = {}
        self.failures = {}
        for row in imported["records"]:
            point = tuple(row["point"])
            if (
                point in self.imported
                or point in self.failures
                or canonical_digest(row["receipt"]) != row["receipt_sha256"]
            ):
                raise ValueError("duplicate or changed imported receipt")
            if row.get("status") == "source-failed":
                self.failures[point] = row["error"]
                continue
            seed, fit = validate_receipt(row["receipt"], point, len(self.bank.numbers))
            if (
                canonical_digest(seed["vector"]) != row["seed_vector_sha256"]
                or canonical_digest(fit["vector"]) != row["fit_vector_sha256"]
            ):
                raise ValueError("imported numerical vector changed")
            self.seeds[point] = PositionBootstrap(
                tuple(seed["satellite_indices"]),
                np.asarray(seed["vector"], float),
                tuple(BootstrapMatch(**m) for m in seed["matches"]),
            )
            self.imported[point] = fit

    def original_failure(self, point):
        return point in self.failures

    def __call__(self, east, north, arm):
        point, key = (float(east), float(north)), (float(east), float(north), arm)
        if point in self.failures:
            raise ValueError("original coarse failure preserved: " + self.failures[point])
        if arm != "fitted-c" or point not in self.imported or key in self.rows:
            return super().__call__(east, north, arm)
        seed, fit = self.seeds[point], self.imported[point]
        model = Hard60Objective(
            self.observations,
            self.bank.select(list(seed.satellite_indices)),
            self.prior,
            HARD60_SCORE,
        )
        vector = np.asarray(fit["vector"], float)
        if np.linalg.norm(vector[:2]) > self.prior.radius_km + 1e-9:
            raise ValueError("imported point outside prior disk")
        scores = self.scorer(model, vector, self.bank, fit["objective"])
        # The scorer independently checks the actual physical objective at runtime.
        row = dict(
            point=point,
            arm=arm,
            fit=fit,
            scores=scores,
            provenance="verified ordinary coarse receipt",
        )
        self.rows[key] = row
        return row


def read_import(path, expected_sha256):
    payload = Path(path).read_bytes()
    if hashlib.sha256(payload).hexdigest() != expected_sha256:
        raise ValueError("import bundle hash changed")
    return json.loads(payload)
