"""Score and chart the retrospective, matched-budget causal retry comparison."""

import argparse
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json
from ..scoring import ARMS, ROLES, arm_outcome, validate_result
from . import retry_cadence_trial, retry_policy_pair, screening_figures
from .capture_whole_results import MINIMAL, POS, geographic
from .fresh_replay_results import sealed
from .full_held_scores import held_references
from .full_v5_check import BULK, _sha
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from

FULL = retry_policy_pair.frozen.FULL
TWO = retry_policy_pair.frozen.TWO
HASH = retry_policy_pair.frozen.CONTROL
METHODS = retry_policy_pair.METHODS


def descriptor():
    return dict(
        version=2,
        charts=[
            dict(
                id="retry-policy-retrospective",
                method=METHODS[TWO],
                scope="roof",
                cases="sealed",
                title="Retrospective position with the two-failure retry policy",
                seal="prediction-lock.json",
                caption=(
                    "Across policies, each recording uses its original offer and causal catalogue. "
                    "The hash matches attempt counts by physical receiver and RF. Full conditional "
                    "uses the independently sealed compact result. The prospective DS26-0162 "
                    "recording is shown separately."
                ),
                provenance=["retry-counts.csv", "selection-lock.json", "holdout-policy-lock.json"],
                series=[
                    dict(
                        key=key,
                        label=label,
                        file=POS,
                        value=METHODS[mode],
                        native_field="paired_capture_sha256",
                        match=MINIMAL,
                    )
                    for key, mode, label in (
                        ("one", TWO, "0.8 s after two failed retries"),
                        ("stock", FULL, "Full conditional"),
                        ("all_visits", HASH, "Physical-key matched hash"),
                    )
                ],
            )
        ],
    )


def verified_rows(report):
    prediction = sealed(report, "prediction-lock.json")
    lock = whole_iq.read(report / "selection-lock.json")
    rows = rows_from(report / POS)
    keyed = {(row["id"], row["policy"]): row for row in rows}
    expected = {(i, p) for i in retry_policy_pair.ORDERS for p in METHODS}
    if set(keyed) != expected or len(rows) != len(expected):
        raise ValueError("each case and position policy needs one terminal")
    units = set()
    for ident, (cpu, policies) in retry_policy_pair.ORDERS.items():
        case, _ = whole_iq.binding(ident)
        native = whole_iq.checked(BULK / case["native"]["path"], case["native"]["sha256"])
        signed = whole_iq.read(native)
        original, _, release, reference = retry_cadence_trial.sources(ident)
        if (
            original["source"]["probes"] != signed["source"]["probes"]
            or reference["native_sha256"].removeprefix("sha256:") != _sha(native)
            or reference["result"] != keyed[ident, FULL]["result"]
            or release["receiver"] != lock["cases"][ident]["compact_receiver"]
        ):
            raise ValueError("full conditional position must bind the authentic full probe list")
        for policy in policies:
            row = keyed[ident, policy]
            resources = row["position_resources"]
            unit = resources["service"]["unit"]
            if row["cpu"] != cpu or unit in units:
                raise ValueError("compact services shared a unit or left the assigned CPU")
            units.add(unit)
            request = whole_iq.read(report / "requests" / f"{ident}-{policy}.json")
            if request["native_sha256"] != row["native_sha256"]:
                raise ValueError("terminal request did not consume the frozen policy input")
            for record in ("start", "end"):
                mark = resources[record]
                if mark is not None and (
                    mark["cpus"] != [cpu]
                    or mark["memory.max"] != whole_iq.MEMORY
                    or mark["memory.swap.max"] != 0
                    or mark["memory.swap.current"] != 0
                    or mark["memory.events.oom_kill"] != 0
                ):
                    raise ValueError("actual position resource observations differ from the lock")
            validate_result(row["result"])
    return rows, prediction


def publish(report):
    report = local_output(report)
    rows, prediction = verified_rows(report)
    _, reference = held_references(None, prediction["cases"])
    refs = {row["id"]: row for row in reference}
    records = geographic(rows, refs)
    arms = {(row["id"], row["method"]): row["result"] for row in rows}
    for row in records:
        result = arms[row["id"], row["method"]]
        row["status"], row["reason"] = arm_outcome(result, result["arms"][row["arm"]])
    csv_file(report / "scores.csv", records)
    csv_file(
        report / "v5-controls.csv",
        [
            dict(
                id=ident,
                role=role,
                arm=arm,
                **{
                    k: row["reference"][role][arm].get(k)
                    for k in ("status", "error_km", "rf_rms_hz")
                },
            )
            for ident, row in refs.items()
            for role in ROLES
            for arm in ARMS
        ],
    )
    save_json(report / "figures.json", descriptor())
    screening_figures.generate(report / "charts", evidence=report)
    save_json(
        report / "score-lock.json",
        dict(
            prediction_lock_sha256=_sha(report / "prediction-lock.json"),
            exporter_sha256=_sha(Path(__file__)),
            files={n: _sha(report / n) for n in ("scores.csv", "v5-controls.csv", "figures.json")},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=retry_policy_pair.REPORT)
    publish(parser.parse_args().out.resolve())
