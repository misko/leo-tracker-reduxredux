"""Price the optional nomination handoff on an already accepted saved DS30-0316."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import perf_counter_ns, process_time_ns
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RELEASE = Path("/opt/leo-algo08/bdb869682a2ea63af4b198a920b763a4c6a78c4c")
PAYLOAD = Path("/opt/leo-algo08/algo08v3/payload")
sys.path[:0] = list(map(str, (HERE, ROOT, RELEASE/"src", RELEASE, PAYLOAD)))

from history_risk_weak_physical import deny_original


CASE = "0316"
CONTROL = Path("/dev/shm/leo-v3-history-risk-0316-01")
PINS = {
    "result.json": "ef8d06eb9640e9e176b0e5dcf039f6497b5fd438d676ac46e430127994357849",
    "binding.json": "f239ea3a29d0e57c137771a7a85a863a2455ea0ccc2ac6af5e23d5e1c669a4df",
    "route-binding.json": "f5c266ce5407e7cabd3f12600ac8abbdf3cb54bc024af36cb995dd00a6dab4a3",
    "clock.json": "3f056478a8f8ae9f974bf7d06dfb71860e1fc0491b885d18059be30fc571c300",
    "risk-route.json": "d1aa51bad7494f7d56012257658bd52835afbbe01a18b130a4d29a072e5d0ac8",
    "candidate/ports.json": "95a4da1ba250f224333c7a17867bd2bcf13096fe1e63346f8d1bd7387be86187",
    "candidate/worker.json": "4094dbf5dc6985afe9040eff00339bb4a6da1bbb65a2a067de6ef7618315ef66",
    "candidate/joint-research-receipt.json": "27b2887a1d83b36f2d4fe67dd16e8b1889e4f9e06102a2212378295304d21d41",
}
FILES = ("nomination_handoff_0316.py", "nomination-handoff-0316-protocol.md", "nomination_handoff.py",
         "cold_finalist_race.py", "history_risk_route.py", "exact_named_route.py", "history_risk_route_trial.py")


def read(path):
    return json.loads(path.read_bytes())


def fingerprint(path):
    return sha256(path.read_bytes()).hexdigest()


def sources():
    return {name: fingerprint(HERE/name) for name in FILES}


def controls(trial):
    rows = {name: trial.pinned(CONTROL/name, digest) for name, digest in PINS.items()}
    previous = rows["route-binding.json"]["sources"]
    latest = trial.sources(CASE)
    launcher = "history_risk_route_trial.py"
    if ({k: v for k, v in previous.items() if k != launcher} != {k: v for k, v in latest.items() if k != launcher}
            or rows["result.json"]["clock"] != rows["clock.json"]
            or rows["result.json"]["route"]["route"] != "lean"):
        raise ValueError("The matched accepting input or numerical source changed")
    return rows


def observed_reuse(route):
    data = route.get("nomination_handoff", {})
    attempts = route["lean_attempts"]
    return dict(lean_complete_without_fallback=(route["choice"]["route"] == "lean" and len(attempts) == 1
                                                and attempts[0].get("decision") == "complete"
                                                and "fallback_clocks" not in attempts[0]),
                producer_captured_complete_rank_and_prefix=(data.get("ranked_nodes") == 6
                                                            and data.get("prefixes_captured") == 3),
                no_fallback_reuse=not any(data.get(k, 0) for k in ("rank_reuses", "prefixes_reused", "scan_reuses")))


def launch(root):
    import history_risk_route_trial as trial
    import short_raw_diagnostic
    from aperture_trial import write

    started = perf_counter_ns(), process_time_ns()
    old = controls(trial)
    measure = short_raw_diagnostic.measure

    def measured(command, env, destination):
        bound = read(root/"binding.json")
        if (bound["input"] != old["binding.json"]["input"] or bound["machine"] != old["binding.json"]["machine"]
                or {p.name: fingerprint(p) for p in (root/"fonts").glob("fontlist-*.json")} !=
                {p.name: fingerprint(p) for p in (CONTROL/"fonts").glob("fontlist-*.json")}):
            raise ValueError("The new worker changes a causal input, renderer font or execution condition")
        write(root/"handoff-binding.json", dict(
            control_sha256=PINS, sources=sources(), command=[str(p) for p in command],
            ordinary_route_binding_sha256=fingerprint(root/"route-binding.json"),
            ordinary_binding_sha256=fingerprint(root/"binding.json"),
            admission=dict(elapsed_ns=perf_counter_ns()-started[0], cpu_ns=process_time_ns()-started[1])))
        return measure(command, env, destination)

    command = [RELEASE/"venv/bin/python", "-IB", Path(__file__).resolve(), "worker"]
    with patch.object(short_raw_diagnostic, "measure", measured):
        trial.launch(CASE, root, stock_command=command)


def worker(destination):
    import history_risk_route_trial as trial
    from nomination_handoff import routed_binding

    root = destination.parent
    frozen = read(root/"handoff-binding.json")
    if (destination != root/"candidate" or frozen["sources"] != sources()
            or frozen["ordinary_route_binding_sha256"] != fingerprint(root/"route-binding.json")
            or frozen["ordinary_binding_sha256"] != fingerprint(root/"binding.json")):
        raise ValueError("The exact opt-in worker or its authenticated binding changed")
    with patch.object(trial, "binding", routed_binding):
        trial.worker(CASE, root)


def score(root):
    import history_risk_route_trial as trial
    from aperture_trial import write
    from exact_named_route_score import parity
    from held_adaptive_0160_score import verified

    old = controls(trial)
    assignment = read(root/"binding.json")["input"]
    req = trial.pinned(Path(assignment["request"]), assignment["packets"][assignment["request"]])
    live_clock = read(root/"clock.json")
    if live_clock["exit_code"]:
        raise ValueError("The sole candidate exited unsuccessfully and retained its external clock")
    before = verified(CONTROL/"candidate", old["clock.json"], "worker.json", req)
    after = verified(root/"candidate", live_clock, "worker.json", req)
    (route,) = read(root/"risk-route.json")["solves"]
    (old_route,) = old["risk-route.json"]["solves"]
    attempt = next(iter(route["lean_attempts"]), {})
    (prior_attempt,) = old_route["lean_attempts"]
    ports = read(root/"candidate/ports.json")
    checks = observed_reuse(route) | dict(
        same_two_round_branch=attempt.get("cold", {}).get("scores") == prior_attempt["cold"]["scores"]
        and attempt.get("cold", {}).get("branch") == prior_attempt["cold"]["branch"],
        same_signed_survivor_decision=attempt.get("named_survivor_fit", {}).get("status")
        == prior_attempt["named_survivor_fit"]["status"],
        full_grid=after["sample"] is not None and after["sample"]["complete"] and after["sample"]["evaluated_points"] == 179,
        one_preparation_and_solve=len(ports["history"]["prepare"]) == ports["history"]["solves"] == 1)
    same = parity(before, after)
    names = ("binding.json", "route-binding.json", "handoff-binding.json", "clock.json", "risk-route.json",
             "candidate/worker.json", "candidate/joint-research-receipt.json", "candidate/ports.json")
    write(root/"result.json", dict(
        case=req["case"], checks=checks, parity=same, handoff=route.get("nomination_handoff", {}),
        route=route["choice"]["route"], attempt_decision=attempt.get("decision"), attempt_reason=attempt.get("reason"),
        phase_inputs_sha256=req["native_sha256"], clocks=dict(candidate=live_clock, earlier_routed=old["clock.json"],
            archived_installed=old["result.json"]["archive_stock_clock"], archived_exact=old["result.json"]["archived_exact_clock"]),
        candidate_admission=read(root/"handoff-binding.json")["admission"], prior_admission=old["route-binding.json"]["preflight"],
        cold_cpu_s=dict(before=prior_attempt["cold_clocks"]["cpu_s"], after=attempt.get("cold_clocks", {}).get("cpu_s")),
        pre_evidence_cpu_s=dict(before=prior_attempt["candidate_pre_evidence_clocks"]["cpu_s"],
                                after=attempt.get("candidate_pre_evidence_clocks", {}).get("cpu_s")),
        receiver_and_phase_inputs=assignment["packets"], rank=ports["rank"], blocks=ports["blocks"],
        science=old["result.json"]["scientific"]["runs"] if all(same.values()) else None,
        terminal=after["terminal"], figure_products=after["products"], sources=read(root/"handoff-binding.json")["sources"],
        owners={k: len(v) for k,v in after["rows"].items()}, archive_prepare=ports["history"]["prepare"],
        process_and_publication_sha256={name: fingerprint(root/name) for name in names}, controls=PINS,
        no_original_recording_read=True, no_backing_archive_read=True))
    if not all(same.values()) or not all(checks.values()):
        raise ValueError("The sealed accepting-control result did not preserve all prespecified evidence")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("launch", "score", "worker"))
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    sys.addaudithook(deny_original)
    {"launch": launch, "score": score, "worker": worker}[args.action](args.root)
