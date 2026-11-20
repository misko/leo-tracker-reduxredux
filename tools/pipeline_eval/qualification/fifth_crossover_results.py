"""Seal and score matched stock, fourth-replacement and fifth-union whole-IQ arms."""

import argparse
import gzip
from collections import Counter
from hashlib import sha256
from pathlib import Path

from .. import iq_service, whole_iq
from ..__main__ import local_output, save_json, write
from ..scoring import ARMS, distribution
from . import diagnostic_whole_results as prior
from . import fifth_crossover as study
from . import frontier_whole_replay_results as traces
from . import screening_figures
from . import whole_band_results as measured
from . import whole_center_union_results as union
from .exact_wide_iq_results import timing_rows
from .full_held_scores import held_references
from .full_v5_check import _sha
from .phase_support_results import pack
from .prefix_figures import csv_file
from .whole_pressure_trial import rows_from
from .wide_roster_results import same_receiver

ROLE_METHOD = {"control": study.CONTROL, "replace": study.REPLACE, "union": study.METHOD}
NATIVE_METHOD = {
    prior.trial.BASELINE: "control",
    prior.trial.METHOD: "replace",
    "frontier-whole-iq_control": "control",
    study.whole_fftw_trial.METHOD: "replace",
}
POSITION = "positions.jsonl.gz"
TRACE = "new-union-visits.jsonl.gz"
FRESH_PIN = "14ab3e27d00c79c090896a55c6d9340fe6eb2c99077d59ddfbc0f4d0a1a31c6a"
FRESH_CASES = {"DS26-0197", "DS29-0316"}


def load_study(folder, digest):
    seal, plan = study.checked_parent(folder, digest)
    for name, checksum in seal["files"].items():
        whole_iq.checked(folder / name, checksum)
    return (
        seal,
        plan,
        whole_iq.read(folder / "resources.json"),
        rows_from(folder / POSITION),
        rows_from(folder / "visits.jsonl.gz"),
    )


def historical_inputs(plan):
    held = study.whole_fftw_trial
    inputs = [
        (
            study.diagnostic.REPORT,
            study.DIAGNOSTIC_PIN,
            {"control": "control", "candidate": "replace"},
        ),
        (held.REPORT, study.HELD_FFTW_PIN, {"fftw": "replace"}),
        (held.prior.REPORT, study.HELD_STOCK_PIN, {"control": "control"}),
    ]
    positions, resources, visits, native_raw, read_sources = {}, {}, {}, {}, {}
    for path, digest, translate in inputs:
        seal, source, measurements, position_rows, trace_rows = load_study(path, digest)
        same_receiver(source["receiver_files"], plan, Path(source["receiver"]))
        if source["native_sources"] != plan["native_sources"]:
            raise ValueError("historical compact receiver compiler inputs changed")
        read_sources[path.name] = dict(prediction_sha256=digest, cases=seal["cases"])
        for row in position_rows:
            role = NATIVE_METHOD.get(row["method"])
            if role not in translate.values():
                continue
            ident = row["id"]
            current, frozen = plan["cases"][ident], source["cases"][ident]
            if any(
                current[key] != frozen[key]
                for key in (
                    "recording",
                    "request_sha256",
                    "clock_authority",
                    "orbit_snapshots",
                    "tile",
                )
            ):
                raise ValueError("historical captures change the current original request")
            key = ident, role
            positions[key] = dict(row, method=ROLE_METHOD[role], cohort=current["cohort"])
            branch = next(old for old, new in translate.items() if new == role)
            resource = resources[key] = measurements[ident][branch]
            expected = plan[
                "original_stock_sha256" if role == "control" else "original_overwrite_sha256"
            ]
            if resource["detector_sha256"] != expected or not iq_service.succeeded(
                resource["service"]
            ):
                raise ValueError("the distinct historical detector service is unavailable")
            limit = (
                source.get("stock_limit_s", source["limit_s"])
                if role == "control"
                else source["limit_s"]
            )
            resources[key] = dict(resource, planned_deadline_s=limit)
            native_raw[key] = native_authority(path, seal, row, resource, role)
        for visit in trace_rows:
            if visit["role"] in translate:
                key = visit["id"], translate[visit["role"]]
                visits.setdefault(key, []).append(dict(visit, role=key[1]))
    expected = {(ident, role) for ident in plan["cases"] for role in ("control", "replace")}
    if positions.keys() != expected or resources.keys() != expected or visits.keys() != expected:
        raise ValueError(
            "each prerecorded comparison needs a genuine paired stock and replacement arm"
        )
    return positions, resources, visits, native_raw, read_sources


def native_authority(path, seal, row, resource, role):
    ident = row["id"]
    if role == "replace":
        name = f"native/{ident}.json.gz"
        archive = whole_iq.checked(path / name, seal["files"][name])
    elif path == study.diagnostic.REPORT:
        frozen, _ = study.diagnostic.stock_sources()
        name = f"native/control/{ident}.json.gz"
        archive = whole_iq.checked(study.diagnostic.STOCK / name, frozen["files"][name])
    else:
        binding = resource["service"]["binding"]
        directory = Path(binding["attempt"])
        whole_iq.checked(directory / "plan.json", binding["plan_sha256"])
        archive = whole_iq.checked(directory / "recording/native.json", row["native_sha256"])
    data = archive.read_bytes()
    if archive.suffix == ".gz":
        data = gzip.decompress(data)
    if sha256(data).hexdigest() != row["native_sha256"]:
        raise ValueError("historical native factor digest changed")
    return dict(native_sha256=row["native_sha256"], archive=str(archive))


def compare_hints(older, newer):
    counts = Counter()
    for old, new in zip(older, newer, strict=True):
        if old["visit_metadata_sha256"] != new["visit_metadata_sha256"]:
            raise ValueError("the detector inputs differ at a physical visit")
        if old["status"] == "processed":
            a = old["differential"]["hints"]
            b = new["differential"]["hints"]
            if a != b:
                raise ValueError("the old and new policy selected different FFTW hints")
            counts["matched_dual_calls"] += 1
            counts["matched_hints"] += sum(hint is not None for hint in a)
            counts["historical_changed_receivers"] += sum(old["differential"]["changed"])
            counts["union_changed_receivers"] += sum(new["differential"]["changed"])
    return dict(counts)


def seal(work, out):
    if (out / "prediction-lock.json").exists():
        raise FileExistsError("crossover predictions already sealed")
    plan = study.source(work)
    older, old_stats, past_calls, lineage, parents = historical_inputs(plan)
    rows, measurements, new_calls, paired, files = [], {}, [], {}, []
    files.append("historical-authority.json")
    save_json(
        out / files[0],
        dict(
            parents=parents,
            native={f"{ident}/{role}": v for (ident, role), v in lineage.items()},
        ),
    )
    for ident, scheduled in plan["cases"].items():
        folder = work / ident / "candidate"
        fifth, receipt, native = measured.attempt(
            work, ident, "candidate", plan, method=study.METHOD
        )
        resources = measurements[ident] = {
            role: old_stats[ident, role] for role in ("control", "replace")
        }
        resources["union"] = dict(receipt, planned_deadline_s=plan["limit_s"])
        stock, replace = (older[ident, role] for role in ("control", "replace"))
        for key in (*prior.PHYSICAL_KEYS, "mode"):
            if stock[key] != replace[key] or stock[key] != fifth[key]:
                raise ValueError(
                    "crossover branches disagree on original tile, recording or request"
                )
        prior.matched_physical(resources["control"], resources["replace"], scheduled)
        rows.extend((stock, replace, fifth))
        audit = paired[ident] = dict(full_new_raw=native is not None)
        old_stock, old_replace = (past_calls[ident, role] for role in ("control", "replace"))
        audit["stock_vs_fourth_replace"] = traces.compare_probes(old_stock, old_replace)
        if native is not None:
            prior.matched_physical(resources["control"], receipt, scheduled)
            _, actual = prior.trace_bundle(ident, "union", folder, receipt)
            audit["native_scout"] = traces.scout_trace(folder, actual)
            audit["fifth_admissions"] = union.union_telemetry(actual)
            audit["exact_common_scout"] = compare_hints(old_replace, actual)
            audit["stock_vs_fifth"] = traces.compare_probes(old_stock, actual)
            audit["fourth_replace_vs_fifth"] = traces.compare_probes(old_replace, actual)
            new_calls.extend(actual)
            name = f"native/{ident}.json.gz"
            write(out / name, gzip.compress(native.read_bytes(), mtime=0))
            files.append(name)
        log = folder / "service.log"
        if log.is_file():
            whole_iq.checked(log, receipt["service"]["log_sha256"])
            name = f"{ident}.service.log"
            write(out / name, log.read_bytes())
            files.append(name)
    traces.protect_resources(measurements)
    calls = [r for batch in past_calls.values() for r in batch] + new_calls
    timing = timing_rows(measurements, [r for r in calls if r["status"] == "processed"])
    for row in timing:
        entry = measurements[row["id"]][row["role"]]
        row["deadline_s"] = entry["planned_deadline_s"]
        row["service_wall_s"] = entry["service"].get("service_wall_s")
        row["wall_to_failure_s"] = entry.get("wall_to_failure_s")
        row["cpu_to_failure_s"] = entry.get("cpu_to_failure_s")
    csv_file(out / "deadlines.csv", timing)
    pack(out / POSITION, rows)
    pack(out / TRACE, new_calls)
    save_json(out / "resources.json", measurements)
    save_json(out / "probe-audit.json", paired)
    files.extend(
        (
            POSITION,
            TRACE,
            "resources.json",
            "probe-audit.json",
            "deadlines.csv",
            "PROTOCOL.md",
            "source-lock.json",
        )
    )
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=list(plan["cases"]),
            files={f: _sha(out / f) for f in files},
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def chart(out, name, ids, rows, files, title, caption, *, two_policy=False):
    file = POSITION if name == "all" else f"{name}-positions.jsonl.gz"
    if name != "all":
        pack(out / file, [r for r in rows if r["id"] in ids])
    lock = f"{name}-figure-lock.json"
    save_json(out / lock, dict(cases=ids, files={f: _sha(out / f) for f in [file, *files]}))
    pair = ["tile", "mode", "original_request_sha256", "catalog_sha256", "paired_capture_sha256"]
    series = [
        dict(
            key="one",
            file=file,
            value=study.METHOD,
            label="Keep four + add fifth",
            native_field="paired_capture_sha256",
        ),
        dict(
            key="stock",
            file=file,
            value=study.CONTROL,
            label="Stock four starts",
            native_field="paired_capture_sha256",
            match=pair,
        ),
    ]
    if not two_policy:
        series.append(
            dict(
                key="one_native_factors",
                file=file,
                value=study.REPLACE,
                label="Replace fourth",
                native_field="paired_capture_sha256",
                match=pair,
            )
        )
    prefix = "fifth-center" if two_policy else "fifth-crossover"
    return dict(
        id=f"{prefix}-{name}",
        title=title,
        caption=caption,
        method=study.METHOD,
        scope="roof",
        cases="sealed",
        seal=lock,
        provenance=files,
        series=series,
    )


def summary(groups, scores, roles=ROLE_METHOD):
    grouped = {}
    for name, ids in groups.items():
        grouped[name] = {}
        for arm in ARMS:
            grouped[name][arm] = {}
            for role, method in roles.items():
                data = [
                    r
                    for r in scores
                    if r["id"] in ids and r["arm"] == arm and r["method"] == method
                ]
                grouped[name][arm][role] = dict(
                    attempted=len(data),
                    published=sum(r["error_km"] is not None for r in data),
                    within_5pct=sum(r["within_5pct"] for r in data),
                    within_10pct=sum(r["within_10pct"] for r in data),
                    error_km=distribution([r["error_km"] for r in data]),
                )
    return grouped


def six_recording_charts(out, current, historical_rows, files):
    fresh_folder = study.union.REPORT
    fresh_seal, fresh = study.checked_parent(fresh_folder, FRESH_PIN)
    for name, digest in fresh_seal["files"].items():
        whole_iq.checked(fresh_folder / name, digest)
    if set(fresh_seal["cases"]) != FRESH_CASES or FRESH_CASES.intersection(current["cases"]):
        raise ValueError("six-recording pooled request changed the separate fixed cohorts")
    active = whole_iq.read(fresh_folder / study.activation.PIN)
    same_receiver(fresh["receiver_files"], current, Path(fresh["receiver"]))
    if (
        any(
            active["assets"][role]["sha256"] != current["assets"][role]["sha256"]
            for role in ("candidate", "scout")
        )
        or fresh["detectors"]["control"]["sha256"] != current["original_stock_sha256"]
        or fresh["native_sources"] != current["native_sources"]
        or any(
            current["programs"].get(path) != digest for path, digest in active["sources"].items()
        )
        or any(fresh[key] != current[key] for key in ("memory_max", "swap_max", "limit_s"))
    ):
        raise ValueError("new and retrospective fifth-center programs or resource caps differ")
    aliases = {study.union.METHOD: study.METHOD, study.union.BASELINE: study.CONTROL}
    measurements = whole_iq.read(fresh_folder / "resources.json")
    complete = rows_from(fresh_folder / POSITION)
    if {(r["id"], r["method"]) for r in complete} != {
        (ident, method) for ident in FRESH_CASES for method in aliases
    }:
        raise ValueError("fresh prediction rows are not the two fixed recording pairs")
    for ident in FRESH_CASES:
        current_group = measurements[ident]
        if all(role.get("counts") for role in current_group.values()):
            prior.matched_physical(
                current_group["control"],
                current_group["candidate"],
                fresh["cases"][ident],
            )
    combined = [
        dict(r, cohort="retrospective crossover")
        for r in historical_rows
        if r["method"] != study.REPLACE
    ] + [dict(r, cohort="fresh manifest-selected", method=aliases[r["method"]]) for r in complete]
    all_ids = sorted(set(current["cases"]) | FRESH_CASES)
    _, refs = held_references(None, all_ids)
    scored = prior.geographic(combined, {r["id"]: r for r in refs})
    groups = {
        "all-six": all_ids,
        "retrospective-four": sorted(current["cases"]),
        "fresh-two": sorted(FRESH_CASES),
    }
    csv_file(out / "six-scores.csv", scored)
    roles = {key: value for key, value in ROLE_METHOD.items() if key != "replace"}
    save_json(out / "six-summary.json", summary(groups, scored, roles))
    save_json(
        out / "six-authority.json",
        dict(
            fresh_predictions=FRESH_PIN,
            retrospective_predictions=_sha(out / "prediction-lock.json"),
            native_assets={k: v["sha256"] for k, v in active["assets"].items()},
            programs=active["sources"],
            compact_sha256=current["receiver_files"],
            groups=groups,
        ),
    )
    evidence = [
        *files,
        "SIX-RECORDINGS.md",
        "six-authority.json",
        "six-scores.csv",
        "six-summary.json",
    ]
    labels = {
        "all-six": "Stock and genuine fifth center across six complete roof recordings",
        "retrospective-four": "Stock and fifth center on four retrospective recordings",
        "fresh-two": "Stock and fifth center on two newly selected recordings",
    }
    caption = (
        "One roof. Four retrospective recordings and two independently "
        "manifest-selected recordings. Matched compact release and 25 km tiles. "
        "Original v5 policies use capture-era factors."
    )
    return [
        chart(out, name, ids, combined, evidence, labels[name], caption, two_policy=True)
        for name, ids in groups.items()
    ]


def score(out):
    lock = whole_iq.read(out / "prediction-lock.json")
    for name, digest in lock["files"].items():
        whole_iq.checked(out / name, digest)
    plan = whole_iq.read(out / "source-lock.json")
    rows = rows_from(out / POSITION)
    _, refs = held_references(None, lock["cases"])
    scored = prior.geographic(rows, {r["id"]: r for r in refs})
    csv_file(out / "scores.csv", scored)
    groups = dict(
        all=lock["cases"],
        development=[
            i for i in lock["cases"] if plan["cases"][i]["cohort"] == "development diagnostic"
        ],
        held=[i for i in lock["cases"] if plan["cases"][i]["cohort"] == "previous held"],
    )
    save_json(out / "summary.json", summary(groups, scored))
    paired, _ = union.paired_scores(scored)
    csv_file(out / "calibration.csv", paired)
    files = [
        "prediction-lock.json",
        "historical-authority.json",
        "scores.csv",
        "calibration.csv",
        "deadlines.csv",
        "summary.json",
        "probe-audit.json",
    ]
    titles = {
        "all": "Stock, replace fourth, and add a fifth on four complete recordings",
        "development": "Three timing-center policies on two development recordings",
        "held": "Three timing-center policies on two previous manifest-held recordings",
    }
    detail = (
        "Complete recorded IQ, matched compact phase release, original tile. "
        "Stock and replace-fourth timings come from earlier services. "
        "Four capture-era v5 policies are shown. All recordings come from one roof."
    )
    charts = six_recording_charts(out, plan, rows, files)
    charts.extend(
        chart(out, key, ids, rows, files, titles[key], detail) for key, ids in groups.items()
    )
    save_json(out / "figures.json", dict(version=1, charts=charts))
    screening_figures.generate(out / "charts", evidence=out)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("seal", "score"))
    parser.add_argument("--work", type=local_output, default=study.WORK)
    parser.add_argument("--out", type=local_output, default=study.REPORT)
    args = parser.parse_args()
    if args.mode == "seal":
        seal(args.work, args.out)
    else:
        score(args.out)
