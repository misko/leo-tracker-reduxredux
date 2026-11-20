"""Run and seal regional absolute-Doppler tests before opening truth."""

import argparse
import gzip
import json
import subprocess
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import regional_levels as model
from . import absolute_doppler_trial as world
from .armijo_finish_results import pack

OUT = world.OUT.parent / "regional-levels"
METHODS = (model.METHOD, model.CONTROL)
PREDICTIONS = "positions.jsonl.gz"
WORKER = """
import json
import sys
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time
from types import SimpleNamespace

wall, cpu = perf_counter(), process_time()
from tools.pipeline_eval.variants import regional_levels as solver
q = json.load(sys.stdin)
assert set(q) == {'capture', 'tile'}
c = q['capture']
assert c['catalog_timestamp_ns'] <= c['cutoff_utc_ns']
capture = SimpleNamespace(**(c | {'catalog': c['catalog'].encode('ascii')}))
results = solver.paired(capture, q['tile'])
json.dump(dict(results=results, worker_s=perf_counter()-wall, cpu_s=process_time()-cpu,
               peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss), sys.stdout, allow_nan=False)
"""


def inputs():
    authority = world.read(world.OUT / "prediction-lock.json")
    world.verify(world.OUT, authority["files"])
    rows = [
        q
        for q in world.read(world.OUT / "blind-plan.json")["cases"]
        if q["cohort"] in ("diagnostic", "reserve", "omitted")
    ]
    if len(rows) != 8:
        raise ValueError("eight precommitted archive offers are required")
    return rows


def attempt(q, work):
    started = perf_counter()
    payload = dict(capture=world.clock.data(q, work), tile=q["tile"])
    prior = world.prior
    argv = prior.command(world.CPU, "peak_paths", prior.sources()["peak_paths"][0])
    argv[-1] = WORKER
    world.clock.ablation._mount(
        argv,
        [
            Path(model.__file__),
            Path(model.world.__file__),
            Path(model.world.geodesy.__file__),
            *world.clock.candidate_sources(),
        ],
    )
    try:
        proc = subprocess.run(
            argv, input=encoded(payload), check=True, capture_output=True, timeout=world.CAP
        )
        worker = json.loads(proc.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        detail = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1900:]
        failed = dict(
            status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
            reason=detail or str(err),
            boundary=model.BOUNDARY,
            metrics={},
            arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
        )
        worker = dict(results=[failed, failed])
    results = worker.pop("results")
    elapsed = perf_counter() - started
    output = []
    for method, result in zip(METHODS, results, strict=True):
        validate_result(result)
        print(q["id"], method, result["status"], result["reason"], round(elapsed, 2), flush=True)
        output.append(
            dict(
                q,
                method=method,
                result=result,
                input_sha256=world.digest(encoded(payload)),
                cpu=world.CPU,
                native_elapsed_s=elapsed,
                same_worker_controls=True,
                **worker,
            )
        )
    return output


def run(work):
    work.mkdir(parents=True, mode=0o700)
    source_paths = [
        Path(model.__file__),
        Path(__file__),
        OUT / "PROTOCOL.md",
        *world.source_paths(),
        world.OUT / "prediction-lock.json",
    ]

    def hashes():
        return {str(p.relative_to(ROOT)): world.digest(p.read_bytes()) for p in source_paths}

    sources = hashes()
    save_json(OUT / "source-lock.json", sources)
    queries = inputs()
    simulated, labels_sha, seed_sha = world.simulation(work)
    queries += simulated
    if len(queries) != 12:
        raise ValueError("regional experiment requires exactly twelve distinct offers")
    save_json(
        OUT / "blind-plan.json",
        dict(
            cases=queries,
            sources=sources,
            cpu=world.CPU,
            cap_s=world.CAP,
            private_labels_sha256=labels_sha,
            seed_sha256=seed_sha,
        ),
    )
    records = [r for q in queries for r in attempt(q, work)]
    if hashes() != sources:
        raise ValueError("regional trial source changed during the run")
    files = {
        name: world.digest((OUT / name).read_bytes())
        for name in ("source-lock.json", "blind-plan.json")
    }
    files[PREDICTIONS] = pack(OUT, PREDICTIONS, records)
    save_json(OUT / "prediction-lock.json", dict(cases=[q["id"] for q in queries], files=files))


def repair_legacy_width(work):
    first_lock = world.read(OUT / "prediction-lock.json")
    world.verify(OUT, first_lock["files"])
    first = world.read(OUT / "blind-plan.json")
    with gzip.open(OUT / PREDICTIONS, "rt") as stream:
        rows = list(map(json.loads, stream))
    for r in rows:
        implicit = "width_km" not in r["tile"]
        failed = (
            r["result"]["status"] == "failed" and "KeyError: 'width_km'" in r["result"]["reason"]
        )
        if implicit != failed:
            raise ValueError("repair applies only to the exact legacy width decode failures")
    if sum("width_km" not in r["tile"] for r in rows) != 2 * 8:
        raise ValueError("expected eight legacy offers and four explicit offers")
    files = {}
    for name in (*first_lock["files"], "prediction-lock.json"):
        backup = "first-" + name
        archived = (OUT / name).read_bytes()
        with (OUT / backup).open("xb") as stream:
            stream.write(archived)
        files[backup] = world.digest(archived)
    sources = {name: world.digest((ROOT / name).read_bytes()) for name in first["sources"]}
    changed = sorted(k for k in sources if sources[k] != first["sources"][k])
    if changed != sorted(str(Path(p).relative_to(ROOT)) for p in (model.__file__, __file__)):
        raise ValueError("trial repair is limited to offer decoding and replay accounting")
    first.update(
        sources=sources,
        before_truth_correction={
            "reason": "Decode legacy offers with the persisted 25 km default",
            "only_retried_legacy_offers": True,
            "retained_explicit_simulation_offers": True,
            "changed_sources": changed,
            "first_receipt_hashes": files,
        },
    )
    save_json(OUT / "source-lock.json", sources)
    save_json(OUT / "blind-plan.json", first)
    records = []
    for q in first["cases"]:
        if "width_km" not in q["tile"]:
            records.extend(attempt(q, work))
        else:
            records.extend(r for r in rows if r["id"] == q["id"])
    if any(world.digest((ROOT / name).read_bytes()) != sha for name, sha in sources.items()):
        raise ValueError("source changed after the width correction")
    files |= {
        name: world.digest((OUT / name).read_bytes())
        for name in ("source-lock.json", "blind-plan.json")
    }
    files[PREDICTIONS] = pack(OUT, PREDICTIONS, records)
    save_json(OUT / "prediction-lock.json", dict(cases=list(first_lock["cases"]), files=files))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    parser.add_argument("--repair-legacy-width", action="store_true")
    args = parser.parse_args()
    if args.repair_legacy_width:
        repair_legacy_width(args.work)
    else:
        run(args.work)


if __name__ == "__main__":
    main()
