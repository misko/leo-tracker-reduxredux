"""Profile one public saved solve through the unmodified screened-stock freeze."""

import argparse
import cProfile
import json
import os
import pstats
import runpy
import subprocess
from contextlib import ExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from time import perf_counter, process_time
from types import SimpleNamespace
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
MEASUREMENTS = HERE / "measurements"


def worker(site, frozen, output):
    from tools.pipeline_eval.qualification import experimental_publication as publication
    from tools.pipeline_eval.variants.experimental import lean_startup

    specification = json.loads((frozen / "spec.json").read_bytes())
    if (not Path(publication.__file__).is_relative_to(frozen)
            or specification.get("startup") != "lazy-exports"):
        raise ValueError("Expected the fresh frozen publication entry point with lazy startup")
    native = json.loads((site / "native.json").read_bytes())
    diagnostics = {}
    profile = cProfile.Profile(timer=process_time)

    def from_saved(recording, _root, assets, archive, offer):
        from leo.operations.tle_archive import TleArchiveReader
        from tools import algo08_position

        if recording.name != "no-recording" or archive != site / "tle" or diagnostics:
            raise ValueError("Expected one saved detector callback")
        cpu, wall = process_time(), perf_counter()
        with profile:
            decision, packet, policy = algo08_position.solve(
                native, TleArchiveReader(archive), assets, offer,
            )
        diagnostics.update(
            solver_cpu_s=process_time() - cpu, solver_wall_s=perf_counter() - wall,
            stage_wall_s=decision["metrics"]["stage_s"], orbit_policy=policy,
        )
        if packet is None:
            raise ValueError(f"Expected the released containing fit: {decision['status']}")
        return dict(status=decision["status"], arms=decision["arms"],
                    owners={k: v["owner_sha256"] for k, v in packet["arms"].items()},
                    associated={k: v["associated_points"] for k, v in packet["arms"].items()})

    ordinary_install = lean_startup.install
    with TemporaryDirectory() as directory, ExitStack() as stack:
        root = Path(directory)

        def install_then_adapt():
            ordinary_install()
            from tools import algo08_scan

            stack.enter_context(patch.object(algo08_scan, "analyze", from_saved))

        stack.enter_context(patch.object(lean_startup, "install", install_then_adapt))
        args = SimpleNamespace(recording=root / "no-recording", bulk_root=root,
                               archive=site / "tle", region=site / "matched-tile.json")
        result = publication.run(args, specification)
    profile.dump_stats(output / "solver.prof")
    payload = dict(result=result, timing=diagnostics)
    (output / "terminal.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")


def profile_readout(path):
    stats = pstats.Stats(str(path))

    def lookup(file, function):
        record, = [value for (filename, _, name), value in stats.stats.items()
                   if Path(filename).name == file and name == function]
        return record[3]

    groups = dict(
        native_and_causal_preparation=lookup("regional_bound_guard.py", "prepare"),
        initial_search=lookup("algo08_stock_finish.py", "select"),
        conservative_recovery=lookup("conservative_recovery.py", "conservative_recovery"),
        family_history=lookup("history_policy.py", "history_policy"),
        signed_context=lookup("signed_context.py", "signed_context"),
        family_cavity=lookup("algo08_cavity_projection.py", "run")
        + lookup("family_cavity.py", "cavity_policy"),
        selected_packet=lookup("algo08_position.py", "selected_packet"),
    )
    subgroups = dict(
        salvage=lookup("conservative_recovery.py", "salvage"),
        objective_grid=lookup("experimental_publication.py", "posterior_grid"),
    )
    for file, name in (("retained_track_likelihood.py", "profile"),
                       ("polynomial_satellite_diagnostics.py", "batch_noise_screen")):
        callers, = [record[4] for (filename, _, function), record in stats.stats.items()
                    if Path(filename).name == file and function == name]
        calls, _, self_cpu, total_cpu = next(
            record for (filename, _, function), record in callers.items()
            if Path(filename).name == "conservative_recovery.py" and function == "salvage"
        )
        subgroups[f"salvage_{name}"] = dict(calls=calls, self_cpu_s=self_cpu, cpu_s=total_cpu)

    records = []
    for (filename, line, name), (primitive, calls, own, cumulative, _) in sorted(
            stats.stats.items(), key=lambda item: item[1][2], reverse=True)[:35]:
        records.append(dict(file=Path(filename).name, line=line, function=name, calls=calls,
                            primitive_calls=primitive, self_cpu_s=own, cumulative_cpu_s=cumulative))
    return dict(total_cpu_s=stats.total_tt, calls=stats.total_calls,
                primitive_calls=stats.prim_calls, groups_cpu_s=groups,
                subgroups=subgroups, self_time_top=records)


def run(scratch, frozen, output):
    from leo.contracts.digests import canonical_digest
    from tools.pipeline_eval.__main__ import THREAD_ENV
    from tools.pipeline_eval.qualification.paired_publication import verify_sources

    transfer = runpy.run_path(str(HERE / "covariance_transfer_trial.py"))
    audit = runpy.run_path(str(HERE / "complete_family_cavity_trial.py"))
    freeze = json.loads((MEASUREMENTS / "screened-stock-freeze.json").read_bytes())
    spec = json.loads((frozen / "spec.json").read_bytes())
    if spec != freeze["spec"] or canonical_digest(spec) != freeze["specification"]:
        raise ValueError("Expected the released screened-stock freeze")
    verify_sources(frozen / "reports/ALGO08/single-core-2x/run-candidate", spec["sources"])
    comparison = MEASUREMENTS / "screened-stock-recovery-containing.json"
    row, = [r for r in json.loads(comparison.read_bytes())["rows"]
            if r["case"] == transfer["SOUTH"]]
    site = scratch / row["case"]
    if (transfer["digest"]((site / "native.json").read_bytes()) != row["document_sha256"]
            or json.loads((site / "matched-tile.json").read_bytes()) != row["offer"]):
        raise ValueError("Expected the published containing offer and detector document")
    audit["verify_archive"](transfer, row, site)
    release = transfer["RELEASE"]
    env = dict(os.environ, PYTHONPATH=f"{frozen}:{release / 'src'}:{release}", **THREAD_ENV)
    command = [str(release / "venv/bin/python"), "-BPs", str(Path(__file__).resolve()), "worker"]
    output.mkdir(parents=True, exist_ok=False)
    subprocess.run([*command, *map(str, (site, frozen, output))], env=env, timeout=200, check=True)
    profiled = json.loads((output / "terminal.json").read_bytes())
    prior = row["builds"]["screened_stock_recovery"]
    outcome = profiled["result"]
    expected_arms = {k: {"latlon": v["latlon"], "rf_rms_hz": v["rf_rms_hz"]}
                     for k, v in prior["arms"].items()}
    if (outcome["arms"] != expected_arms
            or any(outcome[k] != prior[k] for k in ("status", "owners", "associated"))):
        raise ValueError("Profiled solve differs from the stored screened-stock result")
    source = output / "solver.prof"
    transfer["write"](output / "summary.json", dict(
        specification_sha256=freeze["specification"], native_sha256=row["document_sha256"],
        history_sha256=row["history_sha256"], status_and_both_arms_and_owners_equal=True,
        offer=row["offer"], stock_solver_cpu_s=row["builds"]["installed"]["solver_cpu_s"],
        prior_screened_solver_cpu_s=prior["solver_cpu_s"], profile_sha256=transfer["digest"](
            source.read_bytes(),
        ), profiler=profile_readout(source), **profiled,
    ))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("run", "worker"))
    parser.add_argument("inputs", type=Path)
    parser.add_argument("frozen", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    (run if args.action == "run" else worker)(args.inputs, args.frozen, args.output)
