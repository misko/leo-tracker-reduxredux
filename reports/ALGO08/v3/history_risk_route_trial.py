"""Run the earlier orbit risk router on two sealed, resident named packets."""

import argparse
from contextlib import contextmanager
from pathlib import Path
import json
import os
import subprocess
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

import exact_named_route as exact
from history_risk_route import binding


EARLIER = (Path("/dev/shm/leo-v3-early-causal-history-run/census/result.json"),
           "1f69aeebd9826a2af6b7beee9bfd414c65fd5f89c6441a0e1f2a4e391dcc372b")
EXACT = {
    "0160": (Path("/dev/shm/leo-v3-exact-named-0160-result01"), "dd1f4a2f3891bba9a5ae9985f87273117223b137e398f39334e5b6edb3e1016b"),
    "0316": (Path("/dev/shm/leo-v3-exact-named-0316-result02"), "f53bfaad5a6b849398dce78bd7669c6d845f6bd886474a96ce71981c49464bc8"),
}
LEAN = Path("/dev/shm/leo-v3-final-0316-transfer-result02")
LEAN_WITNESS_SHA = "ebbaed6c90a1d03b229b4199835bcc399984eee2524755b8b2e7d0470c907d1f"
EXPECTED = {"0160": "named", "0316": "lean"}


def sources():
    names = ("history_risk_route.py", "history_risk_route_trial.py", "history-risk-route-protocol.md", "early_causal_history.py",
             "prepared_exterior.py", "cold_finalist_race.py", "certified_salvage.py", "isolated_salvage.py", "named_survivor_fit.py",
             "blind_joint_route.py", "blind_joint_finish.py", "blind_joint_repair.py", "blind_joint_signed.py")
    return {name: exact.digest(HERE/name) for name in names}


def pinned(path, digest):
    path = exact.resident_path(path)
    if exact.digest(path) != digest:
        raise ValueError(f"The archive reference changed: {path}")
    return exact.read(path)


def worker(case, output):
    from aperture_trial import write
    import named_history_once as history

    enrollment = exact.read(output/"route-binding.json")
    if enrollment["sources"] != sources():
        raise ValueError("The frozen risk route sources changed")
    original_named, original_ports = history.named_solve, exact.exact_ports
    audit = dict(solves=[])
    rank = None

    @contextmanager
    def exact_ports(*args, **kwargs):
        nonlocal rank
        from tools.pipeline_eval.variants import v5_core

        rank = v5_core.ranked_initial_nodes
        with original_ports(*args, **kwargs):
            yield

    @contextmanager
    def named(enabled, release, payload):
        from tools import algo08_scan

        with original_named(enabled, release, payload) as original_audit:
            ordinary = algo08_scan.solve

            def dispatch(native, reader, assets, offer):
                if rank is None:
                    raise ValueError("The shared exact numerical bindings are unavailable")
                audit["solves"].append(route := {})
                with binding(reader, enrollment["cutoff_utc_ns"], route, rank):
                    return ordinary(native, reader, assets, offer)

            with patch.object(algo08_scan, "solve", dispatch):
                yield original_audit

    try:
        with patch.object(history, "named_solve", named), patch.object(exact, "exact_ports", exact_ports):
            exact.worker(case, output)
    finally:
        write(output/"risk-route.json", audit)


def launch(case, output):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from leo.contracts.digests import canonical_digest
    from leo.operations.tle_archive import TleArchiveReader
    from short_raw_diagnostic import measure

    started = process_time_ns(), perf_counter_ns()
    machine = host()
    entry = exact.bind(case)
    request = exact.read(Path(entry["request"]))
    archive, archive_pin = EXACT[case]
    if not pinned(archive/"result.json", archive_pin)["exact"]:
        raise ValueError("The ordinary exact reference was not verified")
    pinned(*EARLIER)
    if case == "0316":
        pinned(LEAN/"candidate/joint-research-receipt.json", LEAN_WITNESS_SHA)
    if exact.resident_path(output.parent) != Path("/dev/shm") or output.exists():
        raise ValueError("Expected a fresh tmpfs root")
    _, refs = exact.checked_catalogue(entry, request, TleArchiveReader, canonical_digest)
    residence = json.loads(subprocess.check_output(
        ["fincore", "--json", "--bytes", "-o", "RES,SIZE", *(ref.path for ref in refs)], text=True))["fincore"]
    if len(residence) != len(refs) or any(row["res"] < row["size"] for row in residence):
        raise ValueError("The previously admitted causal snapshots must remain resident")
    output.mkdir(mode=0o700)
    (output/"fonts").mkdir()
    (output/"tmp").mkdir()
    for file in (Path(entry["stage"])/"fonts").glob("fontlist-*.json"):
        os.link(exact.resident_path(file), output/"fonts"/file.name)
    command = ["/usr/bin/timeout", "--kill-after=2s", "55s", RELEASE/"venv/bin/python",
               "-IB", HERE/Path(__file__).name, "worker", case, output]
    write(output/"binding.json", dict(input=entry, machine=machine, command=list(map(str, command)),
          resident_bytes=sum(row["size"] for row in residence), resident_snapshots=len(refs)))
    write(output/"route-binding.json", dict(sources=sources(), cutoff_utc_ns=request["causal_cutoff_utc_ns"],
          earlier_reference=str(EARLIER[0]), earlier_sha256=EARLIER[1], control_sha256=archive_pin,
          preflight=dict(cpu_ns=process_time_ns()-started[0], elapsed_ns=perf_counter_ns()-started[1])))
    env = environment(output) | {"TMPDIR": str(output/"tmp"), "XDG_CACHE_HOME": str(output/"tmp")}
    write(output/"clock.json", measure(command, env, output/"candidate"))


def score(case, output):
    from aperture_trial import write
    from exact_named_route_score import parity
    from held_adaptive_0160_score import verified
    from prospective_0316_solver import owner_delta
    from triage_bounds import calibration_comparison

    assignment = exact.read(output/"binding.json")["input"]
    req = exact.read(Path(assignment["request"]))
    clock = exact.read(output/"clock.json")
    control_path, control_pin = EXACT[case]
    control = pinned(control_path/"result.json", control_pin)
    named = verified(control_path/"candidate", control["clocks"]["candidate"], "worker.json", req)
    actual = verified(output/"candidate", clock, "worker.json", req)
    route, = exact.read(output/"risk-route.json")["solves"]
    ports = exact.read(output/"candidate/ports.json")
    proof = route["choice"]
    if proof["route"] != EXPECTED[case] or proof["census"]["cutoff_utc_ns"] != req["causal_cutoff_utc_ns"]:
        raise ValueError("The risk flag did not choose the frozen authentic branch")
    if (len(ports["history"]["prepare"]) != 1 or route["inference_calls"] != 1
            or ports["history"]["solves"] != 1 or len(actual["products"]["images"]) != 8
            or actual["sample"]["evaluated_points"] != 179 or not actual["sample"]["complete"]):
        raise ValueError("The candidate owes one real preparation and a complete saved publication")
    matches = parity(named, actual)
    lean = None
    if case == "0160":
        if not all(matches.values()) or route["lean_attempts"] or not ports["history"]["events"]:
            raise ValueError("The flagged packet must preserve ordinary named decisions and media")
    else:
        archived = LEAN/"candidate"
        prior_clock = exact.read(LEAN/"candidate-clock.json")
        lean = verified(archived, prior_clock, "saved-0316-worker.json", req)
        trial, = route["lean_attempts"]
        if (trial["decision"] != "complete" or trial["named_survivor_fit"]["status"] != "accepted"
                or actual["terminal"] != lean["terminal"] or actual["rows"] != lean["rows"]):
            raise ValueError("The clear branch did not reproduce the genuine lean named-survivor publication")
    original = {"named": named["science"], "routed": actual["science"]}
    summaries = {k: {arm: data["arms"][arm] for arm in ("c0", "fitted_c")} for k, data in original.items()}
    write(output/"result.json", dict(case=req["case"], route=proof, preparation=ports["history"],
          exterior_handoff=route["exterior_handoff"], named_parity=matches,
          lean_terminal_equal=bool(lean and actual["terminal"] == lean["terminal"]),
          clock=clock, archived_exact_clock=control["clocks"]["candidate"], archive_stock_clock=control["clocks"]["named"],
          archived_lean_clock=lean["clock"] if lean else None,
          owners={arm: owner_delta(named["rows"][arm], actual["rows"][arm]) for arm in ("c0", "fitted_c")},
          published=dict(worker=actual["worker"], terminal=actual["terminal"], products=actual["products"], science=actual["science"]),
          scientific=calibration_comparison({k: dict(arms=v) for k, v in summaries.items()}, req["case"]),
          binds={file: exact.digest(output/file) for file in
                 ("binding.json", "route-binding.json", "clock.json", "risk-route.json", "candidate/ports.json")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "score"))
    parser.add_argument("case", choices=EXPECTED)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    {"launch": launch, "worker": worker, "score": score}[args.action](args.case, args.output)
