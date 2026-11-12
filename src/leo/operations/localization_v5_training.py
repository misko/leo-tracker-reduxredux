"""Process-owned scalar receipts for opt-in annotation optimizer work."""

import json
import math
import os
from copy import deepcopy
from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.contracts.localization_v5 import validate_annotation_training_policy

_FIELDS = {
    "evaluations", "stopped", "converged", "reference_fit_completed", "budget_exhausted",
    "physical_budget_exhausted", "optimizer", "solution_origin", "attempted", "completed",
    "success", "status", "message", "reported_fun", "nfev", "njev", "nit", "reason",
    "reported_score", "recorded_score", "additional_residual_evaluations",
    "source", "projected_gradient_inf_norm", "gtol", "satisfied",
    "final_metadata_calculate_calls",
    "score", "convergence_kind", "scipy_result_scope",
}
_NESTED = {"scipy_result", "score_correction", "fallback", "stationarity"}
_COUNTS = {"evaluations", "nfev", "njev", "nit", "additional_residual_evaluations",
           "final_metadata_calculate_calls"}


def _summary(value):
    if not isinstance(value, dict):
        raise ValueError("Annotation training metadata mapping required")
    result = {}
    for key, item in value.items():
        if key in _FIELDS:
            if key in _COUNTS and (type(item) is not int or item < 0):
                raise ValueError("Nonnegative integer annotation training counts required")
            if (item is not None and type(item) not in (str, bool, int, float)):
                raise ValueError("Scalar annotation training metadata required")
            if isinstance(item, float) and not math.isfinite(item):
                raise ValueError("Finite annotation training metadata required")
            result[key] = item
        elif key in _NESTED:
            result[key] = None if item is None else _summary(item)
        elif key == "attempts":
            if not isinstance(item, list):
                raise ValueError("Annotation optimizer attempt list required")
            result[key] = [_summary(attempt) for attempt in item]
    return result


def _counts(fits):
    return dict(
        started=len(fits),
        completed=sum(row["state"] == "completed" for row in fits),
        failed=sum(row["state"] == "failed" for row in fits),
        in_progress=sum(row["state"] == "started" for row in fits),
        evaluations=sum(row["evaluations"] for row in fits),
        optimizer_attempts=sum(len(row.get("result", {}).get("attempts", [None]))
                               for row in fits if row["state"] == "completed"),
        optimizer_attempts_unknown_fits=sum(row["state"] != "completed" for row in fits),
        primary_failures=sum(
            (row["result"].get("attempts") or [row["result"]])[0].get("converged") is False
            or (row["result"].get("scipy_result") or {}).get("success") is False
            for row in fits if row["state"] == "completed"),
        score_corrections=sum(
            row["result"].get("score_correction") is not None
            or any(attempt.get("score_correction") is not None
                   for attempt in row["result"].get("attempts", []))
            for row in fits if row["state"] == "completed"),
        fallback_attempted=sum(row.get("result", {}).get("fallback", {}).get("attempted") is True
                               for row in fits),
        fallback_completed=sum(row.get("result", {}).get("fallback", {}).get("completed") is True
                               for row in fits),
        budget_exhausted=sum(row.get("result", {}).get("budget_exhausted") is True for row in fits),
    )


def _validate_receipt(receipt, binding):
    if (not isinstance(receipt, dict)
            or set(receipt) != {"schema_version", "pid", "policy_sha256", "fits", "counts"}
            or type(receipt["schema_version"]) is not int or receipt["schema_version"] != 1
            or type(receipt["pid"]) is not int or receipt["pid"] <= 0
            or receipt["policy_sha256"] != binding or not isinstance(receipt["fits"], list)):
        raise ValueError("Bound annotation training work receipt required")
    for row in receipt["fits"]:
        state = row.get("state") if isinstance(row, dict) else None
        keys = {"state", "evaluations"} | ({"result"} if state == "completed" else
                                             {"error_type"} if state == "failed" else set())
        if (state not in ("started", "completed", "failed") or set(row) != keys
                or type(row["evaluations"]) is not int or row["evaluations"] < 0):
            raise ValueError("Annotation training work state required")
        if state == "completed" and (
            _summary(row["result"]) != row["result"]
            or row["result"].get("evaluations") != row["evaluations"]
        ):
            raise ValueError("Scalar annotation training result required")
        if state == "failed" and not isinstance(row["error_type"], str):
            raise ValueError("Annotation training failure type required")
    if receipt["counts"] != _counts(receipt["fits"]):
        raise ValueError("Annotation training work counts differ from receipts")
    if any(type(value) is not int for value in receipt["counts"].values()):
        raise ValueError("Integer annotation training work counts required")


def validate_provenance(value, policy):
    """Validate saved accounting without accessing solver artifacts or files."""
    validate_annotation_training_policy(policy)
    binding = canonical_digest(policy)
    if (not isinstance(value, dict)
            or set(value) != {"schema_version", "policy", "policy_sha256", "receipts", "counts"}
            or type(value["schema_version"]) is not int or value["schema_version"] != 1
            or value["policy"] != policy or value["policy_sha256"] != binding
            or not isinstance(value["receipts"], list)):
        raise ValueError("Bound annotation training work provenance required")
    validate_annotation_training_policy(value["policy"])
    for receipt in value["receipts"]:
        _validate_receipt(receipt, binding)
    pids = [row["pid"] for row in value["receipts"]]
    if len(pids) != len(set(pids)):
        raise ValueError("Distinct annotation training worker PIDs required")
    fits = [fit for receipt in value["receipts"] for fit in receipt["fits"]]
    if value["counts"] != _counts(fits) or any(
        type(item) is not int for item in value["counts"].values()
    ):
        raise ValueError("Annotation training aggregate counts differ from receipts")
    return value


class ProcessTrainingFit:
    """Each PID publishes only the annotation fits it actually executes."""

    def __init__(self, fit, receipts):
        self.fit = fit
        self._policy = deepcopy(validate_annotation_training_policy(fit.policy))
        self.receipts = Path(receipts).resolve() / "annotation-training"
        if self.receipts.is_relative_to("/mnt/qnap01"):
            raise ValueError("QNAP is read-only")
        self.receipts.mkdir(parents=True, exist_ok=False)
        self.pid = None
        self.fits = []

    @property
    def policy(self):
        return deepcopy(self._policy)

    def __call__(self, problem, *args, **kwargs):
        pid = os.getpid()
        if self.pid != pid:
            self.pid, self.fits = pid, []
        row = dict(state="started", evaluations=0)
        self.fits.append(row)
        self.flush()

        class CountedProblem:
            def __getattr__(self, name):
                return getattr(problem, name)

            def residual(self, *values, **options):
                row["evaluations"] += 1
                return problem.residual(*values, **options)

        try:
            result = self.fit(CountedProblem(), *args, **kwargs)
            summary = _summary(result)
            if summary.get("evaluations") != row["evaluations"]:
                raise ValueError("Annotation fit count differs from physical residual calls")
            row.update(state="completed", result=summary)
            self.flush()
            return result
        except BaseException as exc:
            row.pop("result", None)
            row.update(state="failed", error_type=type(exc).__name__)
            self.flush()
            raise

    def flush(self):
        if self.pid != os.getpid():
            return
        receipt = dict(schema_version=1, pid=self.pid, policy_sha256=canonical_digest(self._policy),
                       fits=self.fits, counts=_counts(self.fits))
        _validate_receipt(receipt, receipt["policy_sha256"])
        path = self.receipts / (str(self.pid) + ".json")
        temporary = path.with_suffix(".partial")
        temporary.write_text(json.dumps(receipt, sort_keys=True, allow_nan=False) + "\n")
        temporary.replace(path)

    def provenance(self):
        self.flush()
        receipts = []
        binding = canonical_digest(self._policy)
        for path in sorted(self.receipts.glob("*.json")):
            receipt = json.loads(path.read_bytes())
            _validate_receipt(receipt, binding)
            if path.stem != str(receipt["pid"]):
                raise ValueError("Annotation training receipt filename differs from PID")
            receipts.append(receipt)
        fits = [fit for receipt in receipts for fit in receipt["fits"]]
        return validate_provenance(dict(schema_version=1, policy=self.policy,
                                       policy_sha256=binding, receipts=receipts,
                                       counts=_counts(fits)), self._policy)
