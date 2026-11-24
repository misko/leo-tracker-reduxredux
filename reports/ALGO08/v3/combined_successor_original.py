"""Measure one original positive and its prespecified contingent withholding control."""

import argparse
import json
import os
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
from shutil import copytree
import subprocess
import sys


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]
PRIOR = Path("/dev/shm/leo-v3-verify-original-once-result01")
PRIOR_SHA = "4446a97aeba1b496a4c96ed949b43d3d6984432b4ac8f3087d8c8fafbd6c1555"
POSITIVE, TINY = CASES = "DS30-0016", "DS30-0107"
PORT = HERE/"combined_successor_raw_entry.py"
SCOPE = Path("reports/ALGO08/v3")
EXTRA = [SCOPE/name for name in (
    Path(__file__).name, PORT.name, "combined-successor-original-protocol.md", "combined_successor.py",
    "nomination_handoff.py", "two_centre_seeds.py", "live_orbit_support.py", "solver_exception_0022.py")]
EXTRA.append(Path("tools/pipeline_eval/variants/v5_orbit_domain.py"))
EXTRA.extend(Path("tools/pipeline_eval/variants/experimental")/f"{name}.py" for name in (
    "receiver_ingress", "receiver_member_lookahead", "receiver_member_prefetch"))


def command_for(old, target):
    required = {"--verify-original-once", "--legacy-first-map-fast", "--history-risk-route", "--cairo-residual-layout"}
    incompatible = ("--legacy-first-map-replay", "--legacy-first-map-plan", "--legacy-map-custody",
                    "--cairo-six-sheets", "--visit-frame-custody", "--strict-packed", "--first-map-setup-only")
    if (Path(old[5]).name != "legacy_first_map_entry.py" or not required <= set(old)
            or any(value.startswith(incompatible) for value in old)):
        raise ValueError("Expected the identical original verified-once receiver and publisher")
    current = list(old)
    current[5] = str(PORT)
    current[current.index("--output")+1] = str(target)
    return current


def sources(prior):
    from visit_frame_raw_0016 import digest

    old = {name: pin.removeprefix("sha256:") for name, pin in prior["admission"]["sources"].items()}
    current = {name: digest(ROOT/name).removeprefix("sha256:") for name in old}
    if current != old:
        raise ValueError("One or more inherited verified-once sources changed")
    return current | {str(path): digest(ROOT/path).removeprefix("sha256:") for path in EXTRA}


def previous():
    from empty_bootstrap import checked
    from exact_named_raw import staged_path

    return json.loads(checked(staged_path(PRIOR/"verified-once.json"), PRIOR_SHA))


def allowed_tiny(positive, clock):
    return bool(positive.get("qualified") and not clock["exit_code"] and
                clock["elapsed_s"] < positive["verified_once"]["elapsed_s"])


def prepare(root, case, *, short_pin=None, positive_reference=None):
    import empty_bootstrap as boot
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from dense_geographic_trial import host
    from eight_ms_south_transfer import environment_for
    from legacy_first_map_acceleration import checked_artifacts
    import legacy_first_map_panel as panel
    from visit_frame_raw_0016 import digest, read, resident

    started = boot.now()
    folder = root/case
    if root.parent.resolve(strict=True) != Path("/dev/shm") or folder.exists():
        raise ValueError("Use a fresh private tmpfs publication root")
    prior = previous()
    machine = host()
    pins = sources(prior)
    if machine != prior["admission"]["machine"]:
        raise ValueError("The original low-priority environment changed")
    if case == TINY:
        pos = root/POSITIVE if positive_reference is None else positive_reference
        positive = read(pos/"result.json")
        if (read(pos/"prediction-seal.json") != output_seal(pos)
                or positive["positive_prediction_sha256"] != digest(pos/"prediction-seal.json")
                or positive["sources"] != pins or not allowed_tiny(positive, positive["process"])):
            raise ValueError("The original withholding is contingent on a faster qualified positive")
        enrolled = panel.tiny_input()
    else:
        enrolled = panel.positive_input(panel.reference(panel.POSITIVE, panel.POSITIVE_PIN))
    before = prior["admission"]["inputs"][case]
    if any(enrolled[key] != before[key] for key in ("request", "wavepaths")):
        raise ValueError("The original signed recording or causal offer changed")
    old = prior["checked"][case]["clock"]
    if resident(enrolled["wavepaths"]) != old["cache_before"]:
        raise ValueError("The complete enrolled private waveform and metadata must already be resident")
    argv = command_for(old["command"], folder/"candidate")
    native = {}
    from combined_frontier_run import BLOCK_SHA
    from full_short_run import EIGHT_MS_SHA, GEOGRAPHIC_SHA, TRACK_SCORES_SHA

    for flag, pin in zip(("--short-binary", "--geographic-library", "--regional-track-library",
                          "--frontier-block-library"), (short_pin or EIGHT_MS_SHA, GEOGRAPHIC_SHA, TRACK_SCORES_SHA, BLOCK_SHA), strict=True):
        path = Path(argv[argv.index(flag)+1])
        boot.checked(path, pin.removeprefix("sha256:"))
        native[flag] = dict(path=str(path), sha256=pin)
    flag = "--legacy-first-map-fast"
    artifacts = checked_artifacts(Path(argv[argv.index(flag)+1]), argv[argv.index(flag+"-sha256")+1])
    flag = "--legacy-first-map-history"
    path, pin = Path(argv[argv.index(flag)+1]), argv[argv.index(flag+"-sha256")+1]
    boot.checked(path, pin.removeprefix("sha256:"))
    native[flag] = dict(path=str(path), sha256=pin)
    if case == POSITIVE:
        root.mkdir(mode=0o700)
    folder.mkdir(mode=0o700)
    (folder/"tmp").mkdir()
    copytree(PRIOR/case/"fonts", folder/"fonts")
    write(folder/"admission.json", dict(case=case, case_source=enrolled, machine=machine, sources=pins,
          command=argv, native=native, artifacts=artifacts, prior_sha256=PRIOR_SHA, setup=boot.clock(started),
          callback="verified-original-once", prior_map_files_used=0, raw_conditioning_bytes=0, planned_children=1))
    return argv, environment_for(folder), enrolled


def launch(root, case, **options):
    import empty_bootstrap as boot
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from raw_0016_best_trial import measure_mode
    from visit_frame_raw_0016 import resident

    argv, env, enrolled = prepare(root, case, **options)
    folder = root/case
    started = boot.now()
    before = getrusage(RUSAGE_CHILDREN)
    probe = subprocess.run([*argv, "--first-map-setup-only"], env=env, check=False, capture_output=True,
                           text=True, timeout=15)
    after = getrusage(RUSAGE_CHILDREN)
    write(folder/"startup.json", dict(clock=boot.clock(started),
                                      child_cpu_s=(after.ru_utime-before.ru_utime)+(after.ru_stime-before.ru_stime),
                                      exit_code=probe.returncode,
                                      stdout=probe.stdout, stderr=probe.stderr))
    probe.check_returncode()
    scanner, solver = (json.loads(line) for line in probe.stdout.splitlines())
    if (not scanner["reached_scanner"] or scanner["waveform_opens"] or scanner["audit"]["authority_mode"] != "verified-once"
            or not solver["solver_setup"] or not solver["lookahead_setup"] or solver["waveform_opens"]
            or solver["witness_shape"] != [["decision"], ["ports", "timing"]] or (folder/"candidate").exists()):
        raise ValueError("Expected isolated original receiver and guarded solver startup without waveform access")
    measure_mode(folder, "candidate", argv, env, lambda: resident(enrolled["wavepaths"]), require_success=False)
    write(folder/"prediction-seal.json", output_seal(folder))


def score(root, case):
    from aperture_trial import write
    from clean_saved_0169_trial import output_seal
    from history_risk_residual_layout_0402 import media_identity
    from legacy_block_0107_score import snapshot as snapshot_tiny, speedup_gate
    from legacy_block_raw_score import snapshot as snapshot_positive
    from legacy_verify_original_trial import inspect_once
    from leo.contracts.digests import canonical_digest
    from publication_media_checks import verify_position_sidecars
    from visit_frame_raw_0016 import digest, read

    folder, prior = root/case, previous()
    book, log = (read(folder/name) for name in ("admission.json", "candidate-clock.json"))
    if (book["command"] != log["command"] or book["sources"] != sources(prior)
            or read(folder/"prediction-seal.json") != output_seal(folder)):
        raise ValueError("The sealed original-file outcome or frozen build changed")
    checked = prior["checked"][case]
    process = log["clock"]
    result = dict(case=case, process=process, verified_once=prior["clocks"][case]["once"],
                  installed=prior["clocks"][case]["installed"], admission=book, sources=book["sources"],
                  startup=read(folder/"startup.json"),
                  positive_prediction_sha256=digest(folder/"prediction-seal.json"))
    if process["exit_code"]:
        write(folder/"result.json", result | dict(qualified=False, decision="failed"))
        return
    target, req = folder/"candidate", book["case_source"]["request"]
    original = inspect_once(target, req, checked["original"])
    old = checked["science"]
    proof = read(target/"unified-short-bootstrap.json")
    witness = read(target/"exact-named-raw-witness.json")
    decision = proof["receipt"]["decision"]
    engine = original["acceleration"]["solver"]
    checks = dict(custody=original["acceleration"]["artifacts"] == checked["original"]["acceleration"]["artifacts"],
                  complete_members=all(row["complete_encoded_auth"] for row in original["members"]),
                  resident=all(log[key] == checked["clock"][key] for key in ("cache_before", "cache_after")),
                  no_backing=book["raw_conditioning_bytes"] == 0)
    current, sides, positions = {}, None, None
    if case == POSITIVE and decision == "complete":
        current = snapshot_positive(target, log, req, book["case_source"]["producer"])
        timing = prior["checked"][case]["clock"]
        old_root = Path(timing["command"][timing["command"].index("--output")+1])
        old_route = read(old_root/"exact-named-raw-witness.json")["ports"]["history_risk"]
        route = witness["ports"]["history_risk"]
        original_position, candidate_position = (
            {key: value for key, value in output["positions"].items() if key != "figures"} for output in (old, current))
        checks.update(
            genuine_decision=current["receipt"]["decision"] == old["receipt"]["decision"],
            genuine_native=all(current[key] == old[key] for key in ("native_sha256", "native_source", "ordered_owners")),
            geographic=route["boundary_checks"] == old_route["boundary_checks"] and
            [entry["exterior"] for entry in route["lean_attempts"]] ==
            [entry["exterior"] for entry in old_route["lean_attempts"]],
            exact_positions=canonical_digest(candidate_position) == canonical_digest(original_position),
            exact_science=all(current["published"][key] == old["published"][key]
                              for key in ("arms", "owners", "raw_authority", "scientific_digests")),
            exact_media=media_identity(current["images"]) == media_identity(old["images"]),
            normal_prefetch=all(current["prefetch"][key] == old["prefetch"][key]
                                for key in ("fallback", "hits", "hit_bytes", "submitted", "submitted_bytes")),
            actual_guard=len(engine["in_flight"]) == 1,
            actual_grid=engine["grid"].get("projection", {}).get("grids") == 1)
        if checks["exact_media"] and checks["exact_science"]:
            sides = verify_position_sidecars(old_root, target, current["receipt"]["run_id"], old["images"], current["images"])
        positions = current["published"]["arms"]
    elif case == TINY and decision == "withheld":
        current = snapshot_tiny(target, process, req)
        fields = ("factors", "graph_proof", "native_digest", "opportunities", "receiver_visits", "scan_digest",
                  "terminal", "witness")
        checks.update(genuine_withholding=all(current[key] == old[key] for key in fields),
                      no_solver=not engine and not witness["evidence"]["images"])
    else:
        checks["genuine_decision"] = False
    qualified = all(checks.values())
    result.update(qualified=qualified, decision=decision, parity=checks, science=current, positions=positions,
                  standard_sidecars=sides, acquisition=original, witness=witness, receiver=proof)
    result["positive_unlocks_tiny"] = case == POSITIVE and allowed_tiny(result, process)
    if case == TINY and qualified:
        pos = read(root/POSITIVE/"result.json")
        if not allowed_tiny(pos, pos["process"]):
            raise ValueError("The original withholding is contingent on its frozen positive gate")
        result["cohort_gates"] = {metric: speedup_gate(
            {item["case"]: item["installed"][metric] for item in (pos, result)},
            {item["case"]: item["process"][metric] for item in (pos, result)}) for metric in ("elapsed_s", "cpu_s")}
    write(folder/"result.json", result)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    cli.add_argument("case", choices=CASES)
    args = cli.parse_args()
    {"launch": launch, "score": score}[args.action](args.root, args.case)
