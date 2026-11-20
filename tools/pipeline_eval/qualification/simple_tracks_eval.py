"""Measure a compact anonymous track builder against Graph with a common joint fitter."""

import argparse
import json
import os
import subprocess
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from time import perf_counter

from .. import corpus
from ..__main__ import encoded, local_output, save_json
from ..scoring import ARMS, ROLES, distance_km, distribution, validate_result
from ..variants import joint_orbits, simple_tracks
from . import native_joint_trial
from . import native_lean_eval as native
from . import robust_orbit_fit_trials as prior
from .broad_search_budget import frozen_inputs
from .full_v5_check import _sha
from .prefix_figures import csv_file

REPORT = native.ROOT / "reports/2026_11_19_receiver_screening/factors/simple-tracks"
NATIVE = native_joint_trial.NATIVE
WORKER = Path(__file__).with_name("simple_tracks_worker.py")
SIMPLE = Path(simple_tracks.__file__)
METHODS = {"sparse": simple_tracks.METHOD, "graph": simple_tracks.CONTROL}
CONFIRMATION = ("DS26-0275", "DS26-0092", "DS29-0604")
MATCH = ["native_sha256", "catalog_sha256", "scenario_sha256"]


def plan():
    earlier = json.loads((native_joint_trial.REPORT / "plan.json").read_bytes())
    used = {*native.CASES, *prior.CONFIRMATION, *prior.TIMING_IDS}
    used.update(job["recording"] for job in earlier["cases"])
    inputs = frozen_inputs()
    confirmation = tuple(
        ident
        for band, count in (("DS26-", 2), ("DS29-", 1))
        for ident in sorted(
            (
                i
                for i in inputs
                if i.startswith(band) and i not in used and inputs[i].get("recording")
            ),
            key=lambda i: corpus._sha(("simple-tracks-confirmation/v1:" + i).encode()),
        )[:count]
    )
    if confirmation != CONFIRMATION:
        raise ValueError("the disjoint roster differs from the preregistered inventory")
    for cohort, cases in (("primary", native.CASES), ("confirmation", confirmation)):
        for ident in cases:
            yield (
                dict(id=ident, recording=ident, cohort=cohort, condition=None),
                native.request(inputs[ident], "native"),
            )
    recording = native.SMOKE[0]
    wrong = json.loads((corpus.FROZEN / "roof-four-offers.json").read_bytes())[recording]
    if wrong["catalog_sha256"] != inputs[recording]["catalog"]["sha256"]:
        raise ValueError("wrong tile changes the causal catalogue")
    (offer,) = (tile for tile in wrong["regions"] if tile["id"] == "r0")
    for label, condition, selected in (
        ("wrong", "Correct region omitted", offer),
        ("shuffle", "CFO shuffled within lane", None),
    ):
        meta = dict(
            id=f"{recording}-{label}", recording=recording, cohort="transfer", condition=condition
        )
        request, paths = native.request(inputs[recording], "native", offer=selected)
        request["shuffle"] = label == "shuffle"
        yield meta, (request, paths)


def command(cpu, paths, bundle, frontend):
    cmd = native_joint_trial.command(cpu, paths, bundle)
    cmd[cmd.index(str(native_joint_trial.WORKER))] = str(WORKER)
    if frontend == "sparse":
        cmd[-3:-3] = [
            "--ro-bind",
            str(SIMPLE),
            "/worker/tools/pipeline_eval/variants/simple_tracks.py",
        ]
    return cmd


def run_worker(meta, packet, paths, frontend, cpu, bundle):
    common = dict(packet, shuffle=packet.get("shuffle", False))
    body = dict(common, frontend=frontend)
    began = perf_counter()
    try:
        out = json.loads(
            subprocess.run(
                command(cpu, paths, bundle, frontend),
                input=encoded(body),
                capture_output=True,
                timeout=45,
                check=True,
            ).stdout
        )
    except (subprocess.SubprocessError, OSError, ValueError) as exc:
        reason = (getattr(exc, "stderr", None) or b"").decode(errors="replace")[-2000:]
        out = dict(
            result=dict(
                status="timed_out" if isinstance(exc, subprocess.TimeoutExpired) else "failed",
                reason=reason or str(exc),
                boundary="Bound native GLRT worker",
                metrics={},
                arms={arm: dict(latlon=None, forced_latlon=None) for arm in ARMS},
            )
        )
    validate_result(out["result"])
    row = dict(
        **meta,
        **out,
        method=METHODS[frontend],
        cpu=cpu,
        tile=packet["offer"],
        worker_wall_s=perf_counter() - began,
        input_sha256=corpus._sha(encoded(body)),
        scenario_sha256=corpus._sha(encoded(common)),
        native_sha256=packet["native"]["sha256"],
        catalog_sha256=packet["catalogue"]["sha256"],
    )
    print(
        row["id"],
        frontend,
        row["result"]["status"],
        row["result"]["reason"],
        round(row["worker_wall_s"], 3),
        flush=True,
    )
    return row


def source_lock(bundle):
    payload = native_joint_trial.sources(bundle)
    own = [SIMPLE, WORKER, Path(__file__), REPORT / "PROTOCOL.md"]
    return dict(
        frozen=payload, qualification={str(p.relative_to(native.ROOT)): _sha(p) for p in own}
    )


def inventory(rows, base):
    extra = {
        "/worker/main.py": WORKER,
        "/worker/tools/pipeline_eval/variants/native_lean.py": Path(native.native_lean.__file__),
        "/worker/tools/pipeline_eval/variants/joint_orbits.py": Path(joint_orbits.__file__),
        "/worker/tools/pipeline_eval/variants/simple_tracks.py": SIMPLE,
    }
    return {
        name: base[name]
        if name in base and name not in extra
        else dict(
            lines=len(extra[name].read_bytes().splitlines()),
            sha256=_sha(extra[name]),
        )
        for name in sorted({p for r in rows for p in r.get("imported_first_party", ())})
    }


def score(rows, refs):
    for row in rows:
        ref = refs[row["recording"]]
        decision = row["result"]
        metrics = decision["metrics"]
        memory = row.get("proc_memory_kib", {})
        points = row.get("counts", {}).get("winning_peaks")
        for arm, result in decision["arms"].items():
            yield dict(
                id=row["id"],
                method=row["method"],
                cohort=row["cohort"],
                arm=arm,
                error_km=distance_km(result["latlon"], ref["truth"]),
                forced_error_km=distance_km(result.get("forced_latlon"), ref["truth"]),
                status=decision["status"],
                reason=decision.get("reason"),
                conditional_rms_hz=result.get("rf_rms_hz"),
                score=result.get("frequency_score"),
                held_score=result.get("held_score"),
                held_orbits=metrics.get("held_by_arm", {}).get(arm, {}).get("held_orbits"),
                pooled_shift_km=metrics.get("pooled_shift_km"),
                radius_km=result.get("radius_km"),
                associated_orbits=metrics.get("orbit_count"),
                curved_tracks=metrics.get("curved_tracks"),
                tracks=metrics.get("input_tracks"),
                track_points=metrics.get("input_points"),
                winning_peaks=points,
                associated_points=metrics.get("associated_observations"),
                wall_s=row["worker_wall_s"],
                cpu_s=row.get("worker", {}).get("cpu_s"),
                track_cpu_s=row.get("stages", {}).get("track_builder", {}).get("cpu_s"),
                track_wall_s=row.get("stages", {}).get("track_builder", {}).get("wall_s"),
                archive_cpu_s=row.get("stages", {})
                .get("archive_and_peak_selection", {})
                .get("cpu_s"),
                peak_rss_kib=memory.get("VmHWM"),
                peak_virtual_kib=memory.get("VmPeak"),
            )


def summarize(table):
    groups = []
    numeric = [
        "error_km",
        "forced_error_km",
        "conditional_rms_hz",
        "held_score",
        "wall_s",
        "cpu_s",
        "track_cpu_s",
        "track_wall_s",
        "archive_cpu_s",
        "peak_rss_kib",
        "peak_virtual_kib",
        "track_points",
        "associated_points",
    ]
    for key in sorted({(r["cohort"], r["method"], r["arm"]) for r in table}):
        cohort, method, arm = key
        group = [r for r in table if (r["cohort"], r["method"], r["arm"]) == key]
        groups.append(
            dict(
                cohort=cohort,
                method=method,
                arm=arm,
                attempted=len(group),
                statuses=dict(Counter(r["status"] for r in group)),
                **{name: distribution(r.get(name) for r in group) for name in numeric},
            )
        )
    return groups


def publish(rows, lock, inventory_by_method, output, elapsed):
    candidate, graph = (f"{key}-positions.jsonl.gz" for key in METHODS)
    for key, name in (("sparse", candidate), ("graph", graph)):
        native._write_predictions(output / name, rows[key])
    save_json(output / "source-lock.json", lock)
    save_json(output / "deployment.json", inventory_by_method)
    files = [candidate, graph, "source-lock.json", "deployment.json"]
    hashes = {name: _sha(output / name) for name in files}
    save_json(
        output / "prediction-lock.json", dict(cases=[r["id"] for r in rows["sparse"]], files=hashes)
    )
    refs = {r["id"]: r for r in native_joint_trial.phase.projector_roof.roster()}
    table = list(score(rows["sparse"] + rows["graph"], refs))
    matched = {(r["id"], r["arm"]): r for r in table if r["method"] == METHODS["graph"]}
    comparisons = []
    for r in table:
        if r["method"] != METHODS["sparse"]:
            continue
        stock = matched[r["id"], r["arm"]]
        x, y = r["error_km"], stock["error_km"]
        comparisons.append(
            dict(
                id=r["id"],
                arm=r["arm"],
                cohort=r["cohort"],
                publication_mismatch=(x is None) != (y is None),
                reduced_accuracy=x is not None and y is not None and x > y + max(0.1, 0.1 * y),
            )
        )
    for row in rows["sparse"]:
        if row["cohort"] == "transfer":
            continue
        for role in ROLES:
            for arm, item in refs[row["id"]]["reference"][role].items():
                original = dict.fromkeys(table[0])
                original.update(
                    id=row["id"],
                    method=role,
                    cohort=row["cohort"],
                    arm=arm,
                    status="ok" if item["latlon"] else "withheld",
                    error_km=item["error_km"],
                )
                table.append(original)
    csv_file(output / "scores.csv", table)
    digest_matches = {
        a["id"]: a.get("observation_sha256") == b.get("observation_sha256")
        and bool(a.get("observation_sha256"))
        for a, b in zip(*rows.values(), strict=True)
    }
    save_json(
        output / "summary.json",
        dict(
            wall_s=elapsed,
            observation_digest_matches=digest_matches,
            paired_checks=comparisons,
            groups=summarize(table),
        ),
    )
    charts = []
    for cohort in ("primary", "confirmation", "transfer"):
        selected = [r for r in rows["sparse"] if r["cohort"] == cohort]
        cases = [r["id"] for r in selected]
        transfer = cohort == "transfer"
        seal = f"{cohort}-figure-lock.json"
        descriptor = dict(
            id=f"{simple_tracks.METHOD}-{cohort}",
            method=simple_tracks.METHOD,
            scope="transfer" if transfer else "roof",
            cases=cases,
            title=f"Sparse native GLRT tracks with the matched joint orbit fit · {cohort}",
            caption=(
                "Both workers run the same causal joint orbit solver with the same region and "
                "calibration arms. Track membership is the experimental variable."
            ),
            seal=seal,
            provenance=["deployment.json", "source-lock.json"],
            series=[
                dict(
                    key="candidate" if transfer else "one",
                    label="Sparse velocity-continuous tracks",
                    file=candidate,
                    value=METHODS["sparse"],
                    where={"cohort": cohort},
                ),
                dict(
                    key="stock",
                    label="Graph tracks · same joint fitter",
                    file=graph,
                    value=METHODS["graph"],
                    where={"cohort": cohort},
                    match=MATCH,
                ),
            ],
        )
        receipt = dict(cases=cases, files=dict(hashes))
        if transfer:
            queries = "transfer-queries.json"
            save_json(
                output / queries,
                dict(
                    queries=[
                        dict(
                            id=r["id"],
                            condition=r["condition"],
                            recording=r["recording"],
                            truth=refs[r["recording"]]["truth"],
                            bindings={key: r[key] for key in MATCH},
                        )
                        for r in selected
                    ]
                ),
            )
            descriptor["queries"] = queries
            receipt["files"][queries] = _sha(output / queries)
        save_json(output / seal, receipt)
        charts.append(descriptor)
    save_json(output / "figures.json", dict(version=1, charts=charts))


def trial(work, output, cpus):
    if len(set(cpus)) != 2 or not set(cpus) <= os.sched_getaffinity(0):
        raise ValueError("choose two distinct available CPU indices")
    work.mkdir(exist_ok=False, parents=True)
    deployment = json.loads((NATIVE / "deployment.json").read_bytes())["files"]
    graph, _ = native.bundle_imports([dict(imported_first_party=deployment)], work / "graph-source")
    omit = [p for p in deployment if p.startswith("/source/leo/analysis/")]
    sparse, _ = native.bundle_imports(
        [dict(imported_first_party=deployment)], work / "sparse-source", omit=omit
    )
    lock = source_lock(graph)
    jobs = list(enumerate(plan()))
    save_json(
        work / "plan.json",
        dict(
            sources=lock,
            jobs=[dict(**meta, request=packet) for _, (meta, (packet, _)) in jobs],
            cpus=cpus,
        ),
    )

    def lane(cpu, batch):
        for i, (meta, (packet, paths)) in batch:
            pairs = tuple(METHODS)[:: 1 if (i // 2) % 2 == 0 else -1]
            for key in pairs:
                row = run_worker(
                    meta, packet, paths, key, cpu, sparse if key == "sparse" else graph
                )
                save_json(work / f"{meta['id']}-{key}.json", row)

    began = perf_counter()
    with ThreadPoolExecutor(2) as executor:
        for future in [executor.submit(lane, cpu, jobs[i::2]) for i, cpu in enumerate(cpus)]:
            future.result()
    elapsed = perf_counter() - began
    if source_lock(graph) != lock:
        raise ValueError("receiver source changed during the paired trial")
    rows = {
        key: [json.loads((work / f"{meta['id']}-{key}.json").read_bytes()) for _, (meta, _) in jobs]
        for key in METHODS
    }
    for a, b in zip(*rows.values(), strict=True):
        if any(a[k] != b[k] for k in MATCH) or a.get("counts", {}).get("winning_peaks") != b.get(
            "counts", {}
        ).get("winning_peaks"):
            raise ValueError(f"input authority or accepted peak support changed for {a['id']}")
    records = {key: inventory(data, deployment) for key, data in rows.items()}
    publish(rows, lock, records, output, elapsed)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cpu", type=int, nargs=2, default=(6, 23))
    parser.add_argument("--work", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    trial(local_output(args.work), local_output(args.out), args.cpu)


if __name__ == "__main__":
    main()
