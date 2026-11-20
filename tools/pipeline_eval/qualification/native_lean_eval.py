"""Measure streaming archived GLRT and matched prepared tracks under one memory cap."""

import argparse
import gzip
import json
import os
import subprocess
from hashlib import sha256
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import ROOT, encoded, local_output, save_json, write
from ..reference import native_archive
from ..scoring import ARMS, distance_km, distribution, validate_result
from ..variants import native_lean, robust_orbit_fit, v5_lean
from . import raw_robust, robust_orbit_fit_trials
from .full_v5_check import BULK, _load_case, _sha
from .prefix_figures import csv_file

SMOKE = ("DS26-0036", "DS29-0082")
CONFIRMATION = ("DS26-0187", "DS26-0197", "DS29-0519")
CASES = (*SMOKE, *CONFIRMATION)
METHODS = {"native": native_lean.METHOD, "prepared": native_lean.CONTROL}
WORKER = Path(native_lean.__file__)
TRACK_COMPONENTS = ("graph_tracklets.py", "polynomial_tracklets.py", "tracklet_fitting.py")
FILES = {"native": "positions.jsonl.gz", "prepared": "control-positions.jsonl.gz"}
EAGER_INITIALIZERS = {"/source/leo/contracts/__init__.py", "/source/leo/sky/__init__.py"}
WRONG_ID = "DS26-0036-r0"


def check_sources():
    frozen = raw_robust.locked_sources()["frozen_tracker"]
    fit = robust_orbit_fit_trials.locked_sources()
    files = {str(p.relative_to(ROOT)): _sha(p) for p in (WORKER, Path(native_archive.__file__))}
    for name in TRACK_COMPONENTS:
        relative = Path("leo/analysis") / name
        source, reference = ROOT / "src" / relative, v5_lean.SOURCE / relative
        digest = _sha(source)
        if digest != _sha(reference):
            raise ValueError(
                f"current Graph dependency differs from the materialized oracle: {name}"
            )
        files[str(Path("src") / relative)] = digest
    return dict(streaming=files, frozen_tracker=frozen, exact_backend=fit)


def projection_control(case, path, cpu, work):
    began = perf_counter()
    projected = raw_robust.build_tracks(case, path, case["native"]["sha256"], cpu)
    observation = work / f"{case['id']}-prepared-observation.json"
    payload = encoded(projected["projection"])
    write(observation, payload)
    return (
        observation,
        sha256(payload).hexdigest(),
        dict(
            metrics=projected["metrics"],
            supervisor_wall_s=perf_counter() - began,
        ),
    )


def command(cpu, inputs, *, source=None):
    original = robust_orbit_fit_trials.TRIAL_WORKER
    cmd = robust_orbit_fit_trials.command(cpu, robust_orbit_fit.METHOD)[:-1]
    cmd[cmd.index(str(original))] = str(WORKER)
    unused = cmd.index("/worker/rate_triplets.py")
    del cmd[unused - 2 : unused + 1]
    cmd[-3:-3] = [
        "--ro-bind",
        str(Path(native_archive.__file__)),
        "/worker/tools/pipeline_eval/reference/native_archive.py",
    ]
    for key, path in inputs.items():
        cmd[-3:-3] = ["--ro-bind", str(path), f"/input/{key}"]
    if source is not None:
        for i, token in enumerate(cmd):
            if token != "--ro-bind":
                continue
            target = cmd[i + 2]
            if target == "/source/leo":
                cmd[i + 1] = str(source / "leo")
            elif target.startswith("/worker/"):
                cmd[i + 1] = str(source / target.removeprefix("/worker/"))
    return cmd


def request(case, mode, observation=None, observation_sha=None, *, offer=None):
    catalogue = case["catalog"]
    inputs = {"catalogue": BULK / catalogue["path"]}
    checksum = {"catalogue": catalogue["sha256"]}
    if mode == "native":
        for key in ("native", "track_config"):
            inputs[key] = BULK / case[key]["path"]
            checksum[key] = case[key]["sha256"]
    else:
        inputs["observation"] = observation
        checksum["observation"] = observation_sha
    if offer is None:
        (offer,) = case["regions"]
    payload = dict(
        mode=mode,
        cutoff=case["cutoff_utc_ns"],
        catalog_timestamp=case["catalog_timestamp_ns"],
        probe_limit=2 * case["recording"]["window_count"],
        offer=offer,
        **{key: dict(path=f"/input/{key}", sha256=checksum[key]) for key in inputs},
    )
    return payload, inputs


def execute(case, mode, cpu, observation=None, observation_sha=None, *, source=None, offer=None):
    payload, inputs = request(case, mode, observation, observation_sha, offer=offer)
    started = perf_counter()
    try:
        worker = subprocess.run(
            command(cpu, inputs, source=source),
            input=encoded(payload),
            capture_output=True,
            timeout=90,
            check=True,
        )
        out = json.loads(worker.stdout)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as err:
        out = dict(
            result=dict(
                status="timed_out" if isinstance(err, subprocess.TimeoutExpired) else "failed",
                reason=(err.stderr or b"").decode(errors="replace")[-2400:] or str(err),
                boundary=native_lean.BOUNDARY if mode == "native" else native_lean.CONTROL_BOUNDARY,
                metrics={},
                arms={arm: {"latlon": None} for arm in ARMS},
            )
        )
    validate_result(out["result"])
    out.update(
        id=case["id"],
        method=METHODS[mode],
        tile=payload["offer"],
        cpu=cpu,
        native_sha256=case["native"]["sha256"],
        catalog_sha256=case["catalog"]["sha256"],
        input_sha256=sha256(encoded(payload)).hexdigest(),
        worker_wall_s=perf_counter() - started,
    )
    print(
        case["id"],
        mode,
        out["result"]["status"],
        out.get("proc_memory_kib"),
        out["result"].get("reason"),
        flush=True,
    )
    return out


def same_result(candidate, control):
    x, y = (row["result"] for row in (candidate, control))
    return (
        bool(candidate.get("observation_sha256"))
        and candidate["observation_sha256"] == control.get("observation_sha256")
        and (x["status"], x.get("reason"), x["arms"]) == (y["status"], y.get("reason"), y["arms"])
    )


def bundle_imports(rows, bundle, *, omit=()):
    """Materialize exactly the imported first-party scientific files for a fresh rerun."""
    entries = {}
    paths = set(path for row in rows for path in row.get("imported_first_party", ()))
    for path in sorted(paths - set(omit)):
        if path == "/worker/main.py":
            source, target = WORKER, bundle / "main.py"
        elif path.startswith("/source/"):
            suffix = path.removeprefix("/source/")
            source, target = ROOT / "src" / suffix, bundle / suffix
        elif path.startswith("/worker/"):
            suffix = path.removeprefix("/worker/")
            source, target = ROOT / suffix, bundle / suffix
        else:
            raise ValueError(f"unbound source asset {path}")
        raw = source.read_bytes()
        write(target, raw)
        entries[path] = dict(lines=len(raw.splitlines()), sha256=sha256(raw).hexdigest())
    return bundle, entries


def _distributions(rows):
    table = []
    refs = {r["id"]: r for panel in ("ds26-common127", "roof16") for r in corpus.references(panel)}
    for mode in METHODS:
        for record in rows[mode]:
            reference = refs[record["id"]]
            for arm in ARMS:
                point = record["result"]["arms"][arm]
                table.append(
                    dict(
                        id=record["id"],
                        method=METHODS[mode],
                        arm=arm,
                        cohort="smoke" if record["id"] in SMOKE else "confirmation",
                        status=record["result"]["status"],
                        reason=record["result"].get("reason"),
                        error_km=distance_km(point["latlon"], reference["truth"]),
                        forced_error_km=distance_km(point.get("forced_latlon"), reference["truth"]),
                        original_v5_error_km=reference["reference"]["baseline"][arm]["error_km"],
                        rf_rms_hz=point.get("rf_rms_hz"),
                        frequency_score=point.get("frequency_score"),
                    )
                )
    return table


def _summary(rows, table, inventory):
    out = {
        "roster": list(CASES),
        "same_prepared_tracks_and_fits": all(
            same_result(a, b) for a, b in zip(rows["native"], rows["prepared"], strict=True)
        ),
        "first_party": inventory,
    }
    for mode, method in METHODS.items():
        workers = rows[mode]
        out[mode] = dict(
            max_rss_kib=max(r.get("proc_memory_kib", {}).get("VmHWM", 0) for r in workers),
            wall_s=distribution(r["worker_wall_s"] for r in workers),
            cpu_s=distribution(r.get("worker", {}).get("cpu_s") for r in workers),
            geographic={
                arm: distribution(
                    r["error_km"] for r in table if r["arm"] == arm and r["method"] == method
                )
                for arm in ARMS
            },
        )
    return out


def _write_predictions(path, rows):
    write(path, gzip.compress(b"".join(encoded(r) + b"\n" for r in rows), mtime=0))


def _series(mode, filename, *, cohort=None):
    native = mode == "native"
    result = dict(
        key="one" if native else "stock",
        label="Streaming native GLRT" if native else "Same fitter · prepared tracks",
        file=filename,
        value=METHODS[mode],
    )
    if not native:
        result["match"] = ["observation_sha256"]
    if cohort:
        result["where"] = {"cohort": cohort}
    return result


def _wrong_figure(output, predictions):
    filename, queries = "wrong-positions.jsonl.gz", "wrong-queries.json"
    _write_predictions(output / filename, predictions)
    reference = next(r for r in corpus.references("ds26-common127") if r["id"] == SMOKE[0])
    save_json(
        output / queries,
        dict(
            queries=[
                dict(
                    id=WRONG_ID,
                    condition="Correct region omitted",
                    recording=SMOKE[0],
                    truth=reference["truth"],
                    bindings={
                        key: predictions[0][key]
                        for key in ("native_sha256", "catalog_sha256", "observation_sha256")
                    },
                )
            ]
        ),
    )
    seal = "wrong-figure-lock.json"
    save_json(
        output / seal,
        dict(cases=[WRONG_ID], files={name: _sha(output / name) for name in (filename, queries)}),
    )
    candidate, stock = (_series(mode, filename) for mode in METHODS)
    candidate.update(key="candidate", label="Streaming native GLRT · published")
    return dict(
        id=native_lean.METHOD + "-wrong-region",
        method=native_lean.METHOD,
        scope="transfer",
        cases="sealed",
        title="Streaming native GLRT with the correct region omitted",
        caption=(
            "DS26-0036 uses the same recorded factors and causal catalogue as its roof run. "
            "The frozen alternate r0 tile omits the correct region. Geographic errors of "
            "forced coordinates are diagnostic."
        ),
        seal=seal,
        queries=queries,
        series=[candidate, stock],
    )


def publish(output, rows, source_lock, inventory, deployment_record, wrong):
    for mode, records in rows.items():
        _write_predictions(output / FILES[mode], records)
    save_json(output / "source-lock.json", source_lock)
    save_json(output / "deployment.json", deployment_record)
    file_names = (*FILES.values(), "source-lock.json", "deployment.json")
    save_json(
        output / "prediction-lock.json",
        dict(
            cases=CASES,
            files={name: _sha(output / name) for name in file_names},
        ),
    )
    table = _distributions(rows)
    csv_file(output / "errors.csv", table)
    save_json(output / "summary.json", _summary(rows, table, inventory))
    charts = []
    for cohort, cases in (("smoke", SMOKE), ("confirmation", CONFIRMATION)):
        seal = f"{cohort}-figure-lock.json"
        save_json(
            output / seal,
            dict(cases=cases, files={name: _sha(output / name) for name in file_names}),
        )
        charts.append(
            dict(
                id=f"{native_lean.METHOD}-{cohort}",
                method=native_lean.METHOD,
                scope="roof",
                cases=cases,
                title=f"Streaming native GLRT through the exact robust receiver · {cohort}",
                caption=(
                    "Complete capture-era GLRT factors enter a bounded streaming Graph worker. "
                    "Its control uses the same exact fitter on tracks rebuilt from the same "
                    "artifacts. The original v5 references use the same supplied tile."
                ),
                seal=seal,
                provenance=["deployment.json"],
                series=[_series(mode, FILES[mode], cohort=cohort) for mode in METHODS],
            )
        )
    charts.append(_wrong_figure(output, wrong))
    save_json(output / "figures.json", dict(version=1, charts=charts))


def trial(cpu, work, output):
    lock = check_sources()
    work.mkdir(parents=True, exist_ok=False)
    rows = {mode: [] for mode in METHODS}
    smoke = _load_case(SMOKE[0])
    wide = execute(smoke, "native", cpu)
    seed, _ = bundle_imports([wide], work / "discovery-source", omit=EAGER_INITIALIZERS)
    narrow = execute(smoke, "native", cpu, source=seed)
    if not same_result(wide, narrow):
        raise ValueError("the independent import closure changed the first smoke result")
    bundle, inventory = bundle_imports([narrow], work / "deployed-source")
    prepared_smoke = None
    for index, ident in enumerate(CASES):
        case = _load_case(ident)
        path = BULK / case["native"]["path"]
        prepared, checksum, materialized = projection_control(case, path, cpu, work)
        if ident == SMOKE[0]:
            prepared_smoke = (prepared, checksum)
        modes = tuple(METHODS)[:: 1 if index % 2 == 0 else -1]
        for order, mode in enumerate(modes):
            row = execute(case, mode, cpu, prepared, checksum, source=bundle)
            row.update(
                pair_execution_order=order, cohort="smoke" if ident in SMOKE else "confirmation"
            )
            if mode == "prepared":
                row["external_graph_preparation"] = materialized
            rows[mode].append(row)
            save_json(work / f"{ident}-{mode}.json", row)
    wrong_tile = json.loads((corpus.FROZEN / "roof-four-offers.json").read_bytes())[SMOKE[0]]
    if wrong_tile["catalog_sha256"] != smoke["catalog"]["sha256"]:
        raise ValueError("wrong-region catalogue authority differs from the smoke recording")
    (offer,) = (tile for tile in wrong_tile["regions"] if tile["id"] == "r0")
    wrong = [
        dict(execute(smoke, mode, cpu, *prepared_smoke, source=bundle, offer=offer), id=WRONG_ID)
        for mode in METHODS
    ]
    if not all(same_result(a, b) for a, b in zip(*rows.values(), strict=True)) or not same_result(
        *wrong
    ):
        raise ValueError("native and prepared outcomes differ; inspect the per-case records")
    deployment = dict(
        same_first_smoke_fit=same_result(wide, rows["native"][0]),
        original_imported_first_party=wide["imported_first_party"],
        original_memory_kib=wide["proc_memory_kib"],
        files=inventory,
        all_final_workers_bound_to_package=True,
    )
    if check_sources() != lock:
        raise ValueError("scientific implementations changed during paired inference")
    publish(output, rows, lock, inventory, deployment, wrong)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", type=int, default=6)
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    if args.cpu not in os.sched_getaffinity(0):
        parser.error("choose an available CPU")
    trial(args.cpu, local_output(args.work), local_output(args.out))


if __name__ == "__main__":
    main()
