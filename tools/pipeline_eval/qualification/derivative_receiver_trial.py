"""Prospectively bind anonymous derivative receivers to native and measured factors."""

import argparse
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import derivative_receiver as variant
from . import blind_track_identity_trial as clock
from . import physical_transfer as field
from .armijo_finish_results import pack

OUT = ROOT / "reports/2026_11_19_receiver_screening/acquisition-support/derivative-receiver"
FIELD_PLAN = ROOT / "reports/2026_11_19_receiver_screening/physical/plan.json"
CPUS = (6, 7)
DEV = ("DS26-0223", "DS29-0174")
OMITTED = ("DS26-0209-omitted", "DS29-0127-omitted")
FIELD_SITES = ("field-site-05", "field-site-07")
NULL = "DS26-0223-wrong-orbit-time"
METHODS = (variant.METHOD, "polynomial_curvature_only")
prior, read, digest = clock.prior, clock.read, clock.digest
CAP = 60
MATCH = ("input_sha256", "original_request_sha256", "native_sha256", "catalog_sha256", "tile")
WORKER = """
import json
import sys
from time import perf_counter, process_time
from resource import RUSAGE_SELF, getrusage
from types import SimpleNamespace
from tools.pipeline_eval.variants import derivative_receiver as solver

wall, cpu = perf_counter(), process_time()
req = json.load(sys.stdin)
c = req['capture']
capture = SimpleNamespace(**(c | {'catalog': c['catalog'].encode('ascii'),
                                 'anchor_utc_ns': c['anchor_utc_ns'] + req['orbit_ns_shift']}))
shared = dict(tile=req['tile'], differential=req['differential'])
if req['tracks'] is None:
    result = solver.solve(capture, **shared)
else:
    result = solver.infer(capture, req['tracks'], **shared, measured=True)
json.dump(dict(result=result, worker_s=perf_counter()-wall, cpu_s=process_time()-cpu,
               peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss), sys.stdout, allow_nan=False)
"""


def synthetic(site):
    lock = read(clock.SITE_REPORT / "input-lock.json")
    if read(site / "input-lock.json") != lock:
        raise ValueError("site generator evidence differs from its original lock")
    public = {p: v for p, v in lock["files"].items() if p.startswith("public/")}
    prior.archive.base.secant_full._verify_files(site, public)
    manifest = read(site / "public/manifest.json")
    wanted = set(manifest["order"][2:4])
    path = clock.SITE_REPORT / "labels.json"
    if digest(path.read_bytes()) != lock["files"]["private/labels.json"]:
        raise ValueError("site routing differs from previously sealed labels")
    conditions = {k: r["condition"] for k, r in read(path).items()}
    return [
        dict(
            id=q["id"],
            recording=q["capture_id"],
            cohort="simulated-" + conditions[q["id"]],
            native_sha256=manifest["cases"][q["capture_id"]],
            catalog_sha256=public["public/orbit.tle"],
            tile=q["tile"],
            shuffle=False,
            orbit_ns_shift=0,
            original_request_sha256=digest(encoded(q)),
        )
        for q in read(site / "public/offers.json")
        if q["capture_id"] in wanted and conditions[q["id"]] in ("present", "missing-near")
    ]


def measured():
    root = FIELD_PLAN.parent
    seal = read(root / "prediction-lock.json")
    prior.archive.base.secant_full._verify_files(
        root,
        {
            "plan.json": seal["plan_sha256"],
            "positions.jsonl.gz": seal["positions_sha256"],
            "source-lock.json": seal["source_lock_sha256"],
        },
    )
    return [
        dict(
            id=r["alias"],
            recording=r["site_group"],
            original_case=r["original_case"],
            cohort="field-present" if r["mode"] == "supplied-tile" else "field-omitted",
            native_sha256=r["observation_sha256"],
            catalog_sha256=r["catalogue_sha256"],
            tile=dict(center=r["tile_center"], width_km=25),
            shuffle=False,
            orbit_ns_shift=0,
            original_request_sha256=r["input_sha256"],
        )
        for r in read(FIELD_PLAN)["cases"]
        if r["site_group"] in FIELD_SITES and r["mode"] in ("supplied-tile", "omitted-tile")
    ]


def jobs(site):
    base = prior.archive.REPORT
    verify = prior.archive.base.secant_full._verify_files
    verify(base, read(base / "prediction-lock.json")["files"])
    authority = {q["id"]: q for q in read(base / "plan.json")["cases"]}
    excluded = set(DEV)
    for out in (clock.OUT, clock.independent.OUTPUT, clock.ablation.OUT):
        verify(out, read(out / "prediction-lock.json")["files"])
        excluded.update(q.get("recording", q["id"]) for q in read(out / "blind-plan.json")["cases"])
    selected = []
    for prefix, count in (("DS26-", 3), ("DS29-", 1)):
        candidates = [
            k
            for k, q in authority.items()
            if q["cohort"] == "roof" and k.startswith(prefix) and k not in excluded
        ]
        selected += sorted(
            candidates, key=lambda k: digest(("derivative-receiver-20261119/" + k).encode())
        )[:count]
    if len(selected) != 4:
        raise ValueError("fewer than four disjoint roof reserves")
    rows = []
    for ids, cohort in ((DEV, "diagnostic"), (selected, "reserve"), (OMITTED, "omitted")):
        for ident in ids:
            q = authority[ident]
            p = q["packet"]
            rows.append(
                dict(
                    id=ident,
                    recording=q["recording"],
                    cohort=cohort,
                    tile=p["offer"],
                    native_sha256=p["native"]["sha256"],
                    catalog_sha256=p["catalogue"]["sha256"],
                    original_request_sha256=digest(encoded(p)),
                    cutoff=p["cutoff"],
                    collected=p["catalog_timestamp"],
                    shuffle=False,
                    orbit_ns_shift=0,
                )
            )
    simulated, public = synthetic(site), measured()
    if len(simulated) != 4 or len(public) != 4:
        raise ValueError("two independent offer pairs are required on both transfer domains")
    return [
        *rows,
        *simulated,
        *public,
        dict(rows[0], id=NULL, cohort="null", orbit_ns_shift=120 * 10**9),
    ]


def payload(q, site):
    if not q["cohort"].startswith("field-"):
        return dict(capture=clock.data(q, site), tracks=None)
    p = field.STUDY / "public_field"
    native, sky = q["native_sha256"], q["catalog_sha256"]
    o = json.loads(field._read(p / "observations" / (native + ".json"), native))
    catalog = field._read(p / "orbits" / (sky + ".tle"), sky).decode("ascii")
    if set(o) != field.OBS_FIELDS or any(set(r) != field.TRACK_FIELDS for r in o["tracks"]):
        raise ValueError("prepared measurement has unauthorized metadata")
    if o["catalog_timestamp_ns"] > o["cutoff_utc_ns"]:
        raise ValueError("prepared measurement has future orbital authority")
    tracks = [{k: t[k] for k in ("times", "values", "rf_hz")} for t in o.pop("tracks")]
    return dict(capture=o | {"catalog": catalog}, tracks=tracks)


def attempt(q, mode, cpu, site):
    once = perf_counter()
    args = payload(q, site) | dict(tile=q["tile"], orbit_ns_shift=q["orbit_ns_shift"])
    launch = prior.command(cpu, "peak_paths", prior.sources()["peak_paths"][0])
    launch[-1] = WORKER
    clock.ablation._mount(launch, [Path(variant.__file__), *clock.candidate_sources()])
    try:
        p = subprocess.run(
            launch,
            input=encoded(dict(args, differential=mode == variant.METHOD)),
            check=True,
            capture_output=True,
            timeout=CAP,
        )
        out = json.loads(p.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        descr = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-2200:]
        out = dict(
            result=dict(
                status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
                reason=descr or str(err),
                boundary=variant.BOUNDARY,
                metrics={},
                arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
            )
        )
    validate_result(out["result"])
    row = dict(
        q,
        method=mode,
        input_sha256=digest(encoded(args)),
        native_elapsed_s=perf_counter() - once,
        cpu=cpu,
        **out,
    )
    print(
        q["id"],
        mode,
        out["result"]["status"],
        out["result"]["reason"],
        out["result"]["metrics"].get("informative_orbits"),
        round(row["native_elapsed_s"], 2),
        flush=True,
    )
    return row


def run(work, site):
    work.mkdir(parents=True, exist_ok=False)
    queries = jobs(site)
    sources = [
        Path(variant.__file__),
        Path(__file__),
        Path(clock.__file__),
        *clock.candidate_sources(),
        *prior.sources()["peak_paths"][0],
        ROOT / "tools/pipeline_eval/reference/grid.py",
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
        FIELD_PLAN,
        OUT / "PROTOCOL.md",
    ]

    def pins():
        return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in sources}

    frozen = pins()
    plan = [(q, m) for q in queries for m in METHODS if q["id"] != NULL or m == variant.METHOD]
    save_json(
        OUT / "blind-plan.json",
        dict(
            cases=queries,
            sources=frozen,
            cpus=list(CPUS),
            cap_s=CAP,
            site_lock_sha256=digest((clock.SITE_REPORT / "input-lock.json").read_bytes()),
        ),
    )
    start = perf_counter()

    def lane(i):
        for q, m in plan[i::2]:
            save_json(work / f"{q['id']}-{m}.json", attempt(q, m, CPUS[i], site))

    with ThreadPoolExecutor(2) as pool:
        list(pool.map(lane, range(2)))
    if frozen != pins():
        raise ValueError("receiver changed during a sealed benchmark")
    results = [read(work / f"{q['id']}-{m}.json") for q, m in plan]
    groups = {
        "positions.jsonl.gz": [r for r in results if r["id"] != NULL],
        "null-position.jsonl.gz": [r for r in results if r["id"] == NULL],
    }
    files = {name: pack(OUT, name, records) for name, records in groups.items()}
    files["blind-plan.json"] = digest((OUT / "blind-plan.json").read_bytes())
    save_json(
        OUT / "prediction-lock.json",
        dict(
            cases=[q["id"] for q in queries],
            files=files,
            attempts=len(plan),
            wall_s=perf_counter() - start,
        ),
    )


if __name__ == "__main__":
    args = argparse.ArgumentParser(description=__doc__)
    args.add_argument("--work", type=Path, required=True)
    args.add_argument("--site", type=Path, default=clock.SITE_ROOT)
    parsed = args.parse_args()
    run(parsed.work, parsed.site)
