"""Score the frozen crossed-factor services and render explicit missing outcomes."""

import json
from pathlib import Path

from ..__main__ import save_json
from ..scoring import ARMS, distance_km, validate_result
from .factor_cross import TREATMENTS
from .factor_cross_trial import REPORT, TRIAL, write_members
from .full_held_scores import held_references
from .input_factor_bridge import REPO, _sha, check, read
from .input_factor_comparison import REPORT as PARENT
from .input_factor_comparison import ledger, sealed
from .prefix_figures import csv_file

RECIPIENTS = ("capture-era", "ordinary")
METHODS = {"capture-era": "v5_secant_fit", "ordinary": "whole_fractional"}
CHANGES = (
    "changed_gate_flags",
    "changed_cfo_measurements",
    "winner_added",
    "winner_lost",
    "winner_switched",
    "changed_winning_measurement",
)


def chart_specs():
    charts = []
    for cohort, ids in zip(("development", "reserves"), TRIAL, strict=True):
        for recipient in RECIPIENTS:
            charts.append(
                dict(
                    id=f"crossed-factors-{recipient}-{cohort}",
                    method="factor_cross",
                    scope="roof",
                    title=f"Crossed fields on {recipient} factors, {cohort}",
                    caption=(
                        "Swaps use reciprocal matches and preserve the recipient roster. "
                        "Missing cells retain their status."
                    ),
                    cases=list(ids),
                    seal=f"figure-{cohort}-lock.json",
                    provenance=["scores.csv", "summary.json"],
                    series=[
                        dict(
                            key=key,
                            label=label,
                            value=f"{recipient}-{treatment}",
                            where={"cohort": cohort},
                            file="figure-positions.jsonl.gz",
                            native_field="origin_native_sha256",
                            native_authority="ordinary" if recipient == "ordinary" else "frozen",
                        )
                        for key, label, treatment in (
                            ("one", "Donor scores and gate", "score"),
                            ("stock", "Unmodified recipient", "control"),
                            ("one_native_factors", "Donor CFO", "cfo"),
                            ("all_visits", "Both families", "both"),
                        )
                    ],
                )
            )
    return dict(version=1, charts=charts)


def keyed(path, key):
    import gzip

    with gzip.open(path, "rt") as stream:
        out = {}
        for row in map(json.loads, stream):
            index = key(row)
            if index in out:
                raise ValueError(f"duplicate row key {index}")
            out[index] = row
    return out


def checked_result(row, binding, plan):
    if any(row[k] != value for k, value in binding.items()):
        raise ValueError("scientific service result differs from frozen hybrid input")
    result = row["result"]
    validate_result(result)
    if result["status"] == "ok":
        proof = row["runtime"]["proof"]
        finish = row["runtime"]["finish"]
        if (
            row["exit_code"] != 0
            or len(proof) != 1
            or len(finish) != 1
            or proof[0]["cpu"] != row["cpu"]
            or row["cpu"] not in plan["cpus"]
            or proof[0]["memory"] != plan["memory_bytes"]
            or proof[0]["swap"] != plan["swap_bytes"]
            or finish[0]["cgroup_peak"] > plan["memory_bytes"]
        ):
            raise ValueError("complete hybrid lies outside the recorded resource envelope")
    return result


def publish():
    run_lock = sealed(REPORT, "prediction-lock.json")
    plan = read(REPORT / "plan.json")
    for relative, digest in plan["sources"].items():
        check(REPO / relative, digest)
    for name, digest in plan["files"].items():
        check(REPORT / name, digest)
    attempted = ledger(REPORT / "results.jsonl.gz")
    if set(attempted) != set(run_lock["cases"]):
        raise ValueError("attempted service roster differs from sealed receipt")
    case_ids = [ident for pair in TRIAL for ident in pair]
    cohorts = {ident: ("development" if ident in TRIAL[0] else "reserves") for ident in case_ids}
    truth = {r["id"]: r["truth"] for r in held_references("", case_ids)[1]}
    sealed(PARENT, "prediction-lock.json")
    control = keyed(PARENT / "positions.jsonl.gz", lambda r: (r["id"], r["method"]))
    diagnostics = {"cohorts": {}, "run_lock_sha256": _sha(REPORT / "prediction-lock.json")}
    rows, figures, cells = [], [], {}
    for binding in plan["cases"]:
        ident, recipient, treatment = (binding[k] for k in ("recording", "recipient", "treatment"))
        older = control[ident, METHODS[recipient]]
        run = attempted.get(binding["id"])
        if run is None:
            result = dict(
                status="missing",
                reason="No terminal service receipt at this checkpoint",
                boundary="Stored crossed native factors through compact standalone",
                metrics={"position_attempted": False},
            )
        else:
            result = checked_result(run, binding, plan)
        figures.append(
            dict(
                id=ident,
                method=f"{recipient}-{treatment}",
                cohort=cohorts[ident],
                tile=older["tile"],
                origin_native_sha256=binding["origin_native_sha256"],
                native_sha256=binding["native_sha256"],
                catalog_sha256=binding["catalog_sha256"],
                result=result,
            )
        )
        for arm in ARMS:
            before = older["result"]["arms"][arm]
            after = result.get("arms", {}).get(arm, {})
            error = distance_km(after.get("latlon"), truth[ident])
            orig_error = distance_km(before["latlon"], truth[ident])
            freq = after.get("rf_rms_hz")
            elapsed = run["wall_s"] if run else None
            peak = (
                run["runtime"]["finish"][0]["cgroup_peak"]
                if run and run["runtime"]["finish"]
                else None
            )
            row = dict(
                recording=ident,
                recipient=recipient,
                treatment=treatment,
                arm=arm,
                status=result["status"],
                error_km=error,
                recipient_error_km=orig_error,
                error_delta_km=None if error is None else error - orig_error,
                displacement_km=distance_km(after.get("latlon"), before["latlon"]),
                conditional_rms_hz=freq,
                recipient_conditional_rms_hz=before["rf_rms_hz"],
                conditional_rms_delta_hz=None if freq is None else freq - before["rf_rms_hz"],
                prepared_observations=result["metrics"].get("observations"),
                prepared_tracks=result["metrics"].get("tracks"),
                recipient_observations=older["result"]["metrics"]["observations"],
                recipient_tracks=older["result"]["metrics"]["tracks"],
                cavity_offered=result["metrics"].get("cavity_offered"),
                wall_s=elapsed,
                cgroup_peak_bytes=peak,
                **{k: binding["changes"].get(k, 0) for k in CHANGES},
            )
            rows.append(row)
            cells[ident, recipient, treatment, arm] = row
    for ident in case_ids:
        for recipient in RECIPIENTS:
            clean = control[ident, METHODS[recipient]]
            figures.append(
                dict(
                    clean,
                    method=recipient + "-control",
                    cohort=cohorts[ident],
                    origin_native_sha256=clean.get("origin_native_sha256", clean["native_sha256"]),
                )
            )
            for arm in ARMS:
                contrasts = [cells[ident, recipient, t, arm]["error_delta_km"] for t in TREATMENTS]
                if all(d is not None for d in contrasts):
                    diagnostics.setdefault("interactions", []).append(
                        dict(
                            recording=ident,
                            recipient=recipient,
                            arm=arm,
                            geographic_error_interaction_km=contrasts[2]
                            - contrasts[1]
                            - contrasts[0],
                        )
                    )
    for cohort, ids in zip(("development", "reserves"), TRIAL, strict=True):
        records = [r for r in rows if r["recording"] in ids and r["arm"] == "c0"]
        diagnostics["cohorts"][cohort] = {
            k: sum(r["status"] == k for r in records)
            for k in sorted({r["status"] for r in records})
        }
    diagnostics["enabled"] = len(plan["cases"])
    write_members(REPORT / "figure-positions.jsonl.gz", figures)
    csv_file(REPORT / "scores.csv", rows)
    save_json(REPORT / "summary.json", diagnostics)
    save_json(REPORT / "figures.json", chart_specs())
    files = {
        name: _sha(REPORT / name)
        for name in ("figure-positions.jsonl.gz", "scores.csv", "summary.json")
    }
    for cohort, ids in zip(("development", "reserves"), TRIAL, strict=True):
        save_json(
            REPORT / f"figure-{cohort}-lock.json",
            dict(cases=list(ids), files=files, scorer_sha256=_sha(Path(__file__))),
        )


if __name__ == "__main__":
    publish()
