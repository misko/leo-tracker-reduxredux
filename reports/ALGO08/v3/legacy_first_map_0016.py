"""Run and qualify one original first-use map and position publication."""

import argparse
from collections import Counter
import json
from pathlib import Path
from resource import RUSAGE_CHILDREN, getrusage
import subprocess
import sys
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path[:0] = [str(HERE), str(ROOT)]

import legacy_block_raw_0016 as base
from legacy_block_all_0016 import CENSUS, CENSUS_PIN, PREVIOUS, qualified_control
from visit_frame_raw_0016 import checked, digest, read

ALL = Path("/dev/shm/leo-v3-legacy-all-0016-result02")
ALL_PIN = "9a13cc45e8933106a6be91c5ddfd575c87c311773499420131a094b44113b557"
CONTROL_PIN = "7e5f44b388a0674ab276282478122d218ef39adf9985acb31ef3e5a4d3b6afa0"
SOURCES = ("legacy_first_map_0016.py", "legacy_first_map_entry.py", "legacy_first_map_input.py",
           "legacy_fused_map.py", "legacy_fused_history.c", "legacy_block_multi.py",
           "legacy_block_all_entry.py", "legacy_map_receipt.py", "legacy-first-use-0016-protocol.md")
_base_pins = base.runtime_pins


def runtime_pins():
    return _base_pins() | {f"reports/ALGO08/v3/{name}": digest(HERE / name) for name in SOURCES}


def references():
    ordinary = qualified_control(CONTROL_PIN)
    indexed = checked(ALL / "result.json", ALL_PIN)
    if (not indexed["qualified"] or not all(indexed["checks"].values())
            or indexed["ordinary_control_sha256"] != CONTROL_PIN
            or indexed["input"]["totals"]["authenticated_encoded_bytes"] != 991_734_597
            or indexed["admission"]["request"] != ordinary["admission"]["request"]):
        raise ValueError("Use only the sealed original ordinary and prepared-map comparators")
    return ordinary, indexed


def launch(root):
    import empty_bootstrap as boot
    import legacy_block_raw_entry as raw_entry
    from legacy_first_map_entry import parser

    ordinary, indexed = references()
    argv = ordinary["admission"]["commands"]["ordinary"]

    def prepare(root, session, inventory_pin, inventory, expected, census):
        from leo.contracts.digests import canonical_json_bytes
        from reports.ALGO08.v3 import legacy_block_input as port, legacy_block_seek as replay
        from reports.ALGO08.v3 import legacy_fused_map as history

        began = boot.now()
        prior = indexed["admission"]
        plan = prior["plan"]
        port.all_parts(plan, session, inventory_pin, inventory)
        if (plan["raw_authority"] != expected or len(census) != 13 or
                Counter(row["map_kind"] for row in plan["members"]) != {"literal": 5, "exception": 8}):
            raise ValueError("Earlier prepared maps do not cover this signed original recording")
        expected_path = root / "expected-custody.json"
        expected_path.write_bytes(canonical_json_bytes(plan))
        plan_pin = digest(expected_path)
        if plan_pin != prior["map_custody_sha256"]:
            raise ValueError("Expected replay custody serialization changed")
        usage = getrusage(RUSAGE_CHILDREN)
        build = {name: tool.build(root / f"{name}.so") for name, tool in (("history", history), ("replay", replay))}
        after = getrusage(RUSAGE_CHILDREN)
        elapsed = boot.clock(began)
        elapsed["compiler_cpu_s"] = (after.ru_utime - usage.ru_utime) + (after.ru_stime - usage.ru_stime)
        return plan, plan_pin, dict(build=build, total=elapsed, ordinary_control_sha256=CONTROL_PIN,
                                    prepared_control_sha256=ALL_PIN, waveform_reads=0)

    def commands(_prior, root, _index, build, plan_pin):
        from eight_ms_south_transfer import environment_for

        if Path(argv[5]).name != "legacy_block_raw_entry.py" or any(flag.startswith("--legacy-map") for flag in argv):
            raise ValueError("The reused ordinary command contains an input adapter")
        command = list(argv)
        command[5] = str(HERE / "legacy_first_map_entry.py")
        command[command.index("--output") + 1] = str(root / "fused")
        for name, path, pin in (("plan", root / "expected-custody.json", plan_pin),
                                ("history", root / "history.so", build["history"]["binary_sha256"]),
                                ("replay", root / "replay.so", build["replay"]["binary_sha256"])):
            command.extend((f"--legacy-first-map-{name}", str(path), f"--legacy-first-map-{name}-sha256", pin))
        began = boot.now()
        probe = subprocess.run([*command, "--first-map-setup-only"], check=False, capture_output=True,
                               text=True, env=environment_for(root), timeout=15)
        (root / "setup-probe.json").write_text(json.dumps(dict(
            clock=boot.clock(began), exit=probe.returncode, stdout=probe.stdout, stderr=probe.stderr),
            indent=2) + "\n")
        if probe.returncode or not json.loads(probe.stdout)["reached_scanner"]:
            raise ValueError("The waveform-blocked startup probe declined the actual child")
        return {"fused": command}

    with (patch.object(base, "ORDER", ("fused",)), patch.object(base, "prepare", prepare),
          patch.object(base, "commands", commands), patch.object(base, "runtime_pins", runtime_pins),
          patch.object(base, "CENSUS", CENSUS), patch.object(base, "CENSUS_PIN", CENSUS_PIN),
          patch.object(raw_entry, "parser", parser)):
        base.launch(root)


def score(root):
    from aperture_trial import write
    from frame_portable_0016 import seal
    from history_risk_residual_layout_0402 import media_identity
    from legacy_block_raw_score import snapshot
    from leo.contracts.digests import canonical_digest
    from publication_media_checks import verify_position_sidecars

    ordinary_control, prior = references()
    ordinary = ordinary_control["products"]["ordinary"]
    book, log = read(root / "admission.json"), read(root / "fused-clock.json")
    current = snapshot(root / "fused", log, book["request"], book["producer"])
    checks = dict(
        sources=book["sources"] == runtime_pins(), seal=read(root / "prediction-seal.json") == seal(root),
        same_scope=book["request"] == prior["admission"]["request"] and book["producer"] == prior["admission"]["producer"],
        actual_command=log["command"] == book["commands"]["fused"],
        positions=canonical_digest(current["positions"]) == canonical_digest(ordinary["positions"]),
        all_pngs=media_identity(current["images"]) == media_identity(ordinary["images"]),
    )
    checks.update({key: current["receipt"][key] == ordinary["receipt"][key] for key in (
        "decision", "session_id", "run_id", "terminal_sha256", "region", "window_count", "counts")})
    checks.update({key: current[key] == ordinary[key] for key in (
        "native_sha256", "native_source", "ordered_owners", "history_risk")})
    checks.update({key: current["published"][key] == ordinary["published"][key] for key in (
        "raw_authority", "arms", "owners", "scientific_digests")})
    products = verify_position_sidecars(PREVIOUS / "ordinary", root / "fused", current["receipt"]["run_id"],
                                        ordinary["images"], current["images"])
    plan = book["plan"]
    folder = root / "fused/legacy-first-maps"
    audit = read(root / "fused/legacy-first-map-acquisition.json")
    checks.update(
        exact_replay_custody=digest(folder / "custody.json") == book["map_custody_sha256"] == audit["plan_sha256"]
        == prior["admission"]["map_custody_sha256"],
        raw_first_acquisition=audit["finished_raw_authority"] == plan["raw_authority"],
        binaries=all(audit[name + "_sha256"] == book["preparation"]["build"][name]["binary_sha256"]
                     for name in ("history", "replay")),
    )
    for row, declared in zip(audit["members"], plan["members"], strict=True):
        path = folder / declared["map"]
        if (any(row[key] != value for key, value in declared.items()) or
                row["proof"]["original_encoded_reused"] != declared["encoded"] or
                row["proof"]["prefix_bytes"] != 640_000 or
                digest(path) != declared["map_sha256"] or row["map_bytes"] != path.stat().st_size):
            raise ValueError("One generated map failed reopened or durable payload proof")
    checks["all_maps"] = len(audit["members"]) == 13 and sum(
        m["encoded"] for m in audit["members"]) == 991_734_597
    if not all(checks.values()):
        raise ValueError(f"First-use proof changed exact scientific or custody results: {checks}")
    write(root / "result.json", dict(case="DS30-0016", qualified=True, checks=checks,
        original_verification_maps=audit, candidate=current, ordinary=ordinary,
        prepared=prior["products"]["indexed"], prepared_costs=prior["prices"], sidecars=products,
        admission=book, clock=log, prediction_seal=digest(root / "prediction-seal.json")))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("action", choices=("launch", "score"))
    cli.add_argument("root", type=Path)
    args = cli.parse_args()
    {"launch": launch, "score": score}[args.action](args.root)
