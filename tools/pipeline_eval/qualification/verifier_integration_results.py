"""Audit genuine original schedules, native factors, and resident detector resource pairs."""

import argparse
import gzip
import json
import subprocess
from collections import Counter
from pathlib import Path
from statistics import median

from .. import whole_iq
from ..__main__ import local_output, save_json, write
from ..variants import verifier_integration
from . import verifier_integration_trial as trial
from .full_v5_check import _sha

TOLERANCES = dict(hz=1e-6, samples=2e-9, score=5e-12)


def tolerance(key):
    if key.endswith("_hz"):
        return TOLERANCES["hz"]
    if "sample" in key:
        return TOLERANCES["samples"]
    return TOLERANCES["score"]


def differences(original, actual):
    deltas, mismatches = {}, []

    def observe(a, b, path, leaf):
        if type(a) is not type(b):
            mismatches.append(dict(path=path, expected=a, observed=b, reason="type"))
        elif isinstance(a, dict):
            if a.keys() != b.keys():
                mismatches.append(
                    dict(path=path, expected=sorted(a), observed=sorted(b), reason="keys")
                )
            for key in sorted(a.keys() & b.keys()):
                observe(a[key], b[key], f"{path}.{key}", key)
        elif isinstance(a, (list, tuple)):
            if len(a) != len(b):
                mismatches.append(
                    dict(path=path, expected=len(a), observed=len(b), reason="length")
                )
            for i, (left, right) in enumerate(zip(a, b, strict=False)):
                observe(left, right, f"{path}[{i}]", leaf)
        elif isinstance(a, float):
            delta = abs(a - b)
            deltas[leaf] = max(deltas.get(leaf, 0), delta)
            if not delta <= tolerance(leaf):
                mismatches.append(dict(path=path, expected=a, observed=b, reason="numeric"))
        elif a != b:
            mismatches.append(dict(path=path, expected=a, observed=b, reason="discrete"))

    observe(original, actual, "$", "")
    return dict(
        bitwise_equal=original == actual, max_absolute_float_delta=deltas, mismatches=mismatches
    )


def attempts(row):
    return [(call["receiver"], call["anchors"]) for call in row["trace"]["scheduler"]]


def seed_mismatches(reference, actual):
    mismatches = []
    expected = reference["trace"]["scheduler"]
    routes = actual["trace"]["native"]
    if len(expected) != len(routes):
        return [dict(expected_count=len(expected), observed_count=len(routes))]
    for index, (stock, native) in enumerate(zip(expected, routes, strict=True)):
        grids = stock["original_grids"]
        selected = [seed[:3] for seed in native["seeds"]]
        if not selected and native["route"] != "empty":
            continue
        if len(grids) > len(selected) and selected:
            period = len(selected)
            if len(grids) % period == 0 and grids == grids[:period] * (len(grids) // period):
                grids = grids[:period]
        if (stock["receiver"], stock["anchors"], grids) != (
            native["receiver"],
            native["anchors"],
            selected,
        ):
            mismatches.append(
                dict(
                    attempt=index,
                    expected=grids,
                    observed=selected,
                    expected_anchors=stock["anchors"],
                    observed_anchors=native["anchors"],
                )
            )
    return mismatches


def compare(reference, actual):
    if reference["visit"] != actual["visit"]:
        raise ValueError("attempts do not share the same resident capture")
    public = differences(reference["output"]["public"], actual["output"]["public"])
    native = differences(reference["output"]["native"], actual["output"]["native"])
    lhs, rhs = attempts(reference), attempts(actual)
    probes = differences(
        [call["packet"] for call in reference["trace"]["scheduler"]],
        [call["packet"] for call in actual["trace"]["scheduler"]],
    )
    seeds = seed_mismatches(reference, actual) if actual["trace"]["native"] else []
    return dict(
        visit=reference["visit"],
        label=reference["kind"],
        public=public,
        native=native,
        per_probe=probes,
        coarse_seed_mismatches=seeds,
        schedule_equal=lhs == rhs,
        reference_schedule=lhs,
        observed_schedule=rhs,
    )


def stats(run):
    rows = run["rows"]
    times = [item for row in rows for item in row["repeats"]]
    native = [item for row in rows for item in row["trace"]["native"]]
    routes = Counter(item["route"] for item in native)
    return dict(
        setup_cpu_ms=run["setup"]["cpu_ns"] / 1e6,
        setup_wall_ms=run["setup"]["wall_ns"] / 1e6,
        first_resident_wall_ms=rows[0]["first_call"]["wall_ns"] / 1e6,
        median_warm_cpu_ms=median(r["cpu_ns"] for r in times) / 1e6,
        median_warm_wall_ms=median(r["wall_ns"] for r in times) / 1e6,
        peak_rss_kib=run["memory_end"]["VmHWM"],
        resident_rss_kib=run["memory_end"]["VmRSS"],
        setup_rss_delta_kib=run["setup"]["memory"]["VmRSS"] - run["memory_before"]["VmRSS"],
        context_bytes=run["setup"]["context_bytes"],
        visits=len(rows),
        replay_samples=len(times),
        probe_attempts=sum(len(attempts(r)) for r in rows),
        peer_attempts=sum(max(0, len(attempts(r)) - 2) for r in rows),
        native_routes=dict(routes),
        native_candidate_total=sum(n["candidates"] for n in native),
        native_iq_loads=sum(n["converted"] for n in native),
        native_cpu_ns=sum(n["native_cpu_ns"] for n in native),
        actual_coarse_cpu_ns=sum(n["coarse_cpu_ns"] for n in native),
        tied_candidates=sum(bool(f & 128) for n in native for f in n["flags"]),
    )


def publish(work, report):
    if (report / "manifest.json").exists():
        raise FileExistsError("the resident detector evidence is already sealed")
    lock_path = work / "input-lock.json"
    lock = whole_iq.read(lock_path)
    files = ["PROTOCOL.md"]

    def pack(path, directory=Path(), compress=False):
        name = directory / (path.name + (".gz" if compress else ""))
        raw = path.read_bytes()
        write(report / name, gzip.compress(raw, mtime=0, compresslevel=6) if compress else raw)
        files.append(str(name))
        return str(name)

    pack(lock_path)
    binary = whole_iq.checked(Path(lock["bridge"]["path"]), lock["bridge"]["sha256"])
    shared_object = pack(binary, Path("build"), compress=True)
    dynamic = subprocess.check_output(["readelf", "-d", binary], text=True).splitlines()
    dependencies = [line.split("[")[1].split("]")[0] for line in dynamic if "(NEEDED)" in line]
    measured = work / "measured-sources"
    sources = (Path(verifier_integration.__file__), trial.BRIDGE, Path(trial.__file__))
    measured_sources = {}
    for source in sources:
        saved = measured / source.name
        measured_sources[pack(saved, Path("source"), compress=True)] = _sha(saved)
    pack(Path(__file__), Path("source"), compress=True)
    cases = {}
    for ident in trial.CASES:
        folder, out = work / ident, Path(ident)
        staged = folder / "resident-lock.json"
        resident = whole_iq.read(staged)
        resident_path = pack(staged, out)
        for entry in resident["staged"]:
            raw = whole_iq.checked(folder / entry["filename"], entry["iq_sha256"])
            pack(raw, out / "capture", compress=True)
        runs = {}
        arms = {}
        for mode in trial.MODES:
            record = folder / f"{mode}.json.gz"
            payload = runs[mode] = json.loads(gzip.decompress(record.read_bytes()))
            if payload["source_sha256"] != _sha(lock_path) or payload["resident_sha256"] != _sha(
                staged
            ):
                raise ValueError("measurement used a different resident input")
            arms[mode] = dict(trace=pack(record, out), summary=stats(payload))
        expected = lock["cases"][ident]["rows"]
        archived = [
            dict(
                visit=row["visit"], comparison=differences(ref["archived"], row["output"]["native"])
            )
            for ref, row in zip(expected, runs["installed"]["rows"], strict=True)
        ]
        comparisons = {
            f"{basis}_to_{candidate}": [
                compare(a, b)
                for a, b in zip(runs[basis]["rows"], runs[candidate]["rows"], strict=True)
            ]
            for basis, candidate in (
                ("installed", "prepared"),
                ("installed", "portable_installed"),
                ("prepared", "portable_prepared"),
                ("installed", "portable_prepared"),
            )
        }
        check = out / "parity.json"
        save_json(report / check, dict(archived=archived, pairs=comparisons))
        files.append(str(check))
        cases[ident] = dict(
            arms=arms,
            parity=str(check),
            resident=resident_path,
            cpu=trial.CASES[ident],
            producer=lock["cases"][ident]["root"],
        )
    save_json(
        report / "manifest.json",
        dict(
            schema_version=1,
            mode_order=trial.MODES,
            captures=12,
            repeats=trial.REPEATS,
            cases=cases,
            tolerance=TOLERANCES,
            bridge=shared_object,
            bridge_bytes=binary.stat().st_size,
            shared_library_dependencies=dependencies,
            portable_source_seal=trial.PORTABLE_PIN,
            measured_sources=measured_sources,
            files={name: _sha(report / name) for name in files},
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=local_output)
    parser.add_argument("--report", type=local_output, default=trial.REPORT)
    args = parser.parse_args()
    publish(args.work, args.report)
