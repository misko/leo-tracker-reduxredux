"""Repair diagnostic classification from immutable saved fits; perform no fits."""

import hashlib
import json
from pathlib import Path

from leo.application.regional_position_runner import json_value

HERE = Path(__file__).resolve().parent
EXPECTED_ERROR = "AttributeError(\"'PositionFit' object has no attribute 'get'\")"


def normalize_terminal(terminal):
    """Both production fitters' dict/dataclass terminals share a serialized port."""
    normalized = json_value(terminal)
    if not isinstance(normalized, dict) or not isinstance(normalized.get("vector"), list):
        raise ValueError("Terminal must be a fit mapping or PositionFit dataclass")
    return normalized


def supplement(receipt):
    terminal = normalize_terminal(receipt["diagnostics"]["terminal"])
    fit = receipt["fit"]
    returned = receipt["gradient_audits"]["returned"]
    assert terminal["vector"] == fit["vector"], "Different states require a new objective audit"
    assert terminal["objective"] == fit["objective"] == returned["objective"]
    assert abs(fit["stationarity"] - returned["stationarity"]) <= 1e-12
    if receipt["status"] == "failed":
        assert receipt.get("error") == EXPECTED_ERROR
    else:
        assert receipt["status"] == "complete" and receipt.get("error") is None
    qualified = bool(
        fit["converged"] and returned["stationarity"] <= 0.001 and returned["feasible"]
    )
    return dict(
        original_status=receipt["status"],
        original_error=receipt.get("error"),
        numerical_fit_status="qualified" if qualified else "unqualified",
        numerical_fit_preserved=True,
        terminal_equals_returned_exactly=True,
        terminal_audit=returned,
        audit_provenance="Original returned audit reused after exact vector/objective equality",
        new_objective_evaluations=0,
        new_optimizer_calls=0,
    )


def main():
    protocol = HERE / "prefit-protocol.json"
    digest = hashlib.sha256(protocol.read_bytes()).hexdigest()
    rows = {}
    for name in (
        "ordinary-coarse-legacy",
        "ordinary-coarse-bounded",
        "zero-timing-legacy",
        "zero-timing-bounded",
    ):
        path = HERE / "prefit-attempts" / f"{name}.json"
        receipt = json.loads(path.read_text())
        assert receipt["protocol_sha256"] == digest
        rows[name] = dict(
            receipt_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), **supplement(receipt)
        )
    value = dict(
        protocol_sha256=digest,
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        issue="Bounded terminal was PositionFit; .get diagnostic failed after preserving fit",
        scope="No original receipt changed; no refit or new numerical objective evaluation",
        rows=rows,
    )
    with (HERE / "prefit-terminal-supplement.json").open("x") as stream:
        json.dump(value, stream, indent=2)
        stream.write("\n")
    print("Supplemented four saved terminals; zero refits/objective evaluations")


if __name__ == "__main__":
    main()
