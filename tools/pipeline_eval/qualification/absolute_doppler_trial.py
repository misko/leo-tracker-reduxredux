"""Freeze and run worldwide absolute-Doppler predictions without geographic request fields."""

import argparse
import gzip
import json
import secrets
import subprocess
from pathlib import Path
from time import perf_counter

from ..__main__ import ROOT, encoded, save_json
from ..scoring import ARMS, validate_result
from ..variants import absolute_doppler as model
from . import blind_track_identity_trial as clock
from . import cold_scenes as cold
from . import site_transfer_samples as synthetic
from .armijo_finish_results import pack
from .fresh_scenes import _destination

OUT = ROOT / "reports/2026_11_19_receiver_screening/receiver-core/absolute-doppler"
prior, read, digest = clock.prior, clock.read, clock.digest
verify = prior.archive.base.secant_full._verify_files
DEV = ("DS26-0122", "DS29-0247")
OMITTED = ("DS26-0070-omitted", "DS29-0316-omitted")
NULL = "DS26-0122-orbit-time-shift"
METHODS = (model.METHOD, "absolute_doppler_free_offset")
CPU, CAP = 4, 45
WORKER = """
import json
import sys
from resource import RUSAGE_SELF, getrusage
from time import perf_counter, process_time
from types import SimpleNamespace

wall, cpu = perf_counter(), process_time()
from tools.pipeline_eval.variants import absolute_doppler as solver
q = json.load(sys.stdin)
assert set(q) == {'capture', 'orbit_ns_shift'}
c = q['capture']
assert c['catalog_timestamp_ns'] <= c['cutoff_utc_ns']
capture = SimpleNamespace(**(c | {'catalog': c['catalog'].encode('ascii'),
                                'anchor_utc_ns': c['anchor_utc_ns'] + q['orbit_ns_shift']}))
result = solver.paired(capture)
json.dump(dict(results=result, worker_s=perf_counter()-wall, cpu_s=process_time()-cpu,
               peak_rss_kib=getrusage(RUSAGE_SELF).ru_maxrss), sys.stdout, allow_nan=False)
"""


def real_queries():
    archive = prior.archive.REPORT
    verify(archive, read(archive / "prediction-lock.json")["files"])
    known = {r["id"]: r for r in read(archive / "plan.json")["cases"]}
    derivative = OUT.parent.parent / "acquisition-support/derivative-receiver"
    verify(derivative, read(derivative / "prediction-lock.json")["files"])
    exclude = set(DEV) | {v.removesuffix("-omitted") for v in OMITTED}
    exclude.update(q["recording"] for q in read(derivative / "blind-plan.json")["cases"])
    reserve = []
    for prefix, count in (("DS26-", 3), ("DS29-", 1)):
        eligible = [
            k
            for k, q in known.items()
            if q["cohort"] == "roof" and k.startswith(prefix) and k not in exclude
        ]
        reserve += sorted(
            eligible, key=lambda k: digest(f"absolute-doppler-20261119/{k}".encode())
        )[:count]
    if len(reserve) != 4:
        raise ValueError("incomplete disjoint reserve")
    rows = []
    for cohort, cases in (("diagnostic", DEV), ("reserve", reserve), ("omitted", OMITTED)):
        for key in cases:
            q = known[key]
            p = q["packet"]
            rows.append(
                dict(
                    id=key,
                    recording=q["recording"],
                    cohort=cohort,
                    tile=p["offer"],
                    native_sha256=p["native"]["sha256"],
                    catalog_sha256=p["catalogue"]["sha256"],
                    original_request_sha256=digest(encoded(p)),
                    cutoff=p["cutoff"],
                    collected=p["catalog_timestamp"],
                    orbit_ns_shift=0,
                )
            )
    return [*rows, dict(rows[0], id=NULL, cohort="null", orbit_ns_shift=120 * cold.NS)]


def simulation(folder):
    import numpy as np

    public, private = folder / "public", folder / "private"
    public.mkdir()
    private.mkdir(mode=0o700)
    catalog, receipt = synthetic._catalogue()
    (public / "orbit.tle").write_bytes(catalog)
    seed = secrets.token_bytes(32)
    (private / "seed.bin").write_bytes(seed)
    rng = np.random.default_rng(int.from_bytes(seed, "big"))
    orbits = cold._constellation(catalog, receipt)
    answers, rows = {}, []
    for i, centre in enumerate(((18, -66), (-12, 132))):
        site = list(map(float, np.asarray(centre) + rng.uniform(-1.5, 1.5, size=2)))
        ident = rng.bytes(12).hex()
        anchor = receipt + (i + 3) * 1200 * cold.NS
        probes, counter, generated = cold._generate_capture(orbits, anchor, site, rng)
        doc = dict(
            case_id=ident,
            probes=probes,
            sample_rate_hz=cold.RATE,
            probe_ms=cold.PROBE_MS,
            first_counter=counter,
            anchor_utc_ns=anchor,
            cutoff_utc_ns=anchor,
            catalog_timestamp_ns=receipt,
            duration_s=cold.SECONDS,
        )
        blob = gzip.compress(encoded(doc), mtime=0)
        (public / (ident + ".json.gz")).write_bytes(blob)
        answers[ident] = dict(latlon=site, **generated)
        azimuth = float(rng.uniform(0, 2 * np.pi))
        for condition, radius in (("present", 8), ("omitted", 90)):
            row = dict(
                id=ident + "-" + condition,
                recording=ident,
                cohort="simulated-" + condition,
                tile=dict(center=_destination(site, radius, azimuth), width_km=25),
                native_sha256=digest(blob),
                catalog_sha256=digest(catalog),
                orbit_ns_shift=0,
            )
            row["original_request_sha256"] = digest(encoded(row))
            rows.append(row)
    save_json(private / "labels.json", answers)
    return rows, digest((private / "labels.json").read_bytes()), digest(seed)


def source_paths():
    return [
        Path(model.__file__),
        Path(model.geodesy.__file__),
        Path(__file__),
        Path(cold.__file__),
        Path(synthetic.__file__),
        Path(clock.__file__),
        *clock.candidate_sources(),
        *prior.sources()["peak_paths"][0],
        ROOT / "tools/pipeline_eval/reference/grid.py",
        ROOT / "src/leo/sky/frames.py",
        ROOT / "src/leo/sky/propagation.py",
        OUT / "PROTOCOL.md",
    ]


def attempt(q, work):
    started = perf_counter()
    payload = dict(capture=clock.data(q, work), orbit_ns_shift=q["orbit_ns_shift"])
    argv = prior.command(CPU, "peak_paths", prior.sources()["peak_paths"][0])
    argv[-1] = WORKER
    clock.ablation._mount(
        argv, [Path(model.__file__), Path(model.geodesy.__file__), *clock.candidate_sources()]
    )
    try:
        proc = subprocess.run(
            argv, input=encoded(payload), check=True, capture_output=True, timeout=CAP
        )
        out = json.loads(proc.stdout)
    except (OSError, ValueError, subprocess.SubprocessError) as err:
        detail = (getattr(err, "stderr", None) or b"").decode(errors="replace")[-1900:]
        result = dict(
            status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
            reason=detail or str(err),
            boundary=model.BOUNDARY,
            metrics={},
            arms={k: dict(latlon=None, forced_latlon=None) for k in ARMS},
        )
        out = dict(results=[result, result])
    results = out.pop("results")
    rows = []
    for method, result in zip(METHODS, results, strict=True):
        validate_result(result)
        print(
            q["id"],
            method,
            result["status"],
            result["reason"],
            round(perf_counter() - started, 2),
            flush=True,
        )
        rows.append(
            dict(
                q,
                method=method,
                result=result,
                cpu=CPU,
                same_worker_controls=True,
                native_elapsed_s=perf_counter() - started,
                input_sha256=digest(encoded(payload)),
                **out,
            )
        )
    return rows


def run(work):
    work.mkdir(parents=True, mode=0o700)

    def pins():
        return {str(p.relative_to(ROOT)): digest(p.read_bytes()) for p in source_paths()}

    sources = pins()
    save_json(OUT / "source-lock.json", sources)
    queries = real_queries()
    simulated, labels_sha, seed_sha = simulation(work)
    queries += simulated
    save_json(
        OUT / "blind-plan.json",
        dict(
            cases=queries,
            sources=sources,
            cpu=CPU,
            cap_s=CAP,
            private_labels_sha256=labels_sha,
            seed_sha256=seed_sha,
        ),
    )
    predictions, cache = [], {}
    for q in queries:
        key = (q["recording"], q["orbit_ns_shift"])
        reused = key in cache
        if not reused:
            cache[key] = attempt(q, work)
        predictions.extend(row | q | {"reused_offer_only": reused} for row in cache[key])
    if sources != pins():
        raise ValueError("source changed during benchmark")
    names = ("source-lock.json", "blind-plan.json")
    files = {name: digest((OUT / name).read_bytes()) for name in names}
    files["positions.jsonl.gz"] = pack(OUT, "positions.jsonl.gz", predictions)
    save_json(OUT / "prediction-lock.json", dict(files=files, cases=[q["id"] for q in queries]))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", type=Path)
    args = parser.parse_args()
    run(args.work)


if __name__ == "__main__":
    main()
