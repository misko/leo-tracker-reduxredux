"""Seal stage counters independently of uninstrumented release timings."""

import argparse
from pathlib import Path

from ..__main__ import local_output, read_predictions, save_json, write
from ..scoring import ARMS, distance_km, validate_result
from . import fit_work_capture_coverage as held
from . import fit_work_profile as profiling
from . import fit_work_trial as trial
from .cavity_pressure_results import scientific_payload
from .fit_work_results import FILES
from .phase_support_results import pack
from .prefix_figures import csv_file
from .short_receiver_figures import _frozen_roof

COMMON = trial.COMMON


def branch_summary(run):
    phases = run["selected_refits"]
    if phases is None:
        return None
    return dict(
        hypotheses=len(phases),
        cpu_s=sum(x["cpu_s"] for x in phases),
        wall_s=sum(x["wall_s"] for x in phases),
        counts={key: sum(x["calls"][key] for x in phases) for key in phases[0]["calls"]}
        if phases
        else {},
    )


def recover(directory, tag):
    pair = directory / tag
    doc = COMMON.read(directory / f"{tag}.json")
    for name, proof in (("service.log", "log_sha256"), ("position.json", "result_sha256")):
        if COMMON.sha(pair / name) != doc[proof]:
            raise ValueError("monitored files differ from their frozen terminal digests")
    if doc["result"] is not None:
        validate_result(doc["result"])
    return doc | {"conditional": branch_summary(doc)}


def figure(folder, index, parent):
    case = index["binding"]["id"]
    rows, scores = [], []
    truth, frozen = _frozen_roof()
    if frozen[case]["native"]["sha256"] != index["binding"]["native_sha256"]:
        raise ValueError("held factor is outside the capture-era authority")
    for tag in ("stock", "candidate"):
        run = index[tag]
        result = run["result"] or trial.pressure.direct.v5_lean._no_fix(
            "Monitored factor-to-position result unavailable", status="failed"
        )
        rows.append(
            dict(
                id=case,
                method=run["method"],
                result=result,
                native_sha256=index["binding"]["native_sha256"],
                catalog_sha256=index["binding"]["catalog_sha256"],
                input_sha256=index["binding"]["request_sha256"],
                tile=index["binding"]["tile"],
            )
        )
        for arm in ARMS:
            value = result["arms"][arm]
            scores.append(
                dict(
                    id=case,
                    method=run["method"],
                    arm=arm,
                    status=result["status"],
                    position_error_km=distance_km(value["latlon"], truth[case]["truth"]),
                    conditional_RMS_hz=value.get("rf_rms_hz"),
                    frequency_objective=result["metrics"].get(f"{arm}_frequency_score"),
                )
            )
    pack(folder / "positions.jsonl.gz", rows)
    csv_file(folder / "scores.csv", scores)
    files = ("positions.jsonl.gz", "scores.csv", "monitor.json")
    save_json(
        folder / "figure-lock.json",
        dict(
            cases=[case],
            files={name: COMMON.sha(folder / name) for name in files},
            parent_release_receipt_sha256=COMMON.sha(parent / "receipt.json"),
        ),
    )
    save_json(
        folder / "figures.json",
        dict(
            version=1,
            charts=[
                dict(
                    id="constrained-cavity-phase-fit-work-held-" + case.lower(),
                    method=trial.CANDIDATE,
                    scope="roof",
                    cases=[case],
                    seal="figure-lock.json",
                    title="Prepared phase-gate projection on held capture-era factors",
                    caption=(
                        "Separate monitored branch-coverage pair under 512 MiB and zero swap. "
                        "Both methods used the same capture-era factors, causal catalogue "
                        "and offer."
                    ),
                    provenance=["monitor.json", "scores.csv"],
                    series=[
                        dict(
                            key=key,
                            value=method,
                            label=label,
                            file="positions.jsonl.gz",
                            **(
                                {
                                    "match": [
                                        "native_sha256",
                                        "catalog_sha256",
                                        "input_sha256",
                                        "tile",
                                    ]
                                }
                                if key == "stock"
                                else {}
                            ),
                        )
                        for key, method, label in (
                            ("one", trial.CANDIDATE, "Fixed residual-gate projection"),
                            ("stock", trial.STOCK, "Phase-release compact v5"),
                        )
                    ],
                )
            ],
        ),
    )


def publish(folders, parent, profile):
    out = parent / "diagnostics"
    out.mkdir(exist_ok=True, parents=True)
    facts = {}
    for case, root in folders.items():
        plan = COMMON.read(root / "plan.json")
        if plan["case"]["id"] != case:
            raise ValueError("wrong monitored recording")
        entry = dict(binding=plan["case"], plan=plan)
        for tag in ("stock", "candidate"):
            path = root / f"{tag}.json"
            if path.is_file():
                entry[tag] = recover(root, tag)
                write(out / f"{case}-{tag}.log", (root / tag / "service.log").read_bytes())
        if case == profiling.ID:
            for tag, method in (("stock", trial.STOCK), ("candidate", trial.CANDIDATE)):
                release = read_predictions(parent / FILES[method])[case]["result"]
                if scientific_payload(entry[tag]["result"]) != scientific_payload(release):
                    raise ValueError("reserve probe changed its corresponding release result")
        elif case != profiling.ID and "candidate" in entry:
            marked = out / case
            marked.mkdir(exist_ok=True)
            save_json(marked / "monitor.json", entry)
            figure(marked, entry, parent)
        facts[case] = entry
    save_json(out / "monitors.json", facts)
    save_json(out / "stock-cprofile.json", profiling.metrics(profile / "profile.prof"))
    write(out / "stock-cprofile.log", (profile / "profile.log").read_bytes())
    names = [p.name for p in sorted(out.iterdir()) if p.is_file() and p.name != "receipt.json"]
    save_json(
        out / "receipt.json",
        dict(cases=list(facts), files={name: COMMON.sha(out / name) for name in names}),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scratch", type=Path)
    parser.add_argument("profile", type=Path)
    args = parser.parse_args()
    roots = {
        "DS29-0247": args.scratch / "leo-fit-reserve-count",
        "DS26-0122": args.scratch / "leo-fit-coverage-v2",
        "DS26-0036": args.scratch / "leo-fit-coverage-0036",
        held.CASE: args.scratch / "leo-fit-coverage-0052",
    }
    for case in ("DS29-0357", "DS26-0072"):
        path = args.scratch / f"leo-fit-coverage-{case[-4:]}"
        if (path / "comparison.json").is_file():
            roots[case] = path
    publish(roots, local_output(trial.REPORT), args.profile)
