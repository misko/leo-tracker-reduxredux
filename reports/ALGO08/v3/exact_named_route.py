"""Accelerate exact work around the original named v3 inference."""

import argparse
from collections import Counter
from contextlib import ExitStack, contextmanager
from functools import partial
import json
import os
from pathlib import Path
import runpy
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

from held_adaptive_0160 import PINS, catalogue_scope, digest, resident_path


CASES = {
    "0160": (3691, 2354, PINS, "named-0160"),
    "0316": (3042, 2702, {
        "request.json": "e1e3d9cd482bc4b8837f782c329702472b60e34eba8616616b5ec20ef759b739",
        "stock-clock.json": "0cff5ef787bb2f97fe13dc0ccfca4fdb4af64eb73778c8429d02c7605e58344d",
        "stock/joint-research-receipt.json": "d001e6d0182324b47a5c24b19ca16ece4767cce87ed8f4e4e17dd1b29289ffed",
        "stock/saved-0316-worker.json": "217e0bea9e40422d0d60f63ba71724c60b655529941dfebe698c6d55cf662201",
    }, "named-0316"),
}
SHARING = ROOT/"tools/pipeline_eval/variants/algo08_blind_rank.py"
SOURCES = (Path(__file__), SHARING, *(HERE/name for name in (
    "exact-named-route-protocol.md", "held_adaptive_0160.py", "named_history_once.py", "empty_bootstrap.py",
    "prospective_0316_solver.py", "joint_publication.py", "historical_orbit_index.py", "portable_orbit_index.py",
    "portable_orbit_compatibility.py", "combined_raw_research.py", "exact_graph_execution.py", "catalogue_block_rank.py",
    "cold_track_row_reuse.py", "stock_exact_gate_0402.py", "exact_noise_gate_0402.py", "grid_phase_state_reuse.py",
    "verified_png_reads.py",
)))


def read(path):
    return json.loads(path.read_bytes())


def bind(case):
    from exact_solver_0057 import ARTIFACT, ARTIFACT_SHA, PRODUCER_SHA
    from cold_track_row_reuse import SHARING_PIN

    issued, admitted, pins, _ = CASES[case]
    stage = Path(f"/dev/shm/leo-v3-saved-{case}-pair-01")
    req = read(resident_path(stage/"request.json"))
    archive = resident_path(Path(req["local_archive"]["root"]))
    inventory = resident_path(stage/"stock/fast-scan-inputs"/f"{req['session']}.json")
    producer = ARTIFACT.parent/"artifact-bind.json"
    pinned = {**{stage/p: value for p, value in pins.items()}, inventory: req["inventory"][7:],
              Path(req["offer_file"]): req["offer_sha256"], Path(req["native_file"]): req["native_sha256"],
              ARTIFACT: ARTIFACT_SHA[7:], producer: PRODUCER_SHA}
    for path, expected in pinned.items():
        if digest(resident_path(path)) != expected:
            raise ValueError(f"Unreviewed saved input {path}")
    source = {path.name: digest(path) for path in SOURCES}
    if (req["case"] != "DS30-"+case or archive != stage/"tle" or source[SHARING.name] != SHARING_PIN
            or read(producer)["source"]["cutoff_utc_ns"] >= req["causal_cutoff_utc_ns"]):
        raise ValueError("Expected the selected physical input and independently earlier source")
    return dict(case=req["case"], stage=str(stage), request=str(stage/"request.json"), archive=str(archive),
                inventory=str(inventory), packets={str(path): pin for path, pin in pinned.items()},
                issued=issued, admitted=admitted, sources=source, portable=[str(ARTIFACT), ARTIFACT_SHA, PRODUCER_SHA])


def checked_catalogue(binding, req, reader_class, canonical_digest):
    archive = resident_path(Path(binding["archive"]))
    refs = reader_class(archive).list_snapshots("space-track")
    local = req["local_archive"]
    if (len(refs) != local["snapshots"] or sum(ref.byte_size for ref in refs) != local["bytes"]
            or canonical_digest({ref.path.name: ref.sha256 for ref in refs}) != req["original_archive"]["snapshots_sha256"]
            or any(ref.collected_utc_ns >= req["causal_cutoff_utc_ns"] for ref in refs)):
        raise ValueError("Existing tmpfs catalogue differs from the signed causal view")
    for ref in refs:
        resident_path(ref.path)
    return archive, refs


def rank_with_exact_inputs(original, sharing, install, discovery, stats, work):
    def rank(scan):
        started = process_time_ns(), perf_counter_ns()
        with sharing(scan) as reused, ExitStack() as stack:
            tables = discovery.phase_linear_frequency.__self__
            try:
                stack.enter_context(install(scan, tables, work))
            except (AttributeError, ValueError):
                work["stock_curve_fallback"] += 1
            nodes = original(scan)
        stats.append(dict(nodes=len(nodes), cpu_ns=process_time_ns()-started[0],
                          elapsed_ns=perf_counter_ns()-started[1], inputs=dict(reused)))
        return nodes

    return rank


@contextmanager
def exact_ports(bound, req, audit):
    from catalogue_block_rank import install
    from combined_raw_research import Portable, portable_factory
    from exact_graph_execution import graph_execution
    from grid_phase_state_reuse import cached_predictive_grid
    from historical_orbit_index import guarded_preparation
    from leo.analysis.localization_v3 import discovery, family_cavity, feasible
    from leo.analysis.research import polynomial_satellite_diagnostics, retained_track_likelihood
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from stock_exact_gate_0402 import gate_binding, validate_released_ports
    from tools import algo08_position
    from tools.pipeline_eval.variants import v5_core

    probe = runpy.run_path(str(SHARING))["shared_rank_preparation"]
    rank = rank_with_exact_inputs(v5_core.ranked_initial_nodes, probe, install, discovery, audit["rank"], audit["blocks"])
    archive, refs = checked_catalogue(bound, req, TleArchiveReader, canonical_digest)
    read_verified = catalogue_scope(archive, refs, req["causal_cutoff_utc_ns"], TleArchiveReader.read, audit["verified_tle"])
    path, body, producer = bound["portable"]
    factory = partial(portable_factory, Portable(Path(path), body, producer), audit["portable"])
    prepare = guarded_preparation(algo08_position.prepare_native_scan, audit["portable"], index_factory=factory)
    validate_released_ports(feasible, family_cavity, retained_track_likelihood, polynomial_satellite_diagnostics)
    with ExitStack() as stack:
        stack.enter_context(patch.object(algo08_position, "prepare_native_scan", prepare))
        stack.enter_context(patch.object(TleArchiveReader, "read", read_verified))
        stack.enter_context(patch.object(v5_core, "ranked_initial_nodes", rank))
        stack.enter_context(graph_execution(enabled=True, audit=audit["graph"]))
        stack.enter_context(gate_binding(feasible, family_cavity, retained_track_likelihood, audit["gates"]))
        grids = stack.enter_context(cached_predictive_grid())
        yield
    audit["grid"] = dict(grids)


def worker(case, root):
    import empty_bootstrap as boot
    from aperture_trial import write
    from named_history_once import named_solve
    from prospective_0316_solver import worker as saved_worker
    import joint_publication as joint

    bound = read(root/"binding.json")["input"]
    if bound != bind(case):
        raise ValueError("The frozen input or source files changed")
    path = Path(bound["request"])
    req = read(path)
    output = root/"candidate"
    runtime, run, audits = boot.load_runtime, joint.run, {}
    audit = dict(rank=[], blocks=Counter(), graph={}, gates=Counter(), portable={}, png={}, verified_tle=Counter())
    with ExitStack() as stack:
        def load():
            loaded = runtime()
            audits["history"] = stack.enter_context(named_solve(True, boot.RELEASE, boot.PAYLOAD))
            return loaded

        def publish(*args, raw_context, **kwargs):
            from leo.storage.fast_standard_analysis import FastStandardAnalysisStore
            from verified_png_reads import VerifiedPngReads

            cache = VerifiedPngReads(output, joint.figure_evidence, audit["png"])
            @contextmanager
            def active(scan):
                with raw_context(scan), exact_ports(bound, req, audit), cache.capture(FastStandardAnalysisStore):
                    yield

            with patch.object(joint, "artifacts", partial(joint.artifacts, verified_read=cache.read)):
                return run(*args, raw_context=active, **kwargs)

        stack.enter_context(patch.object(boot, "load_runtime", load))
        stack.enter_context(patch.object(joint, "run", publish))
        saved_worker(path, "stock", output, source_pins={}, native_sha=req["native_sha256"], windows=bound["issued"],
                     admitted=bound["admitted"], inventory_file=Path(bound["inventory"]), audit_name="worker.json")
    write(output/"ports.json", audit | audits)


def launch(case, output, first):
    from aperture_trial import RELEASE, write

    sys.path.extend((str(ROOT/"src"), str(RELEASE/"src")))
    from dense_geographic_trial import host
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure

    machine = host()
    enrollment = bind(case)
    if case == "0316":
        if first is None:
            raise ValueError("Provide the sealed DS30-0160 result directory")
        gate = read(resident_path(first/"result.json"))
        if gate["case"] != "DS30-0160" or not gate["exact"] or gate["source_bindings"] != enrollment["sources"]:
            raise ValueError("The independent transfer requires verified earlier complete named parity")
    if resident_path(output.parent) != Path("/dev/shm") or output.exists():
        raise ValueError("Expected a fresh tmpfs output")
    stage = Path(enrollment["stage"])
    _, refs = checked_catalogue(enrollment, read(Path(enrollment["request"])), TleArchiveReader, canonical_digest)
    res = json.loads(subprocess.check_output(
        ["fincore", "--json", "--bytes", "-o", "RES,SIZE", *(r.path for r in refs)], text=True))["fincore"]
    if len(res) != len(refs) or any(row["res"] < row["size"] for row in res):
        raise ValueError("Every authenticated causal body must already be resident")
    output.mkdir(mode=0o700)
    (output/"fonts").mkdir()
    (output/"tmp").mkdir()
    for file in (stage/"fonts").glob("fontlist-*.json"):
        os.link(resident_path(file), output/"fonts"/file.name)
    cmd = ["/usr/bin/timeout", "--kill-after=2s", "55s", RELEASE/"venv/bin/python", "-IB", __file__, "worker", case, output]
    write(output/"binding.json", dict(input=enrollment, machine=machine, command=list(map(str, cmd)),
          resident_bytes=sum(row["size"] for row in res), resident_snapshots=len(refs), first_parity_path=str(first) if first else None))
    env = environment(output) | {"TMPDIR": str(output/"tmp"), "XDG_CACHE_HOME": str(output/"tmp")}
    write(output/"clock.json", measure(cmd, env, output/"candidate"))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker"))
    parser.add_argument("case", choices=CASES)
    parser.add_argument("output", type=Path)
    parser.add_argument("--first", type=Path)
    args = parser.parse_args()
    if args.action == "worker":
        worker(args.case, args.output)
    else:
        launch(args.case, args.output, args.first)
