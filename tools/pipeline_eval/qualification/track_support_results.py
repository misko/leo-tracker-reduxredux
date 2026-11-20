"""Score the time-integrated policy with authenticated fresh and earlier roof truth."""

import argparse
import gzip

from .. import whole_iq
from ..__main__ import ROOT, local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution, thresholds, validate_result
from . import drop_mechanism_results, fresh_adaptive, fresh_replay, screening_figures
from . import track_support_trial as trial
from .full_held_scores import held_references
from .full_v5_check import _sha
from .locked_assignments_results import compare_points, scientific
from .portable_gate_trials import compressed_rows
from .prefix_figures import csv_file
from .rescue_attribution import sealed
from .whole_pressure_trial import rows_from

REPORT = trial.REPORT
NEW_ROOF = "DS29-0047"
METHODS = {trial.STOCK: "time_curvature_stock", trial.CANDIDATE: "time_curvature"}
V5_FILES = {"authority": "roof-authority.json", "predictions": "fresh-v5.jsonl.gz"}
read = whole_iq.read


def references(plan, cases):
    all_roles, sidecars = {}, {}
    known = [i for i in cases if i != NEW_ROOF]
    if known:
        _, entries = held_references(None, known)
        all_roles.update((row["id"], row) for row in entries)
    if NEW_ROOF in cases:
        folder = fresh_replay.REPORT
        lock = read(folder / "all-figure-lock.json")
        for name in (*V5_FILES.values(), "reference-prediction-lock.json"):
            path = whole_iq.checked(folder / name, lock["files"][name])
            if name in V5_FILES.values():
                sidecars[name] = path.read_bytes()
        ref_lock = read(folder / "reference-prediction-lock.json")
        if ref_lock["files"][V5_FILES["predictions"]] != lock["files"][V5_FILES["predictions"]]:
            raise ValueError("fresh v5 roles did not use the same declared reference")
        ref = screening_figures.new_roof_references(folder, lock, V5_FILES, [NEW_ROOF])[NEW_ROOF]
        actual = plan["cases"][NEW_ROOF]
        expected = dict(
            catalog_sha256=actual["catalogue"],
            original_request_sha256=actual["request_sha256"],
            paired_capture_sha256=actual["paired_capture_sha256"],
            tile=actual["tile"],
        )
        if ref["bindings"] != expected or set(ref["reference"]) != set(ROLES):
            raise ValueError("fresh roof authority differs from the four paired role inputs")
        all_roles[NEW_ROOF] = ref
    return all_roles, sidecars


def archived_controls():
    data = drop_mechanism_results.archived()["retained"]
    for row in rows_from(
        sealed(fresh_adaptive.REPORT, "prediction-lock.json", "predictions.jsonl.gz")
    ):
        if row["condition"] == "fifth":
            data[row["id"]] = row
    return data


def owner_intersection(stock, candidate):
    if (
        stock["graph_sha256"] != candidate["graph_sha256"]
        or stock["stock_curved"] != candidate["stock_curved"]
        or stock["observations"] != candidate["observations"]
    ):
        raise ValueError("time-integrated policy modified the original Graph measurement store")
    a, b = (set(row["selected_curved"]) for row in (stock, candidate))
    result = dict(
        observations=stock["observations"],
        graph_tracks=stock["tracks"],
        graph_points=stock["graph_points"],
        original_curved=len(a),
        integrated_curved=len(b),
        stock_only=sorted(a - b),
        integrated_only=sorted(b - a),
        graph_sha256=stock["graph_sha256"],
        fit_paths={
            key: row.get("role") for key, row in (("stock", stock), ("integrated", candidate))
        },
        cavity_adopted={
            key: row.get("cavity_adopted")
            for key, row in (("stock", stock), ("integrated", candidate))
        },
    )
    if all("final" in q for q in (stock, candidate)):
        result["final_support"] = {
            k: compare_points(stock["final"][k], candidate["final"][k])
            for k in ("curved", "predictive")
        }
    return result


def one_attempt(work, plan, row, *, archive):
    folder = work / row["id"] / row["method"] / "observation"
    cell = plan["cases"][row["id"]]
    if (
        row["plan_sha256"] != _sha(REPORT / "plan.json")
        or row["native_sha256"] != cell["source"]["paced"]["native_sha256"]
        or row["pin"] != plan["pins"][row["id"]]
        or read(folder / "attempt.json") != row
    ):
        raise ValueError("attempt does not match sealed native input and affinity")
    log = whole_iq.checked(folder / "service.log", row["log_sha256"])
    artifacts = [log]
    actual = None
    if row["outcome_sha256"]:
        captured = whole_iq.checked(folder / "outcome.json", row["outcome_sha256"])
        artifacts.append(captured)
        if row["returncode"] == 0:
            actual = read(captured)
    if actual is None and row["returncode"] == 0:
        raise ValueError("missing successful position outcome")
    if archive:
        for f in artifacts:
            write(
                REPORT / f"{row['id']}-{row['method']}-{f.name}.gz",
                gzip.compress(f.read_bytes(), mtime=0),
            )
    result = actual["result"] if actual else drop_mechanism_results.failed(row)
    validate_result(result)
    measured = actual["bounds"] if actual else {}
    for key in ("start", "end"):
        if measured and (
            measured[key]["memory.max"] != plan["memory_bytes"]
            or measured[key]["memory.swap.max"]
            or measured[key]["memory.swap.current"]
            or measured["pin"] != row["pin"]
        ):
            raise ValueError("physical position budget differs from trial")
    return (
        result,
        (actual or {}).get("observation"),
        dict(
            id=row["id"],
            method=METHODS[row["method"]],
            pin=row["pin"],
            status=result["status"],
            supervisor_wall_s=row["supervisor_wall_s"],
            process_cpu_s=measured.get("cpu_s"),
            process_wall_s=measured.get("wall_s"),
            cg_peak_bytes=measured.get("end", {}).get("memory.peak"),
            position_stages=result["metrics"].get("stage_s", {}),
        ),
    )


def pair(work, plan, ident, *, archive):
    case = read(REPORT / f"{ident}-pair-lock.json")
    attempts = case["attempts"]
    if (
        case["cases"] != [ident]
        or case["plan_sha256"] != _sha(REPORT / "plan.json")
        or any(row["id"] != ident for row in attempts)
        or [r["method"] for r in attempts] != plan["orders"][ident]
    ):
        raise ValueError("per-recording paired outcomes have not closed")
    rows = [one_attempt(work, plan, a, archive=archive) for a in attempts]
    previous = archived_controls()[ident]
    outputs = dict(zip(plan["orders"][ident], rows, strict=True))
    if previous["native_sha256"] != plan["cases"][ident]["source"]["paced"]["native_sha256"]:
        raise ValueError("unmodified compact archive differs from the measured paced data")
    a, b = (outputs[m][1] for m in METHODS)
    details = (
        owner_intersection(a, b) if a and b and "graph_sha256" in a and "graph_sha256" in b else {}
    )
    details["stock_archive_exact"] = (
        scientific(outputs[trial.STOCK][0]) == scientific(previous["result"])
        if outputs[trial.STOCK][0]["status"] == "ok"
        else None
    )
    details["paired_position_move_km"] = {
        arm: distance_km(
            outputs[trial.STOCK][0]["arms"][arm]["latlon"],
            outputs[trial.CANDIDATE][0]["arms"][arm]["latlon"],
        )
        for arm in ARMS
    }
    return outputs, details


def score(ident, condition, result, ref):
    scores = []
    for arm in ARMS:
        value = result["arms"][arm]
        error = distance_km(value["latlon"], ref["truth"])
        errors = {role: ref["reference"][role][arm].get("error_km") for role in ROLES}
        original = errors["baseline"]
        scores.append(
            dict(
                id=ident,
                arm=arm,
                method=METHODS[condition],
                status=result["status"],
                geographic_error_km=error,
                conditional_rms_hz=value.get("rf_rms_hz"),
                frequency_objective=result["metrics"].get(f"{arm}_frequency_score"),
                within_5pct=error is not None and original is not None and error <= 1.05 * original,
                within_10pct=error is not None
                and original is not None
                and error <= 1.10 * original,
                **{f"v5_{key}_error_km": v for key, v in errors.items()},
            )
        )
    return scores


def summarize(scores):
    summary = {}
    for method in METHODS.values():
        summary[method] = {}
        for arm in ARMS:
            rows = [r for r in scores if r["method"] == method and r["arm"] == arm]
            errors = [r["geographic_error_km"] for r in rows]
            summary[method][arm] = dict(
                scheduled=len(rows),
                published=sum(x is not None for x in errors),
                error_km=distribution(errors),
                within_km=thresholds(errors),
                within_5pct_original=sum(r["within_5pct"] for r in rows),
                within_10pct_original=sum(r["within_10pct"] for r in rows),
                conditional_rms_hz=distribution([r["conditional_rms_hz"] for r in rows]),
            )
    return summary


def pairwise(scores):
    keyed = {(r["id"], r["arm"], r["method"]): r for r in scores}
    rows = []
    for ident in trial.PINS:
        for arm in ARMS:
            a, b = (keyed[ident, arm, method] for method in METHODS.values())
            old, new = (item["geographic_error_km"] for item in (a, b))
            old_rf, new_rf = (item["conditional_rms_hz"] for item in (a, b))
            rows.append(
                dict(
                    id=ident,
                    arm=arm,
                    error_change_km=new - old if old is not None and new is not None else None,
                    rf_rms_change_hz=new_rf - old_rf
                    if old_rf is not None and new_rf is not None
                    else None,
                    within_5pct_stock=old is not None and new is not None and new <= 1.05 * old,
                    within_10pct_stock=old is not None and new is not None and new <= 1.10 * old,
                )
            )
    return rows


def publish(work, only=None):
    plan = read(REPORT / "plan.json")
    if trial.sources() != plan["sources"]:
        raise ValueError("source lock does not reproduce the fitted variant")
    for name, digest in plan["parents"].items():
        whole_iq.checked(ROOT / name, digest)
    candidates = [only] if only else list(trial.PINS)
    if not only:
        for ident in candidates:
            sealed(REPORT, "prediction-lock.json", f"{ident}-pair-lock.json")
    captures = {ident: pair(work, plan, ident, archive=only is None) for ident in candidates}
    refs, sidecars = references(plan, candidates)
    scores, positions, traces, times = [], [], {}, []
    for ident, (results, detail) in captures.items():
        cell = plan["cases"][ident]
        traces[ident] = detail | {"paced": cell["paced"]}
        for condition, (result, _obs, clock) in results.items():
            times.append(clock)
            scores.extend(score(ident, condition, result, refs[ident]))
            positions.append(
                dict(
                    id=ident,
                    method=METHODS[condition],
                    tile=cell["tile"],
                    result=result,
                    native_sha256=cell["source"]["paced"]["native_sha256"],
                    catalog_sha256=cell["catalogue"],
                    original_request_sha256=cell["request_sha256"],
                    paired_capture_sha256=cell["paired_capture_sha256"],
                )
            )
    if only:
        save_json(
            REPORT / f"{only}-early-score.json",
            dict(
                pair_sha256=_sha(REPORT / f"{only}-pair-lock.json"),
                scores=scores,
                support=traces[only],
                resources=times,
            ),
        )
        return
    for name, data in sidecars.items():
        write(REPORT / name, data)
    write(REPORT / "positions.jsonl.gz", compressed_rows(positions))
    save_json(REPORT / "support.json", traces)
    stage_names = sorted({k for r in times for k in r["position_stages"]})
    for r in times:
        clock = r.pop("position_stages")
        r.update({name + "_wall_s": clock.get(name) for name in stage_names})
    csv_file(REPORT / "resources.csv", times)
    csv_file(REPORT / "scores.csv", scores)
    csv_file(REPORT / "paired-effects.csv", pairwise(scores))
    save_json(REPORT / "summary.json", summarize(scores))
    figures()


def figures():
    files = (
        "positions.jsonl.gz",
        "prediction-lock.json",
        "scores.csv",
        "resources.csv",
        "paired-effects.csv",
        "summary.json",
        "support.json",
        *V5_FILES.values(),
    )
    save_json(
        REPORT / "figure-lock.json",
        dict(
            cases=list(trial.PINS),
            files={name: _sha(REPORT / name) for name in files},
        ),
    )
    save_json(
        REPORT / "figures.json",
        dict(
            version=2,
            charts=[
                dict(
                    id="paced-time-integrated-curvature",
                    method="time_curvature",
                    scope="roof",
                    cases="sealed",
                    title="Time-integrated track curvature on paced detector packets",
                    caption=(
                        "Position pairs use identical verified paced detector packets. "
                        "The four original v5 lines use their archived capture-era factors."
                    ),
                    seal="figure-lock.json",
                    provenance=list(files[1:]),
                    roof_references=V5_FILES,
                    series=[
                        dict(
                            file=files[0],
                            value=METHODS[mode],
                            key=key,
                            label=label,
                            native_field="paired_capture_sha256",
                            match=[
                                "native_sha256",
                                "catalog_sha256",
                                "original_request_sha256",
                                "tile",
                            ],
                        )
                        for key, label, mode in (
                            ("one", "Time-integrated curvature", trial.CANDIDATE),
                            ("stock", "Ordinary compact v5", trial.STOCK),
                        )
                    ],
                )
            ],
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--only", choices=trial.PINS)
    a = parser.parse_args()
    publish(a.work, a.only)
