"""Time one prospective matched block and a threshold-gated reverse block."""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

from residual_portable_saved import BASES, controls, digest, read, source_pins


PRIOR = Path("/dev/shm/leo-v3-residual-portable-0169-result02")
PIN = "c6922be6d55412b6d3144d2bf95b28c236697113f74f2f3c55ea89746122b68e"
CASE = "0169"
MODES = ("installed", "routed")
PROTOCOL = HERE/"clean-saved-0169-protocol.md"
ENTRY = HERE/"clean_saved_publication.py"
TARGET = 1.6
MARGIN = .05


def source_binding():
    return source_pins(CASE) | {path.name: digest(path) for path in (PROTOCOL, ENTRY, Path(__file__))}


def reverse_needed(value):
    return value["qualified"] and abs(value["times"]["elapsed_s"]["admitted_speedup"]/TARGET-1) <= MARGIN


def ratio(clocks, ready, common):
    result = {}
    for metric in ("elapsed_s", "cpu_s"):
        worker = {mode: clocks[mode][metric] for mode in MODES}
        pending = {mode: ready[mode][metric] for mode in MODES}
        charged = {mode: worker[mode]+pending[mode]+common[metric] for mode in MODES}
        result[metric] = dict(child=worker, per_arm_setup=pending, common_setup=common[metric], admitted=charged,
                              child_speedup=worker["installed"]/worker["routed"],
                              admitted_speedup=charged["installed"]/charged["routed"],
                              against_child_only_baseline=worker["installed"]/charged["routed"],
                              target_gap_s=charged["routed"]-charged["installed"]/TARGET)
    return result


def output_seal(root):
    return {str(path.relative_to(root)): digest(path) for path in root.rglob("*") if path.is_file()
            and path.relative_to(root).parts[0] not in ("fonts", "tmp")
            and path.name not in ("prediction-seal.json", "result.json")}


def launch(root, first=None):
    from aperture_trial import write
    from dense_geographic_trial import host
    from empty_bootstrap import RELEASE, clock, now
    from exact_named_route import checked_catalogue, resident_path
    from full_short_physical import environment
    from history_risk_route_trial import pinned, request_binding
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure
    from tools.pipeline_eval.qualification.paired_publication import NAMED_V3, verified_v3
    from visit_frame_raw_0016 import resident

    began = now()
    if root.exists() or resident_path(root.parent) != Path("/dev/shm"):
        raise ValueError("Need a new private tmpfs publication root")
    if first is not None:
        prior = read(resident_path(first/"result.json"))
        if not reverse_needed(prior) or prior["admission"]["order"] != list(MODES) or prior["admission"]["sources"] != source_binding():
            raise ValueError("The reverse block needs the same admitted threshold-near qualified initial comparison")
    verified = pinned(PRIOR/"result.json", PIN)
    baseline, control = controls(CASE)
    binding, request = request_binding(CASE)
    machine = host()
    sources = source_binding()
    if (not verified["qualified"] or verified["admission"]["scope"] != binding or control["binding.json"]["input"] != binding
            or machine != control["binding.json"]["machine"]):
        raise ValueError("Expected the prior original signed input, exact portable scope and identical host settings")
    _, refs = checked_catalogue(binding, request, TleArchiveReader, canonical_digest)
    archive = resident([resident_path(ref.path) for ref in refs])
    order = tuple(reversed(MODES)) if first else MODES
    root.mkdir(mode=0o700)
    (root/"tmp").mkdir()
    shutil.copytree(baseline/"fonts", root/"fonts")
    file = root/"job.json"
    write(file, dict(binding=binding, original_archive=request["original_archive"]))
    job = digest(file)
    release = verified_v3(NAMED_V3)
    studio = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    stages, commands = {}, {}
    common = clock(began)
    for mode in MODES:
        started = now()
        stage = root/mode
        stage.mkdir()
        argv = ["/usr/bin/timeout", "--kill-after=2s", "55s", str(RELEASE/"venv/bin/python"), "-IB",
                str(ENTRY), mode, str(file), job, str(stage)]
        commands[mode] = argv
        write(stage/"binding.json", dict(input=binding, command=argv))
        stages[mode] = clock(started)
    write(root/"admission.json", dict(order=order, previous_qualified_sha256=PIN, old_control=BASES[CASE][1], sources=sources,
          job_sha256=job, installed=release, machine=machine, archive=archive, commands=commands, common_setup=common,
          setup_per_worker=stages, prior_initial_sha256=digest(first/"result.json") if first else None))
    for mode in order:
        record = measure(commands[mode], studio, root/mode/"candidate")
        write(root/mode/"clock.json", record)
        if record["exit_code"]:
            break
    write(root/"prediction-seal.json", output_seal(root))


def score(root):
    from aperture_trial import write
    from exact_named_cairo_media import verify_publication
    from exact_named_route_score import parity
    from held_adaptive_0160_score import verified
    from history_risk_0169_input import STOCK_WORKER
    from history_risk_cairo_physical import clean
    from history_risk_residual_layout_0402 import require_active
    from history_risk_route_trial import pinned, request_binding
    from leo.storage.fast_standard_analysis import FastStandardAnalysisStore

    admission = read(root/"admission.json")
    if admission["sources"] != source_binding() or read(root/"prediction-seal.json") != output_seal(root):
        raise ValueError("The timed worker or published outputs changed")
    bound, request = request_binding(CASE)
    previous = pinned(PRIOR/"result.json", PIN)
    _, control = controls(CASE)
    archive = Path(bound["stage"])
    clocks = {mode: read(root/mode/"clock.json") for mode in MODES}
    outputs = {mode: root/mode/"candidate" for mode in MODES}
    records = {mode: verified(outputs[mode], clocks[mode], "worker.json", request) for mode in MODES}
    old_stock = verified(archive/"stock", control["result.json"]["archive_stock_clock"], STOCK_WORKER, request)
    old_Cairo = verified(PRIOR/"candidate", previous["measured"], "worker.json", request)
    checks = {"archived_installed": parity(old_stock, records["installed"]),
              "archived_conservative": parity(old_Cairo, records["routed"])}
    between, sides = verify_publication(records["installed"], records["routed"], outputs["installed"], outputs["routed"])
    for mode, old, old_dir in (("installed", old_stock, archive/"stock"), ("routed", old_Cairo, PRIOR/"candidate")):
        if not all(checks["archived_installed" if mode == "installed" else "archived_conservative"].values()):
            raise ValueError(f"Changed candidate or named publication on the same exact input: {mode}")
        actual = records[mode]
        run = actual["worker"]["receipt"]["run_id"]
        a, b = FastStandardAnalysisStore(outputs[mode]), FastStandardAnalysisStore(old_dir)
        for name, figure in old["products"]["images"].items():
            pin = figure["sha256"]
            if a.artifact(run, name, pin) != b.artifact(run, name, pin):
                raise ValueError(f"The saved PNG bytes differ from their archive: {mode} {name}")
    require_active(read(root/"routed/render-usage.json"))
    ports = read(outputs["routed"]/"ports.json")
    if (clean(ports["portable"]) != clean(previous["orbit_index"])
            or clean(read(root/"routed/risk-route.json")) != clean(read(PRIOR/"risk-route.json"))
            or tuple(ports["png"][kind] for kind in ("verified", "reused", "fallbacks")) != (8, 8, 0)
            or any(root.glob("**/*.pickle"))):
        raise ValueError("The qualified route, active index or all-product verification changed")
    times = ratio(clocks, admission["setup_per_worker"], admission["common_setup"])
    write(root/"result.json", dict(qualified=True, clocks=clocks, times=times, checks=checks | {"matched_pair": between},
          sidecar_bindings=sides, admission=admission, exact_cross_run_png_bytes=8,
          geographical=previous["geography"], prior_scene_export=previous["live_renderer"]["scene_capture"],
          historical_staging=read(archive/"launch.json"), historic_index_build=previous["admission"]["producer_clock"],
          science={mode: group["science"] for mode, group in records.items()}, published={mode: group["products"] for mode, group in records.items()},
          owned={mode: {arm: len(rows) for arm, rows in group["rows"].items()} for mode, group in records.items()},
          solve={mode: group["trace"]["solve"] for mode, group in records.items()}, portable=ports["portable"],
          figures=read(root/"routed/render-usage.json"), png_verification=ports["png"], prediction_sha256=digest(root/"prediction-seal.json"),
          clean_child_source=source_binding()[ENTRY.name], waveform_reads=0, original_archive_reads=0))


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "score"))
    parser.add_argument("root", type=Path)
    parser.add_argument("--initial", type=Path)
    opts = parser.parse_args()
    if opts.action == "launch":
        launch(opts.root, opts.initial)
    else:
        score(opts.root)
