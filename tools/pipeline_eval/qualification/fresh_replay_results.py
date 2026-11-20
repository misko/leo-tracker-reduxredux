"""Seal fresh whole-IQ measurements, then attach historical and exact original v5 controls."""

import argparse
import gzip
from pathlib import Path

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, ROLES, distance_km, distribution
from . import diagnostic_whole_results as published
from . import fifth_crossover as earlier
from . import fresh_replay as trial
from . import frontier_whole_replay_results as traces
from . import screening_figures
from . import whole_band_results as measured
from . import whole_center_union_results as native
from .exact_wide_iq_results import detector_rows, timing_rows
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from
from .wide_roster_results import same_receiver, whole_support

METHODS = {"control": trial.CONTROL, "candidate": trial.METHOD}
VISITS = "visits.jsonl.gz"
POSITIONS = "positions.jsonl.gz"
OLD_SIX = "2b6962e0decae19cbfcfd1f386d897e8242c9326ac17ea5068ae41de77bd17bd"
OLD_PANEL = "all-six-figure-lock.json"
ROOF_REFERENCES = dict(authority="roof-authority.json", predictions="fresh-v5.jsonl.gz")


def sealed(out, name, expected=None):
    path = out / name
    if expected:
        whole_iq.checked(path, expected)
    value = whole_iq.read(path)
    for available, digest in value["files"].items():
        whole_iq.checked(out / available, digest)
    return value


def raw_seal(work, out):
    if (out / "raw-prediction-lock.json").exists():
        raise FileExistsError("paired raw measurements already sealed")
    plan = trial.source(work)
    rows, audit, authority, assets = [], {}, {}, []
    for ident, case in plan["cases"].items():
        outcomes = authority[ident] = {}
        case_audit = audit[ident] = {}
        streams, case_traces = {}, {}
        for role in METHODS:
            folder = work / ident / role
            path = folder / "raw.json"
            if not path.is_file():
                failure = folder.parent / f"{role}-failure.json"
                if not failure.is_file():
                    raise ValueError(
                        "raw is still pending; a missing stream needs a terminal receipt"
                    )
                outcomes[role] = dict(complete=False, failure=whole_iq.read(failure)["error"])
                continue
            raw = whole_iq.read(path)
            actual_plan = whole_iq.read(folder / "plan.json")
            if (
                actual_plan["detector_sha256"] != plan["detectors"][role]["sha256"]
                or actual_plan["receiver_files"] != plan["receiver_files"]
                or actual_plan["native_sources"] != plan["native_sources"]
                or actual_plan["capture_era_request"] != case["request_sha256"]
                or actual_plan["cpus"] != case["cpus"]
                or actual_plan["limit_s"] != plan["limit_s"]
                or actual_plan["recording"] != case["recording"]
            ):
                raise ValueError("raw launch differs from the original locked pair")
            streams[role], calls, logical = detector_rows(folder)
            whole_support(dict(raw, dual_calls=len(calls)), case, case["clock_authority"])
            case_traces[role] = list(
                traces.trace_rows(ident, role, (streams[role], calls, logical))
            )
            if role == "candidate":
                case_audit["scout_trace"] = traces.scout_trace(folder, case_traces[role])
                case_audit["union_admissions"] = native.union_telemetry(case_traces[role])
            source = whole_iq.checked(folder / "recording/native.json", raw["native_sha256"])
            name = f"native/{role}/{ident}.json.gz"
            write(out / name, gzip.compress(source.read_bytes(), mtime=0))
            assets.append(name)
            outcomes[role] = dict(
                complete=True,
                calls=len(calls),
                logical_native_sha256=logical,
                native_sha256=_sha(source),
                raw_receipt_sha256=_sha(path),
                replay_plan_sha256=_sha(folder / "plan.json"),
                **{key: raw[key] for key in ("input_manifest_sha256", *measured.COMMON)},
            )
        if set(streams) == set(METHODS):
            measured.pair_geometry(outcomes["control"], outcomes["candidate"])
            case_audit.update(
                published.gate_stability(
                    streams["control"],
                    streams["candidate"],
                    case_traces["control"],
                    case_traces["candidate"],
                )
            )
        rows.extend(row for branch in case_traces.values() for row in branch)
    pack(out / VISITS, rows)
    save_json(out / "probe-audit.json", audit)
    save_json(out / "raw-authority.json", authority)
    assets.extend(
        (
            VISITS,
            "probe-audit.json",
            "raw-authority.json",
            "source-lock.json",
            "selection.json",
            "PROTOCOL.md",
        )
    )
    save_json(
        out / "raw-prediction-lock.json",
        dict(
            cases=list(plan["cases"]),
            files={name: _sha(out / name) for name in assets},
        ),
    )


def seal(work, out):
    path = out / "prediction-lock.json"
    if path.exists():
        raise FileExistsError("fresh predictions already sealed")
    plan = trial.source(work)
    if not (out / "raw-prediction-lock.json").is_file():
        raw_seal(work, out)
    raw = sealed(out, "raw-prediction-lock.json")
    authority = whole_iq.read(out / "raw-authority.json")
    measurements, rows, logs = {}, [], []
    for ident, planned in plan["cases"].items():
        group = measurements[ident] = {}
        for role, name in METHODS.items():
            row, resource, artifact = measured.attempt(work, ident, role, plan, method=name)
            folder = work / ident / role
            if artifact is not None:
                receipt = authority[ident][role]
                whole_iq.checked(folder / "raw.json", receipt["raw_receipt_sha256"])
                whole_iq.checked(folder / "plan.json", receipt["replay_plan_sha256"])
                if row["native_sha256"] != receipt["native_sha256"]:
                    raise ValueError("coordinates differ from the earlier raw product seal")
            logfile = folder / "service.log"
            if logfile.is_file():
                whole_iq.checked(logfile, resource["service"]["log_sha256"])
                log_name = f"{ident}-{role}.service.log"
                write(out / log_name, logfile.read_bytes())
                logs.append(log_name)
            group[role] = resource
            rows.append(row)
        if all(x.get("counts") for x in group.values()):
            published.matched_physical(group["control"], group["candidate"], planned)
    traces.protect_resources(measurements)
    pack(out / POSITIONS, rows)
    save_json(out / "resources.json", measurements)
    names = (POSITIONS, "resources.json", "raw-prediction-lock.json", *logs)
    save_json(
        path,
        dict(
            cases=list(plan["cases"]),
            files=raw["files"] | {n: _sha(out / n) for n in names},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def references(out, case):
    reference = sealed(out, "reference-prediction-lock.json")
    fresh = rows_from(out / "fresh-v5.jsonl.gz")
    if reference["cases"] != [case["id"]] or sorted(row["method"] for row in fresh) != sorted(
        ROLES
    ):
        raise ValueError("the frozen four numerical v5 roles are needed for the new DS29 row")
    authorized = whole_iq.read(
        whole_iq.checked(trial.DS29 / "evaluation-references.json", trial.TRUTH_SHA)
    )
    label = authorized[case["id"]]
    truth = [label["latitude_deg"], label["longitude_deg"]]
    bindings = dict(
        paired_capture_sha256=case["capture_native_sha256"],
        catalog_sha256=case["catalog_sha256"],
        tile=case["tile"],
        original_request_sha256=case["request_sha256"],
    )
    coordinates = dict(
        id=case["id"], group="DS29", recording=case["id"], truth=truth, bindings=bindings
    )
    records = {}
    for row in fresh:
        if row["id"] != case["id"] or any(row[k] != v for k, v in bindings.items()):
            raise ValueError(
                "new original v5 controls differ from original matched capture authority"
            )
        result = row["result"]
        records[row["method"]] = {
            arm: dict(
                result["arms"][arm],
                status=result["status"],
                error_km=distance_km(truth, result["arms"][arm]["latlon"]),
            )
            for arm in ARMS
        }
    save_json(out / "roof-authority.json", dict(cases=[coordinates]))
    return dict(coordinates, reference=records)


def geographic(rows, refs):
    scores = []
    for row in rows:
        case, result = refs[row["id"]], row["result"]
        for arm in ARMS:
            endpoint = result["arms"][arm]
            error = distance_km(case["truth"], endpoint["latlon"])
            before = case["reference"]["baseline"][arm]["error_km"]
            scores.append(
                dict(
                    id=row["id"],
                    method=row["method"],
                    arm=arm,
                    cohort=row["cohort"],
                    status=result["status"],
                    reason=result.get("reason"),
                    error_km=error,
                    reference_available=before is not None,
                    within_5pct=error is not None and before is not None and error <= before * 1.05,
                    within_10pct=error is not None
                    and before is not None
                    and error <= before * 1.10,
                    conditional_rms_hz=endpoint.get("rf_rms_hz"),
                    frequency_score=result["metrics"].get(f"{arm}_frequency_score"),
                    **{name + "_km": case["reference"][name][arm]["error_km"] for name in ROLES},
                )
            )
    return scores


def distribution_rows(scores, groups):
    return {
        label: {
            arm: {
                role: dict(
                    attempted=len(rows),
                    published=sum(r["error_km"] is not None for r in rows),
                    v5_available=sum(r["reference_available"] for r in rows),
                    within_5pct=sum(r["within_5pct"] for r in rows),
                    within_10pct=sum(r["within_10pct"] for r in rows),
                    error_km=distribution([r["error_km"] for r in rows]),
                )
                for role, method in METHODS.items()
                if (
                    rows := [
                        r
                        for r in scores
                        if (r["id"] in ids and r["arm"] == arm and r["method"] == method)
                    ]
                )
            }
            for arm in ARMS
        }
        for label, ids in groups.items()
    }


def old_pair(plan):
    sealed(earlier.REPORT, "prediction-lock.json", OLD_SIX)
    old = sealed(earlier.REPORT, OLD_PANEL)
    lock = whole_iq.read(earlier.REPORT / "source-lock.json")
    same_receiver(lock["receiver_files"], plan, Path(lock["receiver"]))
    shared = whole_iq.read(earlier.REPORT / "six-authority.json")
    if (
        lock["original_stock_sha256"] != plan["detectors"]["control"]["sha256"]
        or any(
            lock["assets"][role]["sha256"] != plan["detectors"][role]["sha256"]
            for role in ("candidate", "scout")
        )
        or lock["native_sources"] != plan["native_sources"]
        or any(plan["programs"].get(path) != digest for path, digest in shared["programs"].items())
        or set(old["cases"]) & plan["cases"].keys()
    ):
        raise ValueError(
            "previous six shared numerical method or disjointness is not authenticated"
        )
    paths = earlier.REPORT / "all-six-positions.jsonl.gz"
    rows = rows_from(paths)
    aliases = {earlier.CONTROL: trial.CONTROL, earlier.METHOD: trial.METHOD}
    return [dict(row, method=aliases[row["method"]], cohort="previous six") for row in rows], dict(
        original_prediction_lock_sha256=OLD_SIX,
        original_figure_lock_sha256=_sha(earlier.REPORT / OLD_PANEL),
        subset_native_authority_sha256=_sha(paths),
        previous_cases=old["cases"],
    )


def chart(out, key, title, ids, rows, files, extended):
    name = f"{key}-positions.jsonl.gz"
    pack(out / name, [r for r in rows if r["id"] in ids])
    figure_lock = f"{key}-figure-lock.json"
    save_json(
        out / figure_lock,
        dict(cases=ids, files={value: _sha(out / value) for value in [name, *files]}),
    )
    spec = dict(
        id=f"fresh-replay-{key}",
        method=trial.METHOD,
        scope="roof",
        cases="sealed",
        title=title,
        caption=(
            "Matched complete saved-IQ stock and genuine fifth-center replay, phase release, "
            "both calibration arms and original four capture-era v5 options. One roof."
        ),
        seal=figure_lock,
        provenance=files,
        series=[
            dict(
                key="one",
                file=name,
                value=trial.METHOD,
                label="Keep four + add fifth",
                native_field="paired_capture_sha256",
            ),
            dict(
                key="stock",
                file=name,
                value=trial.CONTROL,
                label="Stock wide",
                native_field="paired_capture_sha256",
                match=list(published.PHYSICAL_KEYS),
            ),
        ],
    )
    if extended:
        spec["roof_references"] = ROOF_REFERENCES
    return spec


def score(out):
    compact = sealed(out, "prediction-lock.json")
    plan = whole_iq.read(out / "source-lock.json")
    new = rows_from(out / POSITIONS)
    previous, old_seal = old_pair(plan)
    combined = previous + new
    groups = dict(
        new=compact["cases"],
        previous=old_seal["previous_cases"],
        eight=sorted({row["id"] for row in combined}),
    )
    (novel,) = [ident for ident in compact["cases"] if ident.startswith("DS29")]
    (ds26,) = [ident for ident in compact["cases"] if ident.startswith("DS26")]
    _, original = held_references(None, [ident for ident in groups["eight"] if ident != novel])
    refs = {row["id"]: row for row in original}
    refs[novel] = references(out, plan["cases"][novel])
    scores = geographic(combined, refs)
    csv_file(out / "scores.csv", [row for row in scores if row["id"] in set(compact["cases"])])
    csv_file(out / "eight-scores.csv", scores)
    save_json(out / "summary.json", distribution_rows(scores, groups))
    paired, _ = native.paired_scores(scores)
    csv_file(out / "calibration.csv", paired)
    save_json(out / "eight-authority.json", dict(old_seal, new=compact["cases"]))
    visits = [r for r in rows_from(out / VISITS) if r["status"] == "processed"]
    timing = timing_rows(whole_iq.read(out / "resources.json"), visits)
    csv_file(out / "deadlines.csv", timing)
    save_json(out / "visit-coverage.json", published.visit_coverage(visits))
    files = [
        "prediction-lock.json",
        "raw-prediction-lock.json",
        "reference-prediction-lock.json",
        "fresh-v5.jsonl.gz",
        "roof-authority.json",
        "scores.csv",
        "eight-authority.json",
        "eight-scores.csv",
        "summary.json",
        "calibration.csv",
        "deadlines.csv",
        "visit-coverage.json",
    ]
    charts = [
        chart(out, key, title, ids, combined, files, novel in ids)
        for key, ids, title in (
            (
                "all",
                compact["cases"],
                "Two genuinely new stock and fifth-center whole-IQ recordings",
            ),
            ("ds26", [ds26], f"Fresh whole-IQ stock and fifth-center on {ds26}"),
            ("ds29", [novel], f"Fresh whole-IQ on expanded DS29 recording {novel}"),
            ("eight", groups["eight"], "Eight distinct complete recordings from one roof"),
        )
    ]
    save_json(out / "figures.json", dict(version=1, charts=charts))
    screening_figures.generate(out / "charts", evidence=out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("raw-seal", "seal", "score"))
    parser.add_argument("--work", type=local_output, default=trial.WORK)
    parser.add_argument("--out", type=local_output, default=trial.REPORT)
    args = parser.parse_args()
    if args.mode == "score":
        score(args.out)
    elif args.mode == "raw-seal":
        raw_seal(args.work, args.out)
    else:
        seal(args.work, args.out)
