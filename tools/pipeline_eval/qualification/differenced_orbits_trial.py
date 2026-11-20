"""Seal the staggered-RF experiment and run workers with native-only inputs."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from math import tau
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import differenced_orbits as model
from . import native_joint_full as archive
from .armijo_finish_results import pack
from .cold_input import load
from .cold_missing import _sandbox
from .fresh_scenes import _destination

OUT = ROOT / "reports/2026_11_19_receiver_screening/pilot-search-and-region/differenced-orbits"
PREDICTIONS = "positions.jsonl.gz"
CPUS = (12, 13, 14, 15)
CAP = 45
KNOWN = ("DS26-0261", "DS29-0519")
OTHER_USED = {"DS26-0048", "DS26-0070", "DS29-0316"}
WORKER = """
import json
import sys
from resource import RLIMIT_AS, RUSAGE_SELF, getrusage, setrlimit
from time import perf_counter, process_time
from types import SimpleNamespace

wall, cpu = perf_counter(), process_time()
setrlimit(RLIMIT_AS, (512 << 20, 512 << 20))
from tools.pipeline_eval.variants import differenced_orbits as m
q = json.load(sys.stdin)
assert set(q) == {'capture', 'tile', 'orbit_ns_shift'}
c = q['capture']
assert c['catalog_timestamp_ns'] <= c['cutoff_utc_ns'] and q['orbit_ns_shift'] in (0, 79 * 10**9)
capture = SimpleNamespace(**(c | {
    'catalog': c['catalog'].encode('ascii'),
    'anchor_utc_ns': c['anchor_utc_ns'] + q['orbit_ns_shift'],
}))
result = m.evaluate(capture, q['tile'])
json.dump(dict(result=result, cpu_s=process_time()-cpu, worker_s=perf_counter()-wall,
              peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss), sys.stdout, allow_nan=False)
"""


def digest(value):
    return sha256(value).hexdigest()


def variants(row):
    alias = row["recording"]
    key = f"staggered-differenced-orbits-offer-20261119/{alias}"
    radians = tau * int(digest(key.encode())[:12], 16) / 2**48
    omitted = dict(center=_destination(row["tile"]["center"], 55, radians), width_km=25)
    yield row
    for name, tile, shift in (("omitted", omitted, 0), ("time-sham", row["tile"], 79 * 10**9)):
        query = dict(id=f"{alias}-{name}", tile=tile, orbit_ns_shift=shift)
        yield (
            row
            | query
            | dict(
                cohort=name,
                original_request_sha256=digest(
                    encoded({"derives_from": row["original_request_sha256"]} | query)
                ),
            )
        )


def roster():
    source = archive.REPORT
    seal = source / "prediction-lock.json"
    archive.base.secant_full._verify_files(source, json.loads(seal.read_bytes())["files"])
    authority = source / "plan.json"
    roof = {
        q["id"]: q for q in json.loads(authority.read_bytes())["cases"] if q["cohort"] == "roof"
    }
    pool = roof.keys() - set(KNOWN) - OTHER_USED
    fresh = sorted(
        pool, key=lambda r: digest(f"staggered-differenced-orbits-20261119/{r}".encode())
    )[:3]
    ds29 = min(
        (r for r in pool - set(fresh) if r.startswith("DS29-")),
        key=lambda r: digest(f"staggered-differenced-orbits-ds29-20261119/{r}".encode()),
    )
    selected = []
    for ident in (*KNOWN, *fresh, ds29):
        p = roof[ident]["packet"]
        selected.extend(
            variants(
                dict(
                    id=ident,
                    recording=ident,
                    cohort="known" if ident in KNOWN else "fresh",
                    tile=p["offer"],
                    cutoff=p["cutoff"],
                    collected=p["catalog_timestamp"],
                    native_sha256=p["native"]["sha256"],
                    catalog_sha256=p["catalogue"]["sha256"],
                    original_request_sha256=digest(encoded(p)),
                    orbit_ns_shift=0,
                )
            )
        )
    return selected, [authority, seal]


def worker_sources():
    base = ROOT / "tools/pipeline_eval"
    return [
        base / p
        for p in (
            "__init__.py",
            "reference/__init__.py",
            "reference/grid.py",
            "reference/tracker.py",
            "variants/__init__.py",
            "variants/differenced_orbits.py",
            "variants/doppler_turns.py",
            "variants/folded_doppler.py",
            "variants/pass_hypotheses.py",
            "variants/peak_paths.py",
        )
    ]


def command(cpu):
    argv = _sandbox(cpu, [])
    for p in worker_sources():
        mount = Path("/worker") / p.relative_to(ROOT)
        argv[-4:-4] = ["--ro-bind", str(p), str(mount)]
    argv[-1] = WORKER
    return ["nice", "-n", "10", *argv]


def attempt(q, cpu):
    start = perf_counter()
    cap = load(q["recording"])
    required = (q["native_sha256"], q["catalog_sha256"], q["cutoff"], q["collected"])
    if (
        cap.native_sha256,
        cap.catalog_sha256,
        cap.cutoff_utc_ns,
        cap.catalog_timestamp_ns,
    ) != required:
        raise ValueError("changed native or causal archive")
    payload = encoded(
        dict(
            capture=vars(cap) | {"catalog": cap.catalog.decode("ascii")},
            tile=q["tile"],
            orbit_ns_shift=q["orbit_ns_shift"],
        )
    )
    try:
        run = subprocess.run(
            command(cpu), input=payload, capture_output=True, check=True, timeout=CAP
        )
        stats = json.loads(run.stdout)
    except (OSError, subprocess.SubprocessError) as err:
        detail = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-2000:]
        stats = dict(
            result=dict(
                status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
                reason=detail or str(err),
                boundary=model.BOUNDARY,
                metrics={},
                arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
            )
        )
    elapsed = perf_counter() - start
    result = stats["result"]
    validate_result(result)
    m = result["metrics"]
    print(
        q["id"],
        result["status"],
        m.get("train_groups"),
        m.get("held_groups"),
        m.get("held_qualified_triples"),
        round(elapsed, 2),
        flush=True,
    )
    return q | dict(
        method=model.METHOD,
        input_sha256=digest(payload),
        cpu=cpu,
        native_elapsed_s=elapsed,
        **stats,
    )


def run(work):
    work.mkdir(mode=0o700)
    cases, sources = roster()
    sources.extend(
        [
            *worker_sources(),
            Path(__file__),
            OUT / "PROTOCOL.md",
            ROOT / "src/leo/sky/frames.py",
            ROOT / "src/leo/sky/propagation.py",
            Path(__file__).with_name("cold_input.py"),
            Path(__file__).with_name("cold_missing.py"),
        ]
    )
    source_hashes = {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sources}
    save_json(OUT / "source-lock.json", source_hashes)
    save_json(OUT / "blind-plan.json", dict(cases=cases, cpus=CPUS, per_offer_limit_s=CAP))

    def jobs(i):
        return [attempt(q, CPUS[i]) for q in cases[i :: len(CPUS)]]

    with ThreadPoolExecutor(len(CPUS)) as pool:
        output = [r for rows in pool.map(jobs, range(len(CPUS))) for r in rows]
    indexed = {r["id"]: r for r in output}
    names = [q["id"] for q in cases]
    if set(indexed) != set(names) or any(
        digest((ROOT / n).read_bytes()) != v for n, v in source_hashes.items()
    ):
        raise ValueError("source or blind roster changed")
    files = {p: digest((OUT / p).read_bytes()) for p in ("source-lock.json", "blind-plan.json")}
    files[PREDICTIONS] = pack(OUT, PREDICTIONS, [indexed[n] for n in names])
    save_json(OUT / "prediction-lock.json", dict(files=files, cases=names))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    run(parser.parse_args().work)
