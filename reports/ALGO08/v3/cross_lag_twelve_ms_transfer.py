"""Verify the live guarded cross-lag recipe on the independent 0169 member."""

import argparse
from contextlib import nullcontext
import json
import os
from pathlib import Path
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from cross_lag_guarded import DSO_SHA, RULE, activate


ORDERS = (("ordinary", "routed"), ("routed", "ordinary"))
PACK = Path("/dev/shm/leo-anchored-cfo-raw-pack01")


def worker(output, binary, arm):
    import anchored_cfo_stage as stage
    import continued_cfo as continued

    normal_bind = stage.installed.bind_native
    original_select = continued.select_refined

    def launch(argv):
        staged_seal = stage.installed.bind_native

        def selected(native, preparation, changes, session, inventory, receipt_path):
            import full_short_run

            packet, recipe, detector, route = original_select(native, preparation, changes, session, inventory, receipt_path)
            acquired = native["source"]["probes"]
            stage.write(output / "measurements.json", dict(original=changes.original_rows(acquired), acquired=acquired,
                                                            route=route["choice"], paid=changes.paid))
            with patch.object(full_short_run, "checked_recipe", return_value=recipe):
                staged_seal(packet, session, inventory, detector)
            raise ValueError("Expected the stage to stop before a position solve")

        with (patch.object(continued, "select_refined", selected),
              patch.object(stage.installed, "bind_native", normal_bind),
              activate(binary) if arm == "routed" else nullcontext()):
            continued.raw_entry(None, argv, guarded_pack=PACK)

    stage.worker("anchored", PACK, output, launch=launch)


def compare(a, b):
    original, routed = (row["scope"] for row in (a, b))
    x, y = (row["native"] for row in (a, b))
    if (original["prefix_inventory"] != routed["prefix_inventory"] or original["iq"] != routed["iq"]
            or x["clock_anchor"] != y["clock_anchor"] or x["delivery_clocks"] != y["delivery_clocks"]
            or x["provenance"]["excluded_windows"] != y["provenance"]["excluded_windows"]
            or x["source"]["raw_recording_authority_digest"] != y["source"]["raw_recording_authority_digest"]):
        raise ValueError("The independent pair does not share the original signed member and admissions")
    calls = [row["receiver_audit"]["native"]["native_calls"] for row in (original, routed)]
    if calls != [{"full": 16, "short_primary": 86}] * 2:
        raise ValueError("The entire original stereo anchor/short schedule must execute")
    full = [row for row in range(len(original["vectors"])) if original["vectors"][row]["mode"] == "full"]
    anchors = original["vectors"]
    peer = routed["vectors"]
    if len(full) != 16 or any(anchors[i] != peer[i] for i in full):
        raise ValueError("The full two-scan or cancellation vector changed on an anchor")
    comparisons = dict(raw=anchors == peer, original=a["measurements"]["original"] == b["measurements"]["original"],
                       acquired=a["measurements"]["acquired"] == b["measurements"]["acquired"],
                       paid=a["measurements"]["paid"] == b["measurements"]["paid"],
                       choice=a["measurements"]["route"] == b["measurements"]["route"],
                       selected=x["source"]["probes"] == y["source"]["probes"])
    scope = [row["receiver_audit"]["acquire"]["cpu_ns"] for row in (original, routed)]
    return dict(anchors=len(full), byte_parity=comparisons, original_acquisition_cpu_ns=scope[0],
                routed_acquisition_cpu_ns=scope[1], both_conditions=all(comparisons.values()) and scope[1] < scope[0])


def run(root, binary):
    import anchored_cfo_stage as stage
    from continued_cfo_live_trial import resident
    from short_raw_diagnostic import measure

    if root.parent.resolve() != Path("/dev/shm") or os.sched_getaffinity(0) != {2}:
        raise ValueError("Use the original tmpfs and shared Gauss CPU2 lock")
    root.mkdir()
    pairs = []
    for repeat, order in enumerate(ORDERS):
        runs = {}
        for arm in order:
            path = root / f"{repeat}-{arm}"
            before = resident(stage)
            clock = measure([sys.executable, "-B", str(Path(__file__)), str(path), str(binary), "--worker", arm],
                            dict(os.environ), path)
            if clock["exit_code"]:
                raise RuntimeError(clock["stderr_tail"])
            runs[arm] = dict(clock=clock, before=before, after=resident(stage),
                             **{key: json.loads((path / f"{name}.json").read_bytes()) for key, name in (
                                 ("scope", "scope-receipt"), ("native", "detections"), ("measurements", "measurements"))})
        verified = compare(*(runs[name] for name in ORDERS[0]))
        pairs.append(dict(order=order, runs=runs, verified=verified))
    if any(pairs[0]["runs"][arm]["native"] != pairs[1]["runs"][arm]["native"] for arm in ORDERS[0]):
        raise ValueError("Opposite benchmark order changed the actual selected guarded packet")
    stage.write(root / "result.json", dict(threshold=RULE, binary_sha256=DSO_SHA, pairs=pairs,
                                          north_eligible=all(pair["verified"]["both_conditions"] for pair in pairs)))


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("root", type=Path)
    cli.add_argument("binary", type=Path)
    cli.add_argument("--worker", choices=ORDERS[0])
    args = cli.parse_args()
    if args.worker:
        worker(args.root, args.binary, args.worker)
    else:
        run(args.root, args.binary)
