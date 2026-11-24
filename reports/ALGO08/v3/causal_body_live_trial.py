"""Run the same DS30-0289 saved successor with live causal body election."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parents[2])]
SAVED = Path("/dev/shm/leo-v3-combined-successor-0289-01")
SAVED_SHA = "050fa5e968ce37036622b077e8bcd064ae02299b9e3d7bba4dbb26c0e148afae"
OWNERS_SHA = "94c09406fc926d689920d36f21bf1fd9acf877de5e5a222487f0a845d000fc07"


def pins():
    names = (Path(__file__).name, "causal-live-election-protocol.md", "causal_body_live.py",
             "causal_body_election.py", "historical_orbit_index.py")
    return {name: sha256((HERE/name).read_bytes()).hexdigest() for name in names}


def load(path):
    return json.loads(path.read_bytes())


def untimed(value):
    if isinstance(value, dict):
        return {name: untimed(row) for name, row in value.items() if name not in (
            "cpu_ns", "elapsed_ns", "geometry_guard_cpu_ns", "capture_cpu_ns")}
    if isinstance(value, list):
        return list(map(untimed, value))
    return value


def worker(root):
    from aperture_trial import write
    from causal_body_live import binding
    from combined_successor_0289 import worker as saved_worker

    if load(root/"admission.json")["live_election_sources"] != pins():
        raise ValueError("The admitted live election sources changed")
    audit = {}
    try:
        with binding(audit):
            saved_worker(root)
    finally:
        write(root/"routed/live-election.json", audit)


def launch(root):
    from aperture_trial import write
    import empty_bootstrap as boot
    from clean_saved_0169_trial import output_seal
    from combined_successor_0289 import prepare
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    common_start = boot.now()
    baseline = json.loads(boot.checked(SAVED/"result.json", SAVED_SHA))
    if not baseline["qualified"] or baseline["route"]["lean_attempts"][0]["repair"]["attempted_refits"] != 1:
        raise ValueError("Expected the same sealed complete combined support repair")
    command = prepare(root)
    command[5] = str(Path(__file__).resolve())
    path = root/"admission.json"
    admission = load(path)
    # Persist the actually launched command without removing the verified input
    # and original library/source checks from the ordinary successor admission.
    admission.update(command=command, causal_election=True, live_election_sources=pins(),
                     exact_combined_control=SAVED_SHA, charged_setup=boot.clock(common_start))
    fresh = root/"admission-live.json"
    write(fresh, admission)
    fresh.replace(path)
    env = environment(root) | {"TMPDIR": str(root/"tmp"), "XDG_CACHE_HOME": str(root/"tmp")}
    write(root/"routed/clock.json", measure(command, env, root/"routed/candidate"))
    write(root/"prediction-seal.json", output_seal(root))


def score(root):
    from aperture_trial import write
    from combined_successor_0289 import score as ordinary_score
    from empty_bootstrap import checked

    ordinary_score(root)
    baseline = json.loads(checked(SAVED/"result.json", SAVED_SHA))
    candidate = load(root/"result.json")
    if not candidate["qualified"]:
        raise ValueError("The active compatibility worker did not publish a qualified fix")
    source, proposal = baseline["publication"], candidate["publication"]
    folder = Path("routed/candidate/joint-research-receipt.json")
    old = json.loads(checked(SAVED/folder, OWNERS_SHA))
    new = load(root/folder)
    current_route = candidate["route"]
    original_route = baseline["route"]
    actual = load(root/"routed/live-election.json")
    elected, = actual["attempts"]
    science_keys = ("arms", "owners", "raw_authority", "reason", "scientific_digests")
    route_keys = ("choice", "lean_final_fit", "inference_calls")
    old_attempt, = original_route["lean_attempts"]
    new_attempt, = current_route["lean_attempts"]
    route_checks = {name: new_attempt.get(name) == old_attempt.get(name) for name in (
        "decision", "named_survivor_fit", "pair_passes", "repair", "exterior")}
    route_nomination = current_route["nomination_handoff"]
    old_nomination = original_route["nomination_handoff"]
    checks = dict(
        no_role_change=old["selected_rows"] == new["selected_rows"],
        both_positions_and_rf=candidate["science"]["successor"] == baseline["science"]["successor"],
        actual_native_arms=proposal["terminal"] == source["terminal"],
        signed_output_science=all(proposal["science"][key] == source["science"][key] for key in science_keys),
        paired_grid=proposal["sidecars"] == source["sidecars"] and new["solve"]["grid_points"] == 179,
        eight_pngs=len(proposal["figures"]) == 8 and proposal["figures"] == source["figures"],
        exact_runtime_route=all(untimed(current_route.get(key)) == untimed(original_route.get(key)) for key in route_keys),
        exact_nomination=untimed(route_nomination) == untimed(old_nomination),
        original_causal_reads=candidate["ports"]["verified_tle"] == baseline["ports"]["verified_tle"],
        support_and_geography=all(route_checks.values()) and candidate["geography"] == baseline["geography"],
        live_capture=elected["active_observers"] == elected["observed_regional_calls"] == elected["same_phase_handoffs"] == 1,
        active_election=elected.get("fallback") is None and elected["counts"]["initial_success"] == 1
            and elected["counts"]["history_success"] == 1 and elected["counts"]["projected_rows_not_scanned_again"] > 0,
    )
    table = {mode: dict(child=doc["clock"], numerical=doc["publication_clocks"],
                       initial_preparation=doc["ports"]["portable"]["attempts"],
                       route=doc["route"]["lean_attempts"][0]["repair_fit_clocks"],
                       grid=doc["traces"]["combined-grid.json"],
                       preflight=doc["admission"].get("charged_setup", doc["admission"]["setup"]))
             for mode, doc in (("combined_control", baseline), ("live_election", candidate))}
    write(root/"compatibility.json", dict(qualified=all(checks.values()), checks=checks, repair_checks=route_checks,
          clocks=table, sealed_control=SAVED_SHA, sealed_worker_owners=OWNERS_SHA, published_science=candidate["science"]["successor"],
          owned_by_arm={key: len(rows) for key, rows in new["selected_rows"].items()}, election=actual,
          live=candidate["traces"]["live-corner.json"], native_sha256=proposal["terminal"]["native_sha256"],
          sources=pins(), prediction_seal_sha256=candidate["prediction_seal_sha256"])))
    if not all(checks.values()):
        raise ValueError("The source-bound live compatibility comparison failed")


if __name__ == "__main__":
    from history_risk_weak_physical import deny_original

    sys.addaudithook(deny_original)
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "worker", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    {"launch": launch, "worker": worker, "score": score}[args.action](args.root)
