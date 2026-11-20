"""Freeze and measure anonymous cross-track identity on matched native records."""

import argparse
import gzip
import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, read_predictions, save_json
from ..scoring import ARMS, validate_result
from ..variants import blind_track_identity as model
from . import identity_ablation as ablation
from . import independent_arcs_trial as independent
from .armijo_finish_results import pack
from .cold_input import load

OUT = ROOT / "reports/2026_11_19_receiver_screening/detector-origins/blind-identity"
SITE_REPORT = OUT.parent.parent / "site-transfer"
SITE_ROOT = Path("/tmp/leo-site-transfer.Z4pTPOor/panel")
CPUS = (6, 7)
CAP = 60
DIAGNOSTIC = ("DS26-0197", "DS29-0316")
OMITTED = ("DS26-0277-omitted", "DS29-0604-omitted")
NULL = "DS26-0197-identity-shuffle"
METHODS = (model.METHOD, "local_track_identity", "independent_arcs")
prior = independent.prior
read, digest = prior.read, prior.digest
MATCH = ("native_sha256", "catalog_sha256", "input_sha256", "tile")
WORKER = """
import json
import sys
from time import perf_counter, process_time
from resource import RUSAGE_SELF, getrusage
from types import SimpleNamespace
from tools.pipeline_eval.variants import blind_track_identity as solver

started, start_cpu = perf_counter(), process_time()
q = json.load(sys.stdin)
data = q['capture']
capture = SimpleNamespace(**(data | {'catalog': data['catalog'].encode('ascii')}))
result, trace = solver.solve(capture, tile=q['tile'], mode=q['mode'], shuffle=q['shuffle'])
json.dump(dict(result=result, trace=trace, worker_s=perf_counter()-started,
               cpu_s=process_time()-start_cpu, peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss),
          sys.stdout, allow_nan=False)
"""


def simulated_jobs(site):
    verify = prior.archive.base.secant_full._verify_files
    lock = read(SITE_REPORT / "input-lock.json")
    if read(site / "input-lock.json") != lock:
        raise ValueError("synthetic archive does not match its released input lock")
    public = {name: sha for name, sha in lock["files"].items() if name.startswith("public/")}
    verify(site, public)
    manifest = read(site / "public/manifest.json")
    labels_path = SITE_REPORT / "labels.json"
    if digest(labels_path.read_bytes()) != lock["files"]["private/labels.json"]:
        raise ValueError("synthetic query condition receipt does not match the lock")
    conditions = {key: row["condition"] for key, row in read(labels_path).items()}
    roster = set(manifest["order"][:2])
    return [
        dict(
            id=q["id"],
            recording=q["capture_id"],
            cohort="simulated-" + conditions[q["id"]],
            native_sha256=manifest["cases"][q["capture_id"]],
            catalog_sha256=public["public/orbit.tle"],
            tile=q["tile"],
            shuffle=False,
            original_request_sha256=digest(encoded(q)),
        )
        for q in read(site / "public/offers.json")
        if q["capture_id"] in roster and conditions[q["id"]] in ("present", "missing-near")
    ]


def jobs(site):
    authority = prior.archive.REPORT
    verify = prior.archive.base.secant_full._verify_files
    verify(authority, read(authority / "prediction-lock.json")["files"])
    for source in (independent.OUTPUT, ablation.OUT):
        verify(source, read(source / "prediction-lock.json")["files"])
    records = {row["id"]: row for row in read(authority / "plan.json")["cases"]}
    seen = set(DIAGNOSTIC)
    seen.update(row["recording"] for row in read(independent.OUTPUT / "blind-plan.json")["cases"])
    seen.update(read(ablation.OUT / "prediction-lock.json")["cases"])
    reserve = []
    for prefix in ("DS26-", "DS29-"):
        available = [
            k
            for k, r in records.items()
            if r["cohort"] == "roof" and k.startswith(prefix) and k not in seen
        ]
        reserve += sorted(
            available, key=lambda k: digest(("blind-track-identity-20261119/" + k).encode())
        )[:2]
    if len(reserve) != 4:
        raise ValueError("four disjoint archive reserves are required")
    rows = []
    for cohort, ids in (("diagnostic", DIAGNOSTIC), ("reserve", reserve), ("omitted", OMITTED)):
        for key in ids:
            q = records[key]
            p = q["packet"]
            rows.append(
                dict(
                    id=key,
                    recording=q["recording"],
                    cohort=cohort,
                    tile=p["offer"],
                    shuffle=False,
                    cutoff=p["cutoff"],
                    collected=p["catalog_timestamp"],
                    native_sha256=p["native"]["sha256"],
                    catalog_sha256=p["catalogue"]["sha256"],
                    original_request_sha256=digest(encoded(p)),
                )
            )
    sim = simulated_jobs(site)
    if len(sim) != 4:
        raise ValueError("two sealed simulations with containing and omitted offers are required")
    return [*rows, *sim, dict(rows[0], id=NULL, cohort="shuffle", shuffle=True)]


def data(q, site):
    if q["cohort"].startswith("simulated-"):
        doc = (site / "public" / (q["recording"] + ".json.gz")).read_bytes()
        tle = (site / "public/orbit.tle").read_bytes()
        if (digest(doc), digest(tle)) != (q["native_sha256"], q["catalog_sha256"]):
            raise ValueError("simulated GLRT or orbit snapshot differs from its lock")
        return json.loads(gzip.decompress(doc)) | {"catalog": tle.decode("ascii")}
    cap = load(q["recording"])
    if (cap.native_sha256, cap.catalog_sha256, cap.cutoff_utc_ns, cap.catalog_timestamp_ns) != (
        q["native_sha256"],
        q["catalog_sha256"],
        q["cutoff"],
        q["collected"],
    ):
        raise ValueError("matched native or orbital snapshot differs from its lock")
    return vars(cap) | {"catalog": cap.catalog.decode("ascii")}


def candidate_sources():
    path = Path(model.__file__)
    return [
        path,
        path.with_name("fixed_orbit_position.py"),
        path.with_name("track_link.py"),
        *(
            ROOT / "tools/pipeline_eval/reference" / n
            for n in ("tracker.py", "receiver.py", "native_archive.py")
        ),
    ]


def attempt(q, method, cpu, site):
    start = perf_counter()
    payload = dict(capture=data(q, site), tile=q["tile"], shuffle=q["shuffle"])
    argv = prior.command(cpu, "peak_paths", prior.sources()["peak_paths"][0])
    argv[-1] = WORKER
    ablation._mount(argv, candidate_sources())
    try:
        p = subprocess.run(
            argv,
            input=encoded(payload | dict(mode="clock" if method == model.METHOD else "local")),
            capture_output=True,
            check=True,
            timeout=CAP,
        )
        out = json.loads(p.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        detail = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-2200:]
        out = dict(
            result=dict(
                status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
                reason=detail or str(err),
                boundary=model.BOUNDARY,
                metrics={},
                arms={a: dict(latlon=None, forced_latlon=None) for a in ARMS},
            )
        )
    validate_result(out["result"])
    row = dict(
        q,
        method=method,
        cpu=cpu,
        input_sha256=digest(encoded(payload)),
        native_elapsed_s=perf_counter() - start,
        **out,
    )
    print(
        q["id"],
        method,
        out["result"]["status"],
        out["result"]["reason"],
        out["result"]["metrics"].get("selected_arcs"),
        round(row["native_elapsed_s"], 2),
        flush=True,
    )
    return row


def run(work, site):
    work.mkdir(parents=True, exist_ok=False)
    queries = jobs(site)
    cached = read_predictions(independent.OUTPUT / "positions.jsonl.gz")
    old_files = [
        Path(independent.solver.__file__),
        Path(independent.previous.paired.__file__),
        *prior.sources()["peak_paths"][0],
        ROOT / "tools/pipeline_eval/reference/grid.py",
    ]
    old_pin = digest(b"".join(p.read_bytes() for p in old_files))
    files = [
        *candidate_sources(),
        *old_files,
        Path(__file__),
        Path(independent.__file__),
        Path(prior.__file__),
        Path(load.__code__.co_filename),
        OUT / "PROTOCOL.md",
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
    ]

    def pin():
        return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in files}

    closure = pin()
    plan = [
        (q, method)
        for q in queries
        for method in METHODS[:2]
        if q["id"] != NULL or method == model.METHOD
    ]
    plan.extend((q, METHODS[2]) for q in queries if q["cohort"] == "reserve")
    save_json(
        OUT / "blind-plan.json",
        dict(
            cases=queries,
            sources=closure,
            cpus=list(CPUS),
            cap_s=CAP,
            niceness=10,
            fresh_jobs=[[q["id"], m] for q, m in plan],
            inherited_control_lock_sha256=digest(
                (independent.OUTPUT / "prediction-lock.json").read_bytes()
            ),
            simulated_lock_sha256=digest((SITE_REPORT / "input-lock.json").read_bytes()),
        ),
    )
    start = perf_counter()

    def lane(i):
        for q, method in plan[i :: len(CPUS)]:
            if method == METHODS[2]:
                previous = independent.attempt(
                    q | {"misalign": False}, CPUS[i], prior.sources(), old_files, old_pin
                )
                row = dict(previous, inherited_exact=False)
            else:
                row = attempt(q, method, CPUS[i], site)
            save_json(work / f"{q['id']}-{method}.json", row)

    with ThreadPoolExecutor(len(CPUS)) as pool:
        list(pool.map(lane, range(len(CPUS))))
    if pin() != closure:
        raise ValueError("solver source changed after lock")
    found, traces, negative = [], [], []
    for q in queries:
        m = [model.METHOD] if q["id"] == NULL else METHODS[:2]
        if q["cohort"] in ("diagnostic", "reserve", "omitted"):
            m = METHODS
        for method in m:
            inherited = method == METHODS[2] and q["id"] in cached
            row = (
                dict(cached[q["id"]], cohort=q["cohort"], inherited_exact=True)
                if inherited
                else read(work / f"{q['id']}-{method}.json")
            )
            if method == METHODS[2] and row.get("implementation_sha256") != old_pin:
                raise ValueError("another independent-arcs implementation was supplied")
            if method == model.METHOD:
                base = row
            elif any(row[k] != base[k] for k in (*MATCH, "original_request_sha256")):
                raise ValueError("receiver controls use different original measurements or tiles")
            if "trace" in row:
                traces.append(dict(id=row["id"], method=method, arcs=row.pop("trace")))
            (found if q["id"] != NULL else negative).append(row)
    names = {
        name: pack(OUT, name, content)
        for name, content in (
            ("positions.jsonl.gz", found),
            ("identity-traces.jsonl.gz", traces),
            ("shuffle-position.jsonl.gz", negative),
        )
    }
    names["blind-plan.json"] = digest((OUT / "blind-plan.json").read_bytes())
    save_json(
        OUT / "prediction-lock.json",
        dict(
            cases=[q["id"] for q in queries],
            files=names,
            fresh_attempts=len(plan),
            wall_s=perf_counter() - start,
        ),
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--site", type=Path, default=SITE_ROOT)
    parser.add_argument("--show", action="store_true")
    args = parser.parse_args()
    if args.show:
        print([(r["id"], r["cohort"]) for r in jobs(args.site)])
    else:
        run(args.work, args.site)
