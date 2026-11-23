"""Price attachment coverage using sealed forward and two-sided owner maps, for scoring only."""

import argparse
from collections import Counter, defaultdict
from pathlib import Path

from aperture_trial import read, write
from bidirectional_selection import assignment_changes
from dense_geographic_trial import host
from local_future_inputs import MAX_GAP_S, future_observations, lane
from north_factor_swap import continued
from short_stereo_trial import CASES, HERE, load_source, single_packet


FUTURE = Path("/var/tmp/leo-bidirectional-transfer-nov23")
FORWARD = Path("/var/tmp/leo-causal-weak-south-nov23")
NORTH_FORWARD = Path("/var/tmp/leo-north-short-causal-raw-nov23/containing")


def overlap(forward_rows, restored_rows, native, future):
    before = {oid: (sat, role) for oid, sat, role in forward_rows}
    after = {oid: (sat, role) for oid, sat, role in restored_rows}
    groups = defaultdict(list)
    for oid, owner in before.items():
        groups[owner].append(native[oid])
    missing, counts = [], Counter()
    for oid in sorted(after.keys() - before.keys()):
        new = native[oid]
        owner = after[oid]
        peers = [abs(row["time_s"]-new["time_s"]) for row in groups[owner] if lane(row) == lane(new)]
        nearest = min(peers, default=None)
        supported_by_time = oid in future
        row = dict(observation_id=oid, norad=owner[0], role=owner[1], time_s=new["time_s"], lane=lane(new),
                   future_only=supported_by_time, same_satellite_role=bool(groups[owner]), nearest_same_lane_s=nearest)
        missing.append(row)
        counts["gained_future_only"] += supported_by_time
        counts["gained_already_forward_selected"] += not supported_by_time
        counts["future_existing_satellite_role"] += supported_by_time and bool(groups[owner])
        counts["future_existing_same_lane_within_8s"] += supported_by_time and nearest is not None and nearest <= MAX_GAP_S
    return dict(counts=dict(counts), ownership=assignment_changes(forward_rows, restored_rows), additions=missing)


def run():
    from leo.analysis.localization_v3.tracks import winning_observations
    from leo.contracts.digests import canonical_digest

    machine = host()
    earlier = read(HERE / "measurements/bidirectional-selection.json")
    causal, north = (read(HERE / f"measurements/{name}.json") for name in ("causal-selection-transfer", "north-causal-transfer"))
    results = {}
    for case in CASES:
        _, _, _, pin, offer, source = load_source(case)
        forward = continued(source)
        directory = NORTH_FORWARD if case == "north" else FORWARD / case
        before = read(directory / "joint-research-receipt.json")
        after = read(FUTURE / case / "joint-research-receipt.json")
        sealed = north["cases"]["containing"]["images"] if case == "north" else causal[case]["images"]
        restored = earlier[case]
        readback = read(single_packet(directory))
        terminal = read(directory / "fast-scan-automatic-work" / before["receipt"]["run_id"] / "terminal.json")
        if (before["evidence"]["images"] != sealed or readback["source"]["probes"] != forward["source"]["probes"]
                or terminal["native_sha256"] != canonical_digest(readback)
                or before["receipt"]["terminal_sha256"] != canonical_digest(terminal)
                or after["receipt"]["terminal_sha256"] != restored["terminal"]
                or before["receipt"]["region"] != after["receipt"]["region"] or after["receipt"]["region"] != offer):
            raise ValueError("The sealed owner maps differ from their published forward/two-sided evidence")
        rows, _ = winning_observations(source)
        native = {row["observation_id"]: row for row in rows}
        future = {row["observation_id"] for row in future_observations(source, forward)}
        changes = {arm: overlap(before["selected_rows"][arm], after["selected_rows"][arm], native, future)
                   for arm in before["selected_rows"]}
        if any(data["ownership"] != restored["changes_from_forward"][arm] for arm, data in changes.items()):
            raise ValueError("Archived owner changes failed readback")
        results[case] = dict(source=pin, forward=before["receipt"]["terminal_sha256"], restored=restored["terminal"],
                             future_opportunities=len(future), changes=changes)
    return dict(machine=machine, results=results)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    write(parser.parse_args().output, run())
