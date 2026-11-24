"""Run the saved DS30-0004 worker with the optional exact nomination bridge."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
PAYLOAD = Path("/opt/leo-algo08/algo08v3/payload")
sys.path[:0] = list(map(str, (HERE, ROOT, RELEASE/"src", RELEASE, PAYLOAD)))
from history_risk_0004 import binding, deny_original, prior
from nomination_handoff_trial import PAIR, PINS


STAGE = PAIR.with_name(PAIR.name+"-inputs")
CONTROL = PINS | {
    "routed/route-binding.json": "37ed553a199128fff8148feafb0ce55994cccaebaf0f813bce238851d115b4ad",
    "pair-binding.json": "bcaefaae8e9737b12d1d5a6a9a7c0164400bc6827789eaf02932cea238ddb400",
    "routed/clock.json": "04c39799fbce8f6a9105a61ae5339614964ab5fcaffa7d4588d10410859bbc28",
    "named/clock.json": "8f2e861bb78cc61c2579c409237781d4741dcd6aaefbd9237b64619dd00283ec",
    "result.json": "89aeaee758857adfad44ceb7980bff7a0da7371e04739ef3b79e3d3023d389d6",
}
REQUEST_SHA = "cbe6833176539c0d99d427b93f3c48040bab4aad9b858dc145fb44b3a7d9bb97"
FILES = ("nomination_handoff_publication.py", "nomination_handoff.py", "nomination-handoff-publication-protocol.md",
         "history_risk_route.py", "cold_finalist_race.py", "joint_publication.py")


def file_sha(path):
    return sha256(path.read_bytes()).hexdigest()


def originals():
    from exact_named_route import resident_path

    docs = {}
    for name, pin in CONTROL.items():
        body = resident_path(PAIR/name).read_bytes()
        if sha256(body).hexdigest() != pin:
            raise ValueError(f"The authenticated prior saved control changed: {name}")
        docs[name] = json.loads(body)
    return docs


def admission():
    from exact_named_route import resident_path
    from leo.operations.tle_archive import TleArchiveReader

    request = resident_path(STAGE/"request.json")
    if file_sha(request) != REQUEST_SHA:
        raise ValueError("Expected the originally staged signed saved request")
    with binding(STAGE):
        bound, req = prior.bound_request()
    archive = resident_path(Path(bound["archive"]))
    refs = TleArchiveReader(archive).list_snapshots("space-track")
    cache = json.loads(subprocess.check_output(
        ["fincore", "--json", "--bytes", "-o", "RES,SIZE", *(resident_path(r.path) for r in refs)]
    ))["fincore"]
    if len(cache) != req["local_archive"]["snapshots"] or any(row["res"] < row["size"] for row in cache):
        raise ValueError("The admitted causal snapshot roster is no longer fully resident")
    return bound, req, sum(row["size"] for row in cache)


def worker(root):
    import history_risk_route_trial as trial
    from nomination_handoff import routed_binding

    sealed = json.loads((root/"run-binding.json").read_bytes())
    if sealed["source_sha256"] != {name: file_sha(HERE/name) for name in FILES}:
        raise ValueError("The original saved worker or selected prototype changed")
    with binding(STAGE), patch.object(trial, "binding", routed_binding):
        prior.worker(root/"routed", "routed")


def launch(root):
    from aperture_trial import write
    from dense_geographic_trial import host
    from exact_named_route import resident_path
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    wall, cpu = perf_counter_ns(), process_time_ns()
    if resident_path(root.parent) != Path("/dev/shm") or root.exists():
        raise ValueError("Expected a fresh tmpfs candidate")
    machine = host()
    if machine["cpu"] != [2] or machine["nice"] != 15 or "prio 7" not in machine["ionice"]:
        raise ValueError("Use the single existing low-priority Gauss slot")
    controls = originals()
    bound, _, resident = admission()
    if bound != controls["routed/binding.json"]["input"]:
        raise ValueError("The candidate changes the old causal or saved input")
    root.mkdir(mode=0o700)
    for name in ("tmp", "fonts", "routed"):
        (root/name).mkdir()
    fonts = controls["pair-binding.json"]["common_font_cache"]
    for name, pin in fonts.items():
        source = resident_path(PAIR/"fonts"/name)
        if file_sha(source) != pin:
            raise ValueError("The shared renderer font seed changed")
        os.link(source, root/"fonts"/name)
    command = ["/usr/bin/timeout", "--kill-after=2s", "110s", str(RELEASE/"venv/bin/python"),
               "-IB", str(Path(__file__).resolve()), "worker", str(root)]
    write(root/"routed/binding.json", dict(input=bound, command=command))
    write(root/"routed/route-binding.json", controls["routed/route-binding.json"])
    write(root/"run-binding.json", dict(input=bound, controls=CONTROL, machine=machine, command=command,
          resident_archive_bytes=resident, font_sha256=fonts, source_sha256={k: file_sha(HERE/k) for k in FILES},
          preflight=dict(elapsed_ns=perf_counter_ns()-wall, cpu_ns=process_time_ns()-cpu)))
    clock = measure(command, environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")},
                    root/"routed/candidate")
    write(root/"routed/clock.json", clock)
    if clock["exit_code"]:
        raise ValueError("The candidate stopped before ordinary completion; preserved external clock")


def score(root):
    from aperture_trial import write
    from exact_named_route_score import parity
    from held_adaptive_0160_score import verified

    control = originals()
    run = json.loads((root/"run-binding.json").read_bytes())
    request = STAGE/"request.json"
    if file_sha(request) != REQUEST_SHA:
        raise ValueError("The staged named request changed after the run")
    req = json.loads(request.read_bytes())
    clock = json.loads((root/"routed/clock.json").read_bytes())
    stock = verified(PAIR/"named/candidate", control["named/clock.json"], "worker.json", req)
    found = verified(root/"routed/candidate", clock, "worker.json", req)
    same = parity(stock, found)
    routed, = json.loads((root/"routed/risk-route.json").read_bytes())["solves"]
    attempt, = routed["lean_attempts"]
    prior_route, = control["routed/risk-route.json"]["solves"]
    earlier, = prior_route["lean_attempts"]
    metrics = found["worker"]["receipt"]["screened_nomination"]
    guard = routed["nomination_handoff"]
    verified_fields = ("screen_c0_scores", "completed_c0_score", "ranks", "winning_rank", "fallback")
    gates = dict(reused_rank=guard["rank_reuses"] == 1, reused_prefix=guard["prefixes_reused"] == 3,
                 original_screen=all(metrics[k] == stock["worker"]["receipt"]["screened_nomination"][k]
                                     for k in verified_fields),
                 both_arms=tuple(sorted(found["rows"])) == ("c0", "fitted_c"),
                 complete_grid=found["sample"]["complete"] and found["sample"]["evaluated_points"] == 179,
                 fallback=attempt["reason"] == earlier["reason"] == "repair_rejection_cap")
    ports = json.loads((root/"routed/candidate/ports.json").read_bytes())
    result = dict(case=req["case"], scientific_exact=all(same.values()), parity=same, handoff_checks=gates,
                  handoff=guard, input_sha256=REQUEST_SHA, source_pins=run["source_sha256"],
                  admission=run["preflight"], clocks=dict(candidate=clock, named=control["named/clock.json"],
                      earlier_routed=control["routed/clock.json"]),
                  solve=found["worker"]["solve"], controls=CONTROL,
                  science=control["result.json"]["scientific"]["runs"]["named"] if all(same.values()) else None,
                  owners={arm: len(rows) for arm, rows in found["rows"].items()}, figure_products=found["products"],
                  rank=ports["rank"], preparation=ports["history"]["prepare"],
                  candidate_clocks={key: attempt[key] for key in ("candidate_pre_evidence_clocks", "cold_clocks", "fallback_clocks")},
                  control_clocks={key: earlier[key] for key in ("candidate_pre_evidence_clocks", "cold_clocks", "fallback_clocks")},
                  artifacts_sha256={name: file_sha(root/name) for name in ("run-binding.json", "routed/clock.json",
                      "routed/risk-route.json", "routed/candidate/ports.json", "routed/candidate/worker.json")},
                  no_original_recording_read=True, no_backing_archive_read=True)
    write(root/"result.json", result)
    if not all(same.values()) or not all(gates.values()):
        raise ValueError("The saved candidate did not preserve all named products and the planned handoff")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "score", "worker"))
    parser.add_argument("root", type=Path)
    options = parser.parse_args()
    sys.addaudithook(deny_original)
    {"launch": launch, "score": score, "worker": worker}[options.action](options.root)
