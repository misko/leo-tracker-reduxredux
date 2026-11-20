"""Seal standard figures from actual portable launches and their audited controls."""

import argparse
import gzip
import json
from collections import Counter
from pathlib import Path

from .. import corpus
from ..__main__ import encoded, local_output, read_predictions, save_json, write
from ..scoring import validate_result
from ..variants import lean_receiver_cli as app
from .screening_figures import _sealed_bytes

ROOT = corpus.REPO
SCREEN = ROOT / "reports/2026_11_19_receiver_screening"
REPORT = SCREEN / "refinement/portable-worker"
PARENTS = {
    "native-full": "native_joint_orbits",
    "native-clock-full": "native_joint_clock_model",
    "iq-to-joint": "iq_to_joint",
}
INPUTS = ("input_sha256", "native_sha256", "catalog_sha256", "observation_sha256", "tile")
METHOD = {"joint": "portable_native_joint", "smooth-clock": "portable_native_clock"}
ROSTER = {
    ("native-full", "DS26-0036"): ("joint", "capture-era"),
    ("iq-to-joint", "DS26-0036"): ("joint", "ordinary"),
    ("iq-to-joint", "DS29-0082"): ("joint", "ordinary"),
    ("native-clock-full", "DS29-0082"): ("smooth-clock", "capture-era"),
    ("native-clock-full", "DS26-0036-r0"): ("smooth-clock", "omitted-tile"),
}


def read(path):
    return json.loads(path.read_bytes())


def sha(path):
    return app.hex_sha(path.read_bytes())


def check_fields(actual, expected, name):
    if changed := [key for key, value in expected.items() if actual.get(key) != value]:
        raise ValueError(f"{name} changes sealed fields {', '.join(changed)}")


def parent_archive(study, link):
    folder = SCREEN / "factors" / study
    name, lock_name = "positions.jsonl.gz", "prediction-lock.json"
    lock = read(folder / lock_name)
    check_fields(
        link,
        dict(
            prediction=str((folder / name).relative_to(ROOT)),
            receipt=str((folder / lock_name).relative_to(ROOT)),
            prediction_sha256=lock["files"][name],
            receipt_sha256=sha(folder / lock_name),
        ),
        study,
    )
    for sealed in lock["files"]:
        _sealed_bytes(folder, lock, sealed)
    rows = read_predictions(folder / name)
    if study == "iq-to-joint":
        if sha(folder / "source-lock.json") != lock["source_lock_sha256"]:
            raise ValueError("the ordinary parent uses a different frozen source lock")
        stages = read(folder / "stage-receipts.json")
        requests = {ident: stage["native_query"] for ident, stage in stages.items()}
        check_fields(
            {i: r["source_lock_sha256"] for i, r in rows.items()},
            dict.fromkeys(rows, lock["source_lock_sha256"]),
            study,
        )
    else:
        requests = {query["id"]: query["packet"] for query in read(folder / "plan.json")["cases"]}
    if Counter(lock["cases"]) != Counter(rows.keys()) or rows.keys() != requests.keys():
        raise ValueError(f"{study} changes the parent recording roster")
    return rows, requests


def matched_pair(replay, archived, request, solver, cohort, study):
    """Validate both scientific outputs before constructing the two plot series."""
    ident = replay["id"]
    receipt_inputs = {key: request[key]["sha256"] for key in app.FILES}
    digest = app.hex_sha(encoded(request))
    check_fields(
        archived,
        dict(
            id=ident,
            method=PARENTS[study],
            tile=request["offer"],
            input_sha256=digest,
            native_sha256=receipt_inputs["native"],
            catalog_sha256=receipt_inputs["catalogue"],
        ),
        ident,
    )
    binding = {key: archived[key] for key in INPUTS}
    measured = archived["result"]
    decisions = {key: measured.get(key) for key in ("status", "reason", "arms")}
    check_fields(
        replay,
        dict(
            decisions,
            solver=solver,
            verified_against=study,
            sealed_science_match=True,
            tile=request["offer"],
            input_sha256=digest,
            input_files_sha256=receipt_inputs,
            cutoff_utc_ns=request["cutoff"],
            catalogue_acquired_utc_ns=request["catalog_timestamp"],
            observation_sha256=archived["observation_sha256"],
            interface_sha256=app.hex_sha(
                encoded(
                    dict(request=request, solver=solver, capture_utc_ns=replay["capture_utc_ns"])
                )
            ),
        ),
        ident,
    )
    if (
        not replay["worker_wall_s"] > 0
        or replay["address_space_limit_mib"] != 512
        or not 0 < replay["memory_kib"]["VmPeak"] <= 512 * 1024
        or replay["status"] not in ("ok", "withheld")
    ):
        raise ValueError(f"{ident} does not attest a completed native worker")
    actual = dict({key: replay[key] for key in decisions}, boundary=app.BOUNDARY, metrics={})
    validate_result(actual)
    shared = dict(id=ident, recording=archived["recording"], cohort=cohort, **binding)
    return (
        dict(
            shared,
            result=actual,
            method=METHOD[solver],
            source_sha256=replay["source_sha256"],
            interface_sha256=replay["interface_sha256"],
            parent_method=archived["method"],
            parent_study=study,
            worker_wall_s=replay["worker_wall_s"],
        ),
        dict(shared, result=measured, method=archived["method"], parent_study=study),
    )


def verify():
    lock = read(REPORT / "prediction-lock.json")
    for name in lock["files"]:
        _sealed_bytes(REPORT, lock, name)
    study = read(REPORT / "parity.json")
    deployment = read(REPORT / "deployment.json")
    if any(deployment[solver] != app.source_manifest(solver) for solver in METHOD):
        raise ValueError("portable parity differs from the packaged source")
    replays = [(r["verified_against"], r["id"]) for r in study["replays"]]
    if Counter(replays) != Counter(ROSTER.keys()) or set(study["benchmarks"]) != PARENTS.keys():
        raise ValueError("portable parity changes the measured roster or parent archives")
    parents = {name: parent_archive(name, link) for name, link in study["benchmarks"].items()}
    rows = []
    for (name, ident), replay in zip(replays, study["replays"], strict=True):
        solver, cohort = ROSTER[name, ident]
        check_fields(replay, {"source_sha256": app.hex_sha(encoded(deployment[solver]))}, ident)
        stock, requests = parents[name]
        rows.extend(matched_pair(replay, stock[ident], requests[ident], solver, cohort, name))
    return rows, study["benchmarks"], lock


def omitted_query(row):
    folder = SCREEN / "factors/native-clock-full"
    name = "omitted-queries.json"
    lock = read(folder / "omitted-figure-lock.json")
    rows = json.loads(_sealed_bytes(folder, lock, name))["queries"]
    (query,) = (item for item in rows if item["id"] == row["id"])
    check_fields(row, query["bindings"], row["id"])
    check_fields(query, dict(recording=row["recording"]), row["id"])
    return dict(query, bindings={key: row[key] for key in INPUTS})


def figures(output):
    rows, parents, lock = verify()
    name = "figure-positions.jsonl.gz"
    write(output / name, gzip.compress(b"".join(encoded(row) + b"\n" for row in rows), mtime=0))
    report = "figure-verification.json"
    save_json(
        output / report,
        dict(
            inputs=lock["files"],
            parent_archives=parents,
            verifier_sha256=sha(Path(__file__)),
            exact_fields=[*INPUTS, "status", "reason", "arms"],
            prepared_only_numerical_attempts=0,
        ),
    )
    files = {key: sha(output / key) for key in (name, report)}
    definitions = (
        ("joint", "capture-era", "Portable joint on capture-era GLRT", "native-full"),
        ("joint", "ordinary", "Portable joint on ordinary GLRT", "iq-to-joint"),
        (
            "smooth-clock",
            "capture-era",
            "Portable smooth clock on capture-era GLRT",
            "native-clock-full",
        ),
        (
            "smooth-clock",
            "omitted-tile",
            "Portable smooth clock with the correct tile omitted",
            "native-clock-full",
        ),
    )
    charts = []
    for solver, cohort, title, parent in definitions:
        method = METHOD[solver]
        candidate = [row for row in rows if row["method"] == method and row["cohort"] == cohort]
        cases = [row["id"] for row in candidate]
        omitted = cohort == "omitted-tile"
        ordinary = dict(native_authority="ordinary") if cohort == "ordinary" else {}
        source = dict(where=dict(cohort=cohort), file=name, **ordinary)
        receipt = f"{method}-{cohort}-lock.json"
        caption = (
            "The portable launch and audited parent used identical complete GLRT factors, "
            "catalogue, Graph and position fit. The chart shows deployment parity."
        )
        if cohort == "ordinary":
            caption += " The original v5 references use capture-era factors."
        chart = dict(
            id=f"{method}-{cohort}",
            method=method,
            cases=cases,
            title=title,
            caption=caption,
            scope="transfer" if omitted else "roof",
            seal=receipt,
            provenance=[report],
            series=[
                dict(
                    key="candidate" if omitted else "one",
                    label="Portable launch",
                    value=method,
                    **source,
                ),
                dict(
                    key="stock",
                    label="Audited parent",
                    value=PARENTS[parent],
                    match=list(INPUTS),
                    **source,
                ),
            ],
        )
        sealed = dict(files)
        if omitted:
            chart["queries"] = "figure-omitted-query.json"
            save_json(output / chart["queries"], dict(queries=[omitted_query(candidate[0])]))
            sealed[chart["queries"]] = sha(output / chart["queries"])
        save_json(output / receipt, dict(cases=cases, files=sealed))
        charts.append(chart)
    save_json(output / "figures.json", dict(version=1, charts=charts))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=REPORT)
    figures(local_output(parser.parse_args().out))


if __name__ == "__main__":
    main()
