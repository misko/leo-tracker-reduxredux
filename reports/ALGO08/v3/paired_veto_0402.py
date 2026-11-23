"""Combine exact inner gates with a first-arm terminal veto in the named publication."""

import argparse
import os
import sys
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

import stock_exact_gate_0402 as exact
from constrained_pair_veto import ARMS, guard, incompatible_tracks


FIRST_ARM_ENV = "LEO_RESEARCH_CONSTRAINED_FIRST_ARM"
EXACT_ONLY = Path("/dev/shm/leo-v3-0402-exact-gate-scored01.json")
C0_FIRST = Path("/dev/shm/leo-v3-0402-combined-pair-veto-scored01.json")
EXACT_SHA = "04b3fcae4f7404aac51b6b1902bc599a7cc561b31f89b772a38afd5f514d93dd"
C0_SHA = "b0ec53ec483bdcfca8f316a5231b64fd405eab288596ec1deff917bc92c8f2e4"


def trial_result(row):
    if len(row["arms"]) != 1:
        return exact.trial_record(row)
    (arm, first), = row["arms"].items()
    failed = incompatible_tracks(first)
    if arm not in ARMS or not failed or row["paired_valid"] or not row["constrained_refinement_attempted"]:
        raise ValueError("Only a proved failure can omit the second constrained arm")
    return {
        "paired_valid": False,
        "constrained": True,
        "replacements": row["replacements"],
        "arms": {
            arm: {
                "failed_tracks": len(failed),
                "refits": len(first["history"]),
                "rf_rms_hz": first["RMS_hz"],
                "phase_change_s": first["final_phase_change_s"],
            }
        },
    }


def worker(output, *, first_arm="c0"):
    audit = {}

    @contextmanager
    def combined(feasible, cavity, likelihood, counts):
        with (
            exact.gate_binding(feasible, cavity, likelihood, counts),
            guard(cavity, feasible, audit, first_arm=first_arm),
        ):
            yield

    exact.worker(output, binding=combined, summarize_trial=trial_result)
    from aperture_trial import write

    sources = (
        "constrained_pair_veto.py",
        "paired_veto_0402.py",
        "constrained-pair-veto-protocol.md",
        "constrained-pair-arm-order-protocol.md",
    )
    write(
        output / "terminal-veto.json",
        {
            "audit": audit,
            "sources": {
                name: sha256((HERE / name).read_bytes()).hexdigest() for name in sources
            },
        },
    )


def check_trials(current, reference, first_arm="c0"):
    if {k: v for k, v in current.items() if k != "trials"} != {
        k: v for k, v in reference.items() if k != "trials"
    }:
        raise ValueError("The family selection changed")
    partial = 0
    for row, old in zip(current["trials"], reference["trials"], strict=True):
        if row == old:
            continue
        if (
            set(row["arms"]) != {first_arm}
            or row["paired_valid"]
            or old["paired_valid"]
            or not row["constrained"]
            or not old["constrained"]
            or row["replacements"] != old["replacements"]
        ):
            raise ValueError("Invalid or changed trial at the pair veto")
        matched = {k: v for k, v in old["arms"][first_arm].items() if k != "loss"}
        if row["arms"][first_arm] != matched or not matched["failed_tracks"]:
            raise ValueError("The completed first arm disagrees with the named trial")
        partial += 1
    return partial


def evaluate(root, destination):
    from aperture_trial import read, write

    saved = exact.pinned(exact.BASELINE, exact.PINS["scored"])
    old = saved["runs"]["stock"]
    output = root / "exact"
    clock = read(root / "exit.json")["timing"]
    measured = read(output / exact.SETTINGS["audit_name"])
    actual = exact.inspect(
        output, "veto", measured["receipt"], clock, exact.inputs(), **exact.SETTINGS
    )
    exact.compare(actual, old)
    reference = exact.pinned(exact.PROFILE, exact.PROFILE_SHA)
    trace = read(output / "exact-gates.json")
    veto = read(output / "terminal-veto.json")
    counts = trace["counts"]
    prepared = exact.pinned(EXACT_ONLY, EXACT_SHA)
    zero = exact.pinned(C0_FIRST, C0_SHA)
    original_visits = prepared["gates"]["counts"]["visits"]
    zero_visits = zero["exact_gate"]["counts"]["visits"]
    visits = {"c0": zero_visits, "fitted_c": original_visits - zero_visits}
    audit = veto["audit"]
    first_arm = audit["first_arm"]
    partial = check_trials(trace["cavity"], reference["cavity"], first_arm)
    other_arm, = (arm for arm in ARMS if arm != first_arm)
    if (
        clock["exit_code"]
        or partial != 1
        or len(audit["rejected_trials"]) != partial
        or audit["rejected_trials"][0]["skipped_arm"] != other_arm
        or audit["second_arms_started"]
        or counts["phase_fits"] != 5
        or counts["visits"] != visits[first_arm]
        or audit["arms"] != {
            first_arm: dict(phase_fits_started=5, recorded_visits=visits[first_arm]),
            other_arm: dict(phase_fits_started=0, recorded_visits=0),
        }
        or any(counts.get(name, 0) for name in ("screen_stock", "profile_stock", "white_stock"))
    ):
        raise ValueError("The expected single final-arm rejection did not execute")
    write(
        destination,
        {
            "stock_exit": old["process"],
            "combined_exit": clock,
            "stock_solve": old["worker"]["solve"],
            "combined_solve": actual["worker"]["solve"],
            "gate_only_exit": prepared["exact_exit"],
            "gate_only_solve": prepared["exact_solve"],
            "archived_c0_first_exit": zero["combined_exit"],
            "archived_c0_first_solve": zero["combined_solve"],
            "reconstructed_stock_visits_by_arm": visits,
            "exact_gate": trace,
            "terminal_veto": veto,
            "terminal": actual["terminal"],
            "owners": actual["science"]["owners"],
            "scores": saved["scores"]["stock"],
            "owner_counts": {
                k: len(rows) for k, rows in actual["selected_rows"].items()
            },
            "sidecars": actual["sidecars"],
            "figures": actual["figures"],
            "paired_science_equal": True,
            "source_stock_sha256": exact.PINS["scored"],
            "source_gate_only_sha256": EXACT_SHA,
            "source_c0_first_sha256": C0_SHA,
            "waveform_calls": 0,
        },
    )


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    sub = cli.add_subparsers(dest="command", required=True)
    for name in ("worker", "launch", "evaluate"):
        command = sub.add_parser(name)
        command.add_argument("root", type=Path)
        if name == "evaluate":
            command.add_argument("destination", type=Path)
        elif name == "launch":
            command.add_argument("--first-arm", choices=ARMS, default="c0")
    options = cli.parse_args()
    if options.command == "launch":
        with patch.dict(os.environ, {FIRST_ARM_ENV: options.first_arm}):
            exact.launch(options.root, driver=__file__)
    elif options.command == "worker":
        worker(options.root, first_arm=os.environ.get(FIRST_ARM_ENV, "c0"))
    else:
        evaluate(options.root, options.destination)
