"""Confirm both released-ABI routes on a fixed tiny prefix before full clocks."""

import argparse
import json
from contextlib import ExitStack, closing
from itertools import islice
from pathlib import Path

from .. import whole_iq
from . import arrival_queue as pace
from . import capture_release, paced_hit, recording_to_v5
from .full_v5_check import _sha

LIMIT = 32


def run(folder):
    from leo.contracts.fast_scan_native import FastScanPolicyV2
    from leo.scanner.fast_scan_analysis import analyze_window

    plan_file = folder / "detector-lock.json"
    frozen = whole_iq.read(plan_file)
    if frozen["id"] != paced_hit.CASE:
        raise ValueError("preflight bound a different frozen recording")
    spec = frozen["cases"][paced_hit.CASE]
    policy = FastScanPolicyV2()
    capture = spec["capture"]
    recording_to_v5._bind_producer(
        capture["case"], capture_release.producer(capture["case"], capture), policy
    )
    archive = pace.packets
    compressed = []
    with closing(archive(capture, compressed)) as stream:
        frames = list(islice(stream, LIMIT))
    if len(frames) != LIMIT:
        raise ValueError("preflight could not recover the complete declared short prefix")
    evidence = {}
    for role in paced_hit.ORDER:
        branch = spec["modes"][role]
        rows = pace.readgz(whole_iq.checked(folder / branch["events"], branch["sha256"]))
        with paced_hit.configuration(dict(case=spec), rows), ExitStack() as stack:
            detect = pace.build_native(capture, role, frozen["assets"], stack)
            authenticated = []
            for event, frame in zip(rows[:LIMIT], frames, strict=True):
                packet, _ = pace.native_visit(frame, analyze_window, detect, policy)
                stamp = pace.fingerprint(packet)
                if stamp != event["full_visit_sha256"]:
                    raise ValueError(f"{role} failed independent packet parity at {event['visit']}")
                authenticated.append(
                    dict(
                        visit=event["visit"],
                        expected=stamp,
                        primary_receiver=event["primary_receiver"],
                        primary_hit=event["primary_hit"],
                        measured_lanes=event["measured_lanes"],
                        status=event["status"],
                    )
                )
        evidence[role] = authenticated
    valid = [r for r in evidence[paced_hit.HIT] if r["status"] == "processed"]
    if {r["primary_hit"] for r in valid} != {False, True} or {
        r["primary_receiver"] for r in valid
    } != {0, 1}:
        raise ValueError("fixed short prefix did not exercise both primary lanes and gate branches")
    return dict(
        case=paced_hit.CASE,
        physical_visits=LIMIT,
        valid_visits=len(valid),
        detector_lock_sha256=_sha(plan_file),
        prefix_rows=evidence,
        claim="Actual short raw parity. Complete arrival timing is outside this preflight.",
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    print(json.dumps(run(parser.parse_args().folder), sort_keys=True, indent=2))
