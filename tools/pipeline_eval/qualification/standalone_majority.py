"""Build a separate 78-source distribution with the frozen initial-support gate."""

import argparse
import inspect
import os
import shutil
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

from leo.sky.frames import geodetic_to_ecef_km

from ..__main__ import encoded, local_output, save_json, write
from ..variants import transfer_budget as frozen
from . import cavity_payload_transfer as portable
from .fresh_scenes import _read, _sha
from .transfer_budget_results import sealed

REPORT = portable.REPORT.with_name("standalone-majority")
SOURCE = Path("tools/pipeline_eval/variants/v5_direct_cavity.py")
METHOD = "v5_cavity_payload_majority"
OLD = "v5_cavity_payload_small"
PREDICATE_SHA = "c56dcac88cb63bcb8f312adfee331887f476e18cd4c3537d8da18cfb1bf5503a"
PRIMARY_INPUT = Path("/srv/bulk/leo-dev/cpt.k4hJehCo")
NEAR_INPUT = Path("/srv/bulk/leo-dev/receiver-screening-20261119/edge-int.vCgDUBMt")
NEAR = "01528007f49ce8a971e57407"
CPUS = portable.CPUS
OBSERVER = portable.WORKER.replace(
    'worker.__globals__["TMP"] = tmp',
    'worker.__globals__["TMP"] = tmp\nworker.__globals__["STAGES"].add("initial_support")',
)
SCORE_FIELDS = ("latlon", "ecef_km", "capture_id", "role")


def substitute(source, before, after):
    if source.count(before) != 1:
        raise ValueError("unrecognized standalone source insertion point")
    return source.replace(before, after)


def specialize(source):
    path = Path(frozen.__file__)
    if _sha(path) != PREDICATE_SHA:
        raise ValueError("strict-majority coefficient source changed")
    implementation = inspect.getsource(frozen.admits_recovery).rstrip()
    gate = '''def initial_support(initial):
    """Use only the winning original initial c0 compatibility receipts."""
    winner = next(
        choice for choice in initial["choices"]
        if choice["hypothesis"] == initial["selected_hypothesis"]
    )
    metrics = winner["arms"]["c0"]["metrics"]
    evidence = dict(
        accepted_points=int(metrics["accepted_points"]),
        tracked_points=sum(int(row["points"]) for row in metrics["tracks"]),
    )
    return dict(evidence, admitted=admits_recovery(evidence))


'''
    entry = "def infer(prepared, region, bound, stages):"
    source = substitute(source, entry, implementation + "\n\n\n" + gate + entry)
    source = substitute(
        source, "    def withheld(reason):", "    support = None\n\n    def withheld(reason):"
    )
    source = substitute(
        source,
        "            metrics=dict(stage_s=stages),",
        "            metrics=dict(stage_s=stages, initial_support=support),",
    )
    marker = '    stages["initial"] = perf_counter() - started\n'
    source = substitute(
        source,
        marker,
        marker
        + """    started = perf_counter()
    support = initial_support(initial)
    stages["initial_support"] = perf_counter() - started
    if not support["admitted"]:
        return withheld("initial_compatible_support_not_majority")
""",
    )
    return substitute(
        source,
        "            initial_branches=branches,",
        "            initial_support=support,\n            initial_branches=branches,",
    )


def stage(root, original):
    source = original / "small"
    package = root / "majority"
    shutil.copytree(source, package)
    entry = package / SOURCE
    entry.write_text(specialize(entry.read_text()))
    manifest = package / "native/manifest.json"
    declared, replacement = str(source), str(package)
    manifest.write_text(manifest.read_text().replace(declared + "/", replacement + "/"))
    write(REPORT / "as-executed-v5-direct-cavity.py.txt", entry.read_bytes())
    return package


def primary_jobs(root):
    sealed(portable.REPORT)
    frozen_inputs = _read(portable.REPORT / "input-lock.json")
    rows = _read(portable.REPORT / "requests.json")
    inventory = _read(portable.REPORT / "causal-history.json")
    jobs = []
    for row in rows:
        capture = row["capture_id"]
        native = root / "public" / f"{capture}.complete.json"
        config = root / "public/track-config.json"
        archive = root / "public" / f"tle-{capture}"
        if _sha(native) != row["native_sha256"] or _sha(config) != row["track_config_sha256"]:
            raise ValueError("primary capture bits or track configuration changed")
        paths = {str(p.relative_to(root)): _sha(p) for p in archive.rglob("*.tle")}
        expected = {
            p: d for p, d in frozen_inputs.items() if p.startswith(f"public/tle-{capture}/")
        }
        if paths != expected:
            raise ValueError("the exact causal archive changed")
        jobs.append((row, native, config, archive, inventory[capture]))
    return jobs


def near_job(root, near_source):
    old = portable.recent.REPORT
    sealed(old)
    prior = next(r for r in _read(old / "requests.json") if r["id"] == NEAR)
    capture = prior["capture_id"]
    data = _read(old / "public-captures.json")[capture]
    locks = _read(old / "inputs.json")
    source = near_source / "public" / f"{capture}.native.json"
    if _sha(source) != locks[f"public/{capture}.native.json"]:
        raise ValueError("archived near-edge factor stream is unbound")
    (root / "public").mkdir(parents=True)
    shutil.copyfile(source, root / "public" / source.name)
    data["tiles"] = [data["tiles"][0], prior["tile"]]
    save_json(root / "public" / f"{capture}.json", data)
    with patch.object(portable, "SITES", ((tuple(prior["tile"]["center"]), (0, 1)),)):
        _, query = portable.prepare(root, [capture])
    if (
        query[0]["catalog_sha256"] != prior["catalog_sha256"]
        or query[0]["history_sha256"] != prior["history_sha256"]
    ):
        raise ValueError("near-edge history no longer matches earlier portable case")
    return query


def references(root, jobs):
    original_labels = _read(portable.REPORT / "released-labels.json")
    earlier_labels = _read(portable.recent.REPORT / "released-labels.json")
    authority = original_labels | earlier_labels
    out = {}
    for row, *_ in jobs:
        capture = row["capture_id"]
        doc = authority[capture]
        directory, key = (
            (portable.REPORT, "input-lock.json")
            if capture in original_labels
            else (portable.recent.REPORT, "inputs.json")
        )
        sha = portable.prior.INPUTS.cold._sha(encoded(doc) + b"\n")
        if _read(directory / key)[f"private/{capture}.json"] != sha:
            raise ValueError("ECEF coordinate authority is unbound")
        latlon = doc["location"]
        out[row["id"]] = dict(
            capture_id=capture,
            latlon=latlon,
            ecef_km=geodetic_to_ecef_km(*latlon, 0.0).tolist(),
            role=doc["roles"][row["id"]],
        )
    path = root / "private" / "targets.json"
    path.parent.mkdir(mode=0o700)
    save_json(path, out)
    return path


def replay(root, original, primary_source, optional_source):
    receipt = REPORT / "prediction-lock.json"
    if receipt.exists():
        raise ValueError("diagnosed primary predictions already exist")
    locked = portable.bound_packages(original)["small"]
    package = stage(root, original)
    files = {name: _sha(package / name) for name in locked["files"] | locked["binaries"]}
    expected = (locked["files"] | locked["binaries"]) | {str(SOURCE): files[str(SOURCE)]}
    if files != expected:
        raise ValueError("derived package changed a non-targeted scientific source")
    jobs = primary_jobs(primary_source)
    near = near_job(root / "near-input", optional_source)
    authority = references(root, [*jobs, near])
    plan = [
        dict(job[0], cpu=cpu, method=METHOD, cohort="diagnosed-primary")
        for job, cpu in zip(jobs, CPUS, strict=True)
    ] + [dict(near[0], cpu=CPUS[-1], method=m, cohort="archived-near") for m in (OLD, METHOD)]
    save_json(
        REPORT / "source-lock.json",
        dict(
            derived_files=files,
            parent_package_sha256=locked["archive_sha256"],
            native_manifest_sha256=_sha(package / "native/manifest.json"),
            predicate_sha256=PREDICATE_SHA,
            helper_sha256=_sha(Path(__file__)),
            observer_source_sha256=_sha(portable.OBSERVER),
            observed_worker_sha256=portable.prior.INPUTS.cold._sha(OBSERVER.encode()),
            prior_primary_sha256=_sha(portable.REPORT / "prediction-lock.json"),
            prior_near_sha256=_sha(portable.recent.REPORT / "prediction-lock.json"),
            protocol_sha256=_sha(REPORT / "PROTOCOL.md"),
            targets_sha256=_sha(authority),
        ),
    )
    save_json(REPORT / "requests.json", plan)
    began = perf_counter()

    def lane(index, job):
        cpu = CPUS[index]
        rows = [dict(portable.capped(root, root, job, "majority", cpu), cohort="diagnosed-primary")]
        if index == len(CPUS) - 1:
            rows.extend(
                dict(portable.capped(root, path, near, name, cpu), cohort="archived-near")
                for path, name in ((original, "small"), (root, "majority"))
            )
        return rows

    with patch.object(portable, "WORKER", OBSERVER), ThreadPoolExecutor(max_workers=4) as pool:
        result = [row for lane_rows in pool.map(lane, range(len(jobs)), jobs) for row in lane_rows]
    if (
        any(_sha(package / p) != d for p, d in files.items())
        or _sha(authority) != _read(REPORT / "source-lock.json")["targets_sha256"]
    ):
        raise ValueError("derived package or coordinates changed while executing")
    save_json(REPORT / "predictions.json", result)
    lock = (
        "source-lock.json",
        "requests.json",
        "predictions.json",
        "as-executed-v5-direct-cavity.py.txt",
    )
    save_json(
        receipt, dict(files={p: _sha(REPORT / p) for p in lock}, wall_s=perf_counter() - began)
    )
    write(REPORT / "scoring-targets.json", authority.read_bytes())


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("scratch", type=Path)
    args = cli.parse_args()
    if not set(CPUS) <= os.sched_getaffinity(0):
        cli.error("pin to the requested four CPUs")
    replay(local_output(args.scratch), portable.RELEASE, PRIMARY_INPUT, NEAR_INPUT)
