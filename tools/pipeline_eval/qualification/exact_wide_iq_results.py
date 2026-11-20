"""Audit exact saved-IQ science and physical timings after sealing iq_compare results."""

import argparse
import gzip
import io
import json
import tarfile
from hashlib import sha256
from itertools import zip_longest
from pathlib import Path

from .. import figure_books, whole_iq
from .. import iq_comparison_results as publication
from ..__main__ import ROOT, local_output, save_json
from ..scoring import ROLES, distribution
from . import exact_wide_iq as trial
from . import whole_winner_handoff as handoff
from .full_held_scores import held_references
from .full_receiver_comparison import require_fields, sha
from .winner_stream_results import csv_file, scientific_result

PREDICTIONS = "prediction-lock.json"
TRACES = "native-call-times.jsonl.gz"
NATIVE_PARITY = "native-parity.json"
COMPARE = "complete-comparison.csv"
SOURCES = "as-measured-source.tar.gz"


def encoded(value):
    return whole_iq.recording.encoded(value).encode()


def normalized_document(doc):
    """Omit only fields derived from which binary executed an otherwise exact replay."""
    source, provenance = dict(doc["source"]), dict(doc["provenance"])
    source.pop("analysis_manifest_sha256")
    for field in ("run_id", "detector_sha256"):
        provenance.pop(field)
    return dict(doc, source=source, provenance=provenance)


def detector_rows(path):
    if not (path / "raw.json").exists():
        return None
    raw = whole_iq.read(path / "raw.json")
    segments = {}
    pairs = []
    times = []
    for lane in range(2):
        lane_file = path / f"recording/replayed-{lane}.jsonl"
        measured = iter(raw["lanes"][lane]["native_timings_s"])
        seen = sha256()
        for visit in handoff.lane_rows(lane_file, lane, segments, seen):
            pairs.append(visit)
            if visit["status"] == "processed":
                timing = next(measured, None)
                if len(visit["probes"]) != 2 or timing is None:
                    raise ValueError(
                        "native-call timing or receiver order does not cover the visit"
                    )
                times.append(
                    dict(visit=visit["visit"], lane=lane, wall_s=timing[0], cpu_s=timing[1])
                )
            elif visit["status"] != "invalid_capture" or visit["probes"]:
                raise ValueError("raw visit status differs from the native recording contract")
        if next(measured, None) is not None or seen.hexdigest() != sha(lane_file):
            raise ValueError("unexpected detector timing or mutated raw message stream")
    if (
        len(pairs) != raw["counts"]["recording_windows"]
        or len(times) != raw["counts"]["processed_windows"]
    ):
        raise ValueError("native rows do not cover the complete capture")
    ordered = sorted(pairs, key=lambda row: row["visit"])
    if [item["visit"] for item in ordered] != list(range(len(ordered))):
        raise ValueError("raw replay did not cover every chronological visit exactly once")
    positions = path / "recording/native.json"
    whole_iq.checked(positions, raw["native_sha256"])
    norm = normalized_document(whole_iq.read(positions))
    return ordered, times, sha256(encoded(norm)).hexdigest()


def exact_visits(original, changed):
    hashes = [sha256(), sha256()]
    mismatch = []
    count = 0
    for index, paired in enumerate(zip_longest(original, changed)):
        control, candidate = (encoded(visit) if visit is not None else None for visit in paired)
        for digest, row in zip(hashes, (control, candidate), strict=True):
            if row is not None:
                digest.update(row + b"\n")
        if control != candidate:
            count += 1
            if len(mismatch) < 10:
                mismatch.append(index)
    return dict(
        compared_visits=max(len(original), len(changed)),
        mismatches=count,
        first_mismatched_visits=mismatch,
        visit_sha256={
            name: value.hexdigest()
            for name, value in zip(publication.BRANCHES, hashes, strict=True)
        },
    )


def audit(work, dest):
    pins = publication.sealed(dest)
    positions = list(
        map(json.loads, gzip.decompress((dest / "positions.jsonl.gz").read_bytes()).splitlines())
    )
    methods = {(r["id"], r["method"]): r["result"] for r in positions}
    audit, timings = {}, []
    for ident in pins["cases"]:
        observed = {role: detector_rows(work / ident / role) for role in publication.BRANCHES}
        if all(value is not None for value in observed.values()):
            stock, optimized = (observed[role] for role in publication.BRANCHES)
            science_stock, science_optimized = (
                methods[ident, publication.method(trial.METHOD, role)]
                for role in publication.BRANCHES
            )
            positions_exact = None
            if {science_stock["status"], science_optimized["status"]} == {"ok"}:
                positions_exact = encoded(scientific_result(science_stock)) == encoded(
                    scientific_result(science_optimized)
                )
            audit[ident] = dict(
                **exact_visits(stock[0], optimized[0]),
                valid_detector_calls=len(stock[1]),
                invalid_visits=len(stock[0]) - len(stock[1]),
                exact_detector_output_without_library_provenance=stock[2] == optimized[2],
                logical_native_sha256=dict(control=stock[2], candidate=optimized[2]),
                positions_exact=positions_exact,
            )
        else:
            audit[ident] = dict(
                frontends_complete={role: value is not None for role, value in observed.items()}
            )
        for role, value in observed.items():
            if value is not None:
                timings.extend(dict(item, id=ident, role=role) for item in value[1])
    save_json(dest / NATIVE_PARITY, audit)
    (dest / TRACES).write_bytes(gzip.compress(b"\n".join(map(encoded, timings)) + b"\n", mtime=0))


def as_measured(dest):
    lock = whole_iq.read(dest / "source-lock.json")
    require_fields(lock["spec"], {"selection_sha256": sha(dest / "selection.json")})
    native = dest / "native-release.json"
    if not native.exists():
        native.write_bytes(
            whole_iq.checked(trial.RELEASE, lock["spec"]["native_release_sha256"]).read_bytes()
        )
    whole_iq.checked(native, lock["spec"]["native_release_sha256"])
    receipt = dest / "native-build-receipt.json"
    build_sha = whole_iq.read(native)["build_receipt_sha256"]
    if not receipt.exists():
        receipt.write_bytes(
            whole_iq.checked(
                trial.RELEASE.parent / "candidate/build-receipt.json", build_sha
            ).read_bytes()
        )
    whole_iq.checked(receipt, build_sha)
    names = lock["programs"] | {
        str(Path(trial.__file__).relative_to(ROOT)): lock["spec"]["launcher_sha256"],
    }
    saved = dest / SOURCES
    if saved.exists():
        with tarfile.open(saved, mode="r:gz") as archive:
            for name, expected in names.items():
                data = archive.extractfile(name)
                if data is None or sha256(data.read()).hexdigest() != expected:
                    raise ValueError("archived exact-wide runner differs from the frozen source")
        return
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for name, expected in names.items():
            data = whole_iq.checked(ROOT / name, expected).read_bytes()
            info = tarfile.TarInfo(name)
            info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    saved.write_bytes(gzip.compress(buffer.getvalue(), mtime=0))


def timing_rows(resources, timings):
    table = []
    for ident, roles in resources.items():
        for role, measured in roles.items():
            sequence = [r for r in timings if r["id"] == ident and r["role"] == role]
            if sequence and len(sequence) != measured["dual_calls"]:
                raise ValueError("exact timing series differs from the sealed detector call count")
            windows = distribution([1000 * r["wall_s"] for r in sequence])
            cpu = distribution([1000 * r["cpu_s"] for r in sequence])
            stages = measured.get("stages", [])
            table.append(
                dict(
                    id=ident,
                    role=role,
                    service_status=measured["service"].get("systemd", {}).get("Result"),
                    calls=len(sequence),
                    wall_within_20ms=sum(row["wall_s"] <= 0.02 for row in sequence),
                    cpu_within_20ms=sum(row["cpu_s"] <= 0.02 for row in sequence),
                    **{f"call_wall_{key}_ms": windows[key] for key in ("p50", "p95", "p99", "max")},
                    **{f"call_cpu_{key}_ms": cpu[key] for key in ("p50", "p95", "p99", "max")},
                    detector_cpu_s=sum(row["cpu_s"] for row in sequence) if sequence else None,
                    raw_s=measured.get("raw_s"),
                    assembly_s=measured.get("assembly_s"),
                    position_s=measured.get("position_s"),
                    full_s=measured.get("wall_s"),
                    service_wall_s=measured["service"].get("supervisor_s"),
                    cpu_s=measured.get("cpu_s"),
                    peak_mib=measured["max_bytes"] / 2**20 if "max_bytes" in measured else None,
                    raw_cgroup_cpu_s=(
                        stages[1]["cpu.stat.usage_usec"] - stages[0]["cpu.stat.usage_usec"]
                    )
                    / 1e6
                    if stages
                    else None,
                    fit_cgroup_cpu_s=(
                        stages[3]["cpu.stat.usage_usec"] - stages[2]["cpu.stat.usage_usec"]
                    )
                    / 1e6
                    if len(stages) == 4
                    else None,
                    deadline_s=450,
                )
            )
    return table


def score(source, dest):
    pins = publication.sealed(source)
    if (source / "all-figure-lock.json").exists():
        figure = whole_iq.read(source / "all-figure-lock.json")
        whole_iq.checked(source / TRACES, figure["files"][TRACES])
    resources = whole_iq.read(source / "resources.json")
    rows = list(
        map(json.loads, gzip.decompress((source / "positions.jsonl.gz").read_bytes()).splitlines())
    )
    _, refs = held_references(None, pins["cases"])
    oracle = {row["id"]: row["reference"] for row in refs}
    scores = publication.score_rows(rows, resources, refs, trial.METHOD)
    for line in scores:
        for original in ROLES:
            line[original + "_km"] = oracle[line["id"]][original][line["arm"]]["error_km"]
    time = list(map(json.loads, gzip.decompress((source / TRACES).read_bytes()).splitlines()))
    dest.mkdir(exist_ok=True, parents=True)
    csv_file(dest / "scores.csv", scores)
    csv_file(dest / COMPARE, timing_rows(resources, time))
    return rows


def run(work, out):
    publication.seal(work, out)
    audit(work, out)
    as_measured(out)
    rows = score(out, out)
    source = whole_iq.read(out / "source-lock.json")
    spec = source["spec"]
    cases = list(source["cases"])
    chart = publication.chart(out, spec, spec["title"], "all", cases, rows)
    chart["provenance"].extend([NATIVE_PARITY, COMPARE, TRACES, "selection.json"])
    chart["source_lock"] = dict(file="source-lock.json", digest_key="source_lock_sha256")
    lock_path = out / chart["seal"]
    lock = whole_iq.read(lock_path)
    lock.update(source_lock_sha256=sha(out / "source-lock.json"))
    lock["files"].update(
        {
            p: sha(out / p)
            for p in (
                *chart["provenance"],
                SOURCES,
                "native-release.json",
                "native-build-receipt.json",
            )
        }
    )
    save_json(lock_path, lock)
    save_json(out / "figures.json", dict(version=1, charts=[chart]))
    figure_books.generate(out / "charts", ("c0", "fitted_c"), panel="screening", evidence=out)


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("action", choices=("publish", "score"))
    args.add_argument("source", type=local_output)
    args.add_argument("--out", type=local_output, default=trial.REPORT)
    options = args.parse_args()
    (run if options.action == "publish" else score)(options.source, options.out)
