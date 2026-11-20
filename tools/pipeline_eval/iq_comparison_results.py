"""Seal paired detector attempts and score each complete-waveform position."""

import gzip
import json
from pathlib import Path

from . import figure_books, whole_iq
from .__main__ import save_json, write
from .iq_compare import BRANCHES
from .qualification import whole_band_results as observed
from .qualification.full_held_scores import held_references
from .qualification.full_v5_check import _sha
from .qualification.phase_support_results import pack
from .qualification.prefix_figures import csv_file
from .scoring import ARMS, distance_km, distribution


def method(study_id, branch):
    return study_id + "_" + branch


def sealed(out):
    lock = whole_iq.read(out / "prediction-lock.json")
    for name, digest in lock["files"].items():
        whole_iq.checked(out / name, digest)
    return lock


def seal(work, out, *, keep_factors=False):
    source = whole_iq.checked(
        work / "source-lock.json", (work / "source-lock.sha256").read_text().strip()
    )
    plan = whole_iq.read(source)
    digest = _sha(source)
    if (out / "prediction-lock.json").exists():
        previous = sealed(out)
        if (
            previous["files"]["source-lock.json"] != digest
            or previous["keep_factors"] != keep_factors
        ):
            raise ValueError("a different study or factor export is already sealed here")
        return
    if (out / "source-lock.json").is_file():
        whole_iq.checked(out / "source-lock.json", digest)
    rows, resources, archives = [], {}, {}
    for case in plan["cases"]:
        pair = resources[case] = {}
        for branch in BRANCHES:
            attempt = work / case / branch / "plan.json"
            if attempt.is_file():
                actual = whole_iq.read(attempt)
                if (
                    actual["limit_s"] != plan["limit_s"]
                    or actual["native_sources"] != plan["native_sources"]
                ):
                    raise ValueError("service deadline or installed native sources differ")
            row, pair[branch], native = observed.attempt(
                work, case, branch, plan, method=method(plan["spec"]["id"], branch)
            )
            rows.append(row)
            if keep_factors and native is not None:
                archives[f"native/{branch}/{case}.json.gz"] = native
        if all("raw_authority" in pair[b] for b in BRANCHES):
            observed.pair_geometry(pair["control"], pair["candidate"])
    write(out / "source-lock.json", source.read_bytes())
    pack(out / "positions.jsonl.gz", rows)
    save_json(out / "resources.json", resources)
    for name, native in archives.items():
        write(out / name, gzip.compress(native.read_bytes(), compresslevel=6, mtime=0))
    files = ["source-lock.json", "positions.jsonl.gz", "resources.json", *archives]
    save_json(
        out / "prediction-lock.json",
        dict(
            cases=list(plan["cases"]),
            files={name: _sha(out / name) for name in files},
            keep_factors=keep_factors,
            publisher_sha256=_sha(Path(__file__)),
        ),
    )


def score_rows(rows, resources, references, study_id):
    by_id = {ref["id"]: ref for ref in references}
    branches = {method(study_id, branch): branch for branch in BRANCHES}
    scores = []
    for row in rows:
        case = row["id"]
        branch = branches[row["method"]]
        ref, measurement = by_id[case], resources[case][branch]
        for arm in ARMS:
            estimate = row["result"]["arms"][arm]
            original = ref["reference"]["baseline"][arm]
            error = distance_km(ref["truth"], estimate["latlon"])
            v5 = original.get("error_km")
            scores.append(
                dict(
                    id=case,
                    cohort=row["cohort"],
                    branch=branch,
                    arm=arm,
                    status=row["result"]["status"],
                    published=error is not None,
                    error_km=error,
                    original_v5_km=v5,
                    within_5pct=None if v5 is None else error is not None and error <= 1.05 * v5,
                    within_10pct=None if v5 is None else error is not None and error <= 1.10 * v5,
                    conditional_rms_hz=estimate.get("rf_rms_hz"),
                    original_v5_rms_hz=original.get("rf_rms_hz"),
                    conditional_frequency_score=row["result"]["metrics"].get(
                        arm + "_frequency_score"
                    ),
                    wall_s=measurement.get("wall_s"),
                    cpu_s=measurement.get("cpu_s"),
                    raw_s=measurement.get("raw_s"),
                    position_s=measurement.get("position_s"),
                    wall_to_failure_s=measurement.get("wall_to_failure_s"),
                    cpu_to_failure_s=measurement.get("cpu_to_failure_s"),
                    positive_candidates=measurement.get("counts", {}).get("positive_candidates"),
                    valid_visits=measurement.get("dual_calls"),
                )
            )
    return scores


def chart(out, spec, title, suffix, cases, rows):
    identifier = spec["id"] + "-" + suffix
    name = "positions.jsonl.gz" if suffix == "all" else suffix + ".jsonl.gz"
    if suffix != "all":
        pack(out / name, [row for row in rows if row["id"] in cases])
    provenance = ["prediction-lock.json", "resources.json", "scores.csv"]
    lock = suffix + "-figure-lock.json"
    save_json(out / lock, dict(cases=cases, files={p: _sha(out / p) for p in [name, *provenance]}))
    series = []
    for branch, key in (("candidate", "one"), ("control", "stock")):
        entry = dict(
            key=key,
            label=spec[branch]["label"],
            file=name,
            value=method(spec["id"], branch),
            native_authority="frozen",
            native_field="paired_capture_sha256",
        )
        if branch == "control":
            entry["match"] = ["tile", "catalog_sha256", "original_request_sha256", "mode"]
        series.append(entry)
    return dict(
        id=identifier,
        method=method(spec["id"], "candidate"),
        scope="roof",
        cases=cases,
        title=title,
        caption=spec["caption"],
        seal=lock,
        provenance=provenance,
        series=series,
    )


def publish(out):
    pins = sealed(out)
    source = whole_iq.read(out / "source-lock.json")
    spec = source["spec"]
    with gzip.open(out / "positions.jsonl.gz", "rt") as stream:
        rows = [json.loads(line) for line in stream]
    _, refs = held_references(None, pins["cases"])
    scores = score_rows(rows, whole_iq.read(out / "resources.json"), refs, spec["id"])
    csv_file(out / "scores.csv", scores)
    panels = [dict(id="all", title=spec["title"])] + spec.get("additional_panels", [])
    summary, charts = {}, []
    for panel in panels:
        cases = [
            case
            for case in pins["cases"]
            if not panel.get("cohort") or panel["cohort"] == source["cases"][case]["cohort"]
        ]
        charts.append(chart(out, spec, panel["title"], panel["id"], cases, rows))
        results = summary[panel["id"]] = {}
        for branch in BRANCHES:
            for arm in ARMS:
                sample = [
                    s
                    for s in scores
                    if s["branch"] == branch and s["arm"] == arm and s["id"] in cases
                ]
                results[branch + "_" + arm] = dict(
                    attempts=len(sample),
                    published=sum(s["published"] for s in sample),
                    v5_comparable=sum(s["original_v5_km"] is not None for s in sample),
                    within_5pct=sum(s["within_5pct"] is True for s in sample),
                    within_10pct=sum(s["within_10pct"] is True for s in sample),
                    **{
                        k: distribution([s[k] for s in sample if s[k] is not None])
                        for k in ("error_km", "conditional_rms_hz", "wall_s", "cpu_s")
                    },
                )
    save_json(out / "summary.json", summary)
    save_json(out / "figures.json", dict(version=1, charts=charts))
    figure_books.generate(out / "charts", ("fitted_c", "c0"), panel="screening", evidence=out)
