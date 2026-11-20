"""Run full-support winner interventions using the sealed phase-release calculator."""

import argparse
import gzip
import shutil
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from .. import cavity_runtime
from ..__main__ import encoded, local_output, save_json, write
from . import cavity_payload_transfer as receiver
from .alias_attribution import CONDITIONS, manipulate, match_winners, shuffled
from .factor_cross_trial import write_members
from .input_factor_bridge import REPO, SCREEN, _sha, check, read
from .peak_support_trial import BAND, ORDER, authority, read_band

REPORT = SCREEN / "receiver-core/alias-attribution"
GRAPH = Path(__file__).with_name("alias_attribution_graph.py").resolve()
CPUS = 8, 9
LIMIT = 135
PROFILE = "phase-release"


def local_inputs(root, ident, config, archive, bound, config_sha):
    path = root / "authority" / ident
    path.mkdir(parents=True)
    local_config = path / "track-config.json"
    shutil.copyfile(config, local_config)
    check(local_config, config_sha)
    local_archive = path / "tle"
    expected = {row["utc_ns"]: row["sha256"] for row in bound["history"]}
    for origin in archive.rglob("*.tle"):
        stamp = int(origin.name.split("-", 1)[0])
        target = local_archive / origin.relative_to(archive)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(origin, target)
        check(target, expected.pop(stamp))
    if expected:
        raise ValueError("incomplete ext4 copy of sealed causal history")
    capture = path / "capture-era.json"
    shutil.copyfile(bound["paths"]["capture-era"], capture)
    check(capture, bound["native_sha"]["capture-era"])
    return capture, local_config, local_archive


def prepare(root):
    if (REPORT / "plan.json").exists():
        raise ValueError("alias-attribution science and inputs already sealed")
    bundle = root / PROFILE
    cavity_runtime.install(bundle, profile=PROFILE)
    inputs = {str(p.relative_to(bundle)): _sha(p) for p in bundle.rglob("*") if p.is_file()}
    package = cavity_runtime.release_files(cavity_runtime.RELEASE, PROFILE)
    if any((bundle / name).read_bytes() != raw for name, raw in package.items()):
        raise ValueError("installed science differs from signed phase-release package")
    wide, band = read_band()
    measurements, audit, authorities, jobs, donor_graphs = [], {}, {}, [], {}
    for ident in ORDER:
        settings, (config, archive), (capture, _, target), bound = authority(ident, wide, band)
        chosen, counts = match_winners(capture, target)
        exchanged, singletons = shuffled(target, chosen)
        counts["null_singleton_strata"] = singletons
        measurements.append(dict(id=ident, matches=chosen))
        audit[ident], authorities[ident] = counts, bound
        print(ident, counts["selected"], flush=True)
        if ident not in ORDER[:4]:
            continue
        donor_path, config, archive = local_inputs(
            root,
            ident,
            config,
            archive,
            bound,
            settings["track_config_sha256"],
        )
        donor_graphs[ident] = (donor_path, config)
        for condition in CONDITIONS:
            diag_id = f"{ident}-{condition}"
            provenance = dict(
                id=diag_id,
                condition=condition,
                recipient_native_sha256=bound["native_sha"]["wide"],
                donor_native_sha256=bound["native_sha"]["capture-era"],
            )
            adjusted, changes = manipulate(target, chosen, condition, exchanged=exchanged)
            if condition != "stock":
                adjusted["provenance"] = dict(target["provenance"], alias_attribution=provenance)
            native = root / f"{diag_id}.json"
            payload = (
                gzip.decompress(Path(bound["paths"]["wide"]).read_bytes())
                if condition == "stock"
                else encoded(adjusted) + b"\n"
            )
            write(native, payload)
            binding = dict(
                settings,
                **provenance,
                changes=changes,
                native_sha256=_sha(native),
                origin_native_sha256=bound["native_sha"]["ordinary"],
            )
            if (
                condition == "stock"
                and binding["native_sha256"] != provenance["recipient_native_sha256"]
            ):
                raise ValueError("full wide control bytes changed")
            jobs.append((binding, native, config, archive, None))
    write_members(REPORT / "winner-pairs.jsonl.gz", measurements)
    save_json(REPORT / "match-audit.json", audit)
    paths = (
        Path(__file__),
        GRAPH,
        Path(__file__).with_name("alias_attribution.py"),
        Path(receiver.__file__),
        receiver.OBSERVER,
        REPORT / "PROTOCOL.md",
        BAND / "prediction-lock.json",
        SCREEN / "acquisition-support/peak-support/plan.json",
    )
    save_json(
        REPORT / "plan.json",
        dict(
            sources={str(p.relative_to(REPO)): _sha(p) for p in paths},
            files={
                name: _sha(REPORT / name) for name in ("winner-pairs.jsonl.gz", "match-audit.json")
            },
            authorities=authorities,
            inputs=[r[0] for r in jobs],
            receiver_files=inputs,
            cpus=CPUS,
            limit=LIMIT,
            memory_bytes=receiver.MEMORY,
            swap_bytes=0,
        ),
    )
    return bundle, donor_graphs, jobs


def capture_graph(root, bundle, cpu, ident, native, config):
    out = root / f"{ident}-capture-graph.json"
    log = out.with_suffix(".log")
    argv = [
        "systemd-run",
        "--user",
        "--wait",
        "--pipe",
        f"--property=MemoryMax={receiver.MEMORY}",
        "--property=MemorySwapMax=0",
        f"--property=RuntimeMaxSec={LIMIT}s",
        "--property=Nice=10",
        f"--setenv=TMPDIR={root}",
        *(f"--setenv={v}=1" for v in receiver.ENV),
        "/usr/bin/taskset",
        "-c",
        str(cpu),
        sys.executable,
        "-IB",
        str(GRAPH),
        str(bundle),
        str(native),
        str(config),
        str(out),
    ]
    with log.open("xb") as stream:
        rc = subprocess.run(
            argv, stdout=stream, stderr=subprocess.STDOUT, timeout=LIMIT + 15
        ).returncode
    numeric = (
        dict(status="ok", graph=read(out)) if rc == 0 and out.exists() else dict(status="failed")
    )
    return dict(id=ident, method="capture-era-graph", exit_code=rc, log_sha256=_sha(log), **numeric)


def run(root):
    root.mkdir(parents=True, exist_ok=False)
    bundle, graph_inputs, jobs = prepare(root)
    plan_path = REPORT / "plan.json"
    digest = _sha(plan_path)
    plan = read(plan_path)
    for path, value in plan["receiver_files"].items():
        check(bundle / path, value)
    config = receiver.WORKER.replace(
        'worker.__globals__["TMP"] = tmp\n',
        'worker.__globals__["TMP"] = tmp\n'
        + f"runpy.run_path({str(GRAPH)!r})['observe_graph'](tmp/'graph.json')\n",
    )
    if config == receiver.WORKER:
        raise ValueError("Graph observer insertion point changed")

    def lane(ident, cpu):
        measurements, graphs = [], [capture_graph(root, bundle, cpu, ident, *graph_inputs[ident])]
        for job in jobs:
            bound, native, *_ = job
            if bound["recording"] != ident:
                continue
            check(native, bound["native_sha256"])
            row = receiver.capped(root, root, job, PROFILE, cpu)
            scratch = root / "runs" / row["id"] / PROFILE
            graph = scratch / "graph.json"
            if graph.exists():
                graphs.append(
                    dict(id=row["id"], method="wide-graph", status="ok", graph=read(graph))
                )
            else:
                graphs.append(dict(id=row["id"], method="wide-graph", status="unavailable"))
            save_json(scratch / "receipt.json", row)
            measurements.append(row)
        return measurements, graphs

    results, graphs = [], []
    with patch.multiple(receiver, WORKER=config, LIMIT_S=LIMIT), ThreadPoolExecutor(2) as workers:
        for cohort in (ORDER[:2], ORDER[2:4]):
            tasks = [
                workers.submit(lane, ident, cpu) for ident, cpu in zip(cohort, CPUS, strict=True)
            ]
            for task in tasks:
                outcomes, traces = task.result()
                results.extend(outcomes)
                graphs.extend(traces)
            write_members(REPORT / "results.jsonl.gz", results)
            write_members(REPORT / "graph-traces.jsonl.gz", graphs)
            save_json(
                REPORT / "prediction-lock.json",
                dict(
                    cases=[r["id"] for r in results],
                    plan_sha256=digest,
                    files={
                        n: _sha(REPORT / n)
                        for n in ("results.jsonl.gz", "graph-traces.jsonl.gz", "plan.json")
                    },
                ),
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=local_output)
    run(parser.parse_args().root)
