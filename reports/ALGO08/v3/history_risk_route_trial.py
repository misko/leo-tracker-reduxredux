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
    "0374": (Path("/dev/shm/leo-v3-exact-named-0374-result01"), "cdc50f9118442a98be515c57115a351f83464476920f83356f4d8bf6140cd99a"),
}
LEAN = Path("/dev/shm/leo-v3-final-0316-transfer-result02")
LEAN_WITNESS_SHA = "ebbaed6c90a1d03b229b4199835bcc399984eee2524755b8b2e7d0470c907d1f"
EXACT_ROUTE_SHA256 = "8799f632207d4a1b65954e454766605dcad109a799b9b81a08158c3a2ebc26ff"
DENSE_LEAN_CLOCK_SHA256 = "06eb41d41537adb0783b049258f0964e1fce5b744093a79b1994b4d1ff346c02"
DENSE_LEAN_WITNESS_SHA256 = "46080930eec33cf3586d8dc226c86d56324b734ef18349445b502bd31556d4e9"
EXPECTED = {"0160": "named", "0316": "lean"}


def request_binding(case):
    if case != "0374":
        bound = exact.bind(case)
        return bound, exact.read(Path(bound["request"]))
    import exact_named_dense as dense

    # Reuse the earlier authenticated request adapter with this trial's exact
    # route source pinned explicitly. Neither admission changes the saved input.
    with patch.object(dense, "SOURCE_SHA256", EXACT_ROUTE_SHA256):
        return dense.binding(case)


def sources(case):
    names = ("history_risk_route.py", "history_risk_route_trial.py", "history-risk-route-protocol.md", "early_causal_history.py",
             "prepared_exterior.py", "cold_finalist_race.py", "certified_salvage.py", "isolated_salvage.py", "named_survivor_fit.py",
             "blind_joint_route.py", "blind_joint_finish.py", "blind_joint_repair.py", "blind_joint_signed.py")
    if case == "0374":
        names += ("history-risk-0374-protocol.md", "exact_named_dense.py")
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
    if enrollment["sources"] != sources(case):
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
            if case != "0374":
                exact.worker(case, output)
            else:
                bound, request = request_binding(case)
                guard_read = exact.read

                def request_view(path):
                    return request if path == Path(bound["request"]) else guard_read(path)

                with patch.object(exact, "bind", return_value=bound), patch.object(exact, "read", request_view):
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
    entry, request = request_binding(case)
    archive, archive_pin = EXACT[case]
    if not pinned(archive/"result.json", archive_pin)["exact"]:
        raise ValueError("The ordinary exact reference was not verified")
    pinned(*EARLIER)
    if case == "0316":
        pinned(LEAN/"candidate/joint-research-receipt.json", LEAN_WITNESS_SHA)
    elif case == "0374":
        stage = Path(entry["stage"])
        pinned(stage/"combined/joint-research-receipt.json", DENSE_LEAN_WITNESS_SHA256)
        pinned(stage/"combined-clock.json", DENSE_LEAN_CLOCK_SHA256)
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
    write(output/"route-binding.json", dict(sources=sources(case), cutoff_utc_ns=request["causal_cutoff_utc_ns"],
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
    if (case in EXPECTED and proof["route"] != EXPECTED[case]
            or "census" in proof and proof["census"]["cutoff_utc_ns"] != req["causal_cutoff_utc_ns"]):
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
    elif case == "0316":
        archived = LEAN/"candidate"
        prior_clock = exact.read(LEAN/"candidate-clock.json")["timing"]
        lean = verified(archived, prior_clock, "saved-0316-worker.json", req)
        trial, = route["lean_attempts"]
        if (trial["decision"] != "complete" or trial["named_survivor_fit"]["status"] != "accepted"
                or actual["terminal"] != lean["terminal"] or actual["rows"] != lean["rows"]):
            raise ValueError("The clear branch did not reproduce the genuine lean named-survivor publication")
    else:
        stage = Path(assignment["stage"])
        prior_clock = pinned(stage/"combined-clock.json", DENSE_LEAN_CLOCK_SHA256)
        pinned(stage/"combined/joint-research-receipt.json", DENSE_LEAN_WITNESS_SHA256)
        lean = verified(stage/"combined", prior_clock, "named-final-0374-worker.json", req)
        if proof["route"] == "named" and (not all(matches.values()) or route["lean_attempts"]):
            raise ValueError("Flagged held transfer differs from the named publication")
    original = {"named": named["science"], "routed": actual["science"]}
    if lean is not None:
        original["lean"] = lean["science"]
    summaries = {k: {arm: data["arms"][arm] for arm in ("c0", "fitted_c")} for k, data in original.items()}
    write(output/"result.json", dict(case=req["case"], route=proof, preparation=ports["history"],
          exterior_handoff=route["exterior_handoff"], named_parity=matches,
          lean_terminal_equal=bool(lean and actual["terminal"] == lean["terminal"]),
          clock=clock, archived_exact_clock=control["clocks"]["candidate"], archive_stock_clock=control["clocks"]["named"],
          archived_lean_clock=lean["clock"] if lean else None,
          lean_parity=parity(lean, actual) if lean else None,
          lean_owner_delta={arm: owner_delta(lean["rows"][arm], actual["rows"][arm]) for arm in ("c0", "fitted_c")} if lean else None,
          lean_attempts=[{k: row[k] for k in ("candidate_pre_evidence_clocks", "named_survivor_fit", "exterior_clocks",
                                             "standard_evidence_clocks", "decision") if k in row} for row in route["lean_attempts"]],
          owners={arm: owner_delta(named["rows"][arm], actual["rows"][arm]) for arm in ("c0", "fitted_c")},
          published=dict(worker=actual["worker"], terminal=actual["terminal"], products=actual["products"], science=actual["science"]),
          scientific=calibration_comparison({k: dict(arms=v) for k, v in summaries.items()}, req["case"]),
          binds={file: exact.digest(output/file) for file in
                 ("binding.json", "route-binding.json", "clock.json", "risk-route.json", "candidate/ports.json")}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "worker", "score"))
    parser.add_argument("case", choices=EXACT)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    {"launch": launch, "worker": worker, "score": score}[args.action](args.case, args.output)
