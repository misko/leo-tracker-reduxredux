"""Combine exact inner gates with a first-arm terminal veto in the named publication."""

import argparse
import sys
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path

HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

import stock_exact_gate_0402 as exact
from constrained_pair_veto import guard, incompatible_tracks


def trial_result(row):
    if set(row["arms"]) != {"c0"}:
        return exact.trial_record(row)
    first = row["arms"]["c0"]
    failed = incompatible_tracks(first)
    if not failed or row["paired_valid"] or not row["constrained_refinement_attempted"]:
        raise ValueError("Only a proved failure can omit the second constrained arm")
    return {
        "paired_valid": False,
        "constrained": True,
        "replacements": row["replacements"],
        "arms": {
            "c0": {
                "failed_tracks": len(failed),
                "refits": len(first["history"]),
                "rf_rms_hz": first["RMS_hz"],
                "phase_change_s": first["final_phase_change_s"],
            }
        },
    }


def worker(output):
    audit = {}

    @contextmanager
    def combined(feasible, cavity, likelihood, counts):
        with (
            exact.gate_binding(feasible, cavity, likelihood, counts),
            guard(cavity, feasible, audit),
        ):
            yield

    exact.worker(output, binding=combined, summarize_trial=trial_result)
    from aperture_trial import write

    sources = (
        "constrained_pair_veto.py",
        "paired_veto_0402.py",
        "constrained-pair-veto-protocol.md",
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


def check_trials(current, reference):
    if {k: v for k, v in current.items() if k != "trials"} != {
        k: v for k, v in reference.items() if k != "trials"
    }:
        raise ValueError("The family selection changed")
    partial = 0
    for row, old in zip(current["trials"], reference["trials"], strict=True):
        if row == old:
            continue
        if (
            set(row["arms"]) != {"c0"}
            or row["paired_valid"]
            or old["paired_valid"]
            or not row["constrained"]
            or not old["constrained"]
            or row["replacements"] != old["replacements"]
        ):
            raise ValueError("Invalid or changed trial at the pair veto")
        matched = {k: v for k, v in old["arms"]["c0"].items() if k != "loss"}
        if row["arms"]["c0"] != matched or not matched["failed_tracks"]:
            raise ValueError("The completed c0 result disagrees with the named trial")
        partial += 1
    return partial


def evaluate(root, destination):
    import empty_bootstrap as boot

    boot.load_runtime()
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
    partial = check_trials(trace["cavity"], reference["cavity"])
    if (
        clock["exit_code"]
        or partial != 1
        or len(veto["audit"]["rejected_trials"]) != partial
        or veto["audit"]["second_arms_started"]
        or counts["phase_fits"] != 5
        or not counts["visits"]
    ):
        raise ValueError("The expected single final-arm rejection did not execute")
    write(
        destination,
        {
            "stock_exit": old["process"],
            "combined_exit": clock,
            "stock_solve": old["worker"]["solve"],
            "combined_solve": actual["worker"]["solve"],
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
    options = cli.parse_args()
    if options.command == "launch":
        exact.launch(options.root, driver=__file__)
    elif options.command == "worker":
        worker(options.root)
    else:
        evaluate(options.root, options.destination)
