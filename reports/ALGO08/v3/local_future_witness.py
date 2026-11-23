"""Retrospective full-aperture witnesses for the forward and repaired ownership sets."""

from collections import Counter
import json
from pathlib import Path
from statistics import median
import sys

from local_future_0057 import inputs
from short_primary_epoch_audit import good_match, paired_probes


def census(identities, stock_owners, paired):
    ids = set(identities)
    comparable, full_winners, same_owner, other_owner = [], 0, 0, 0
    for oid in ids:
        short, full = paired[oid]
        if short is None:
            raise ValueError("An assigned observation lacks a signed short factor")
        if full is not None:
            full_winners += 1
            if good_match(full, short):
                comparable.append(abs(full["fractional_tracking_cfo_hz"] - short["fractional_tracking_cfo_hz"]))
        if oid in stock_owners:
            if stock_owners[oid] == identities[oid][0]:
                same_owner += 1
            else:
                other_owner += 1
    return dict(count=len(ids), full_selected=full_winners, rank_zero_time_cfo_match=len(comparable),
                median_abs_cfo_difference_among_matches_hz=median(comparable) if comparable else None,
                stock_same_satellite=same_owner, stock_other_satellite=other_owner,
                stock_unassigned=len(ids)-same_owner-other_owner,
                by_role=dict(Counter(role for _, role in identities.values())),
                by_satellite=dict(Counter(sat for sat, _ in identities.values())))


def analyze(root):
    from aperture_trial import read
    from leo.contracts.digests import canonical_digest

    packets = []
    for arm in ("stock", "repair"):
        _, pin, path, _, _ = inputs(arm)
        packet = read(path)
        if canonical_digest(packet) != pin:
            raise ValueError("Changed raw detector source")
        packets.append(packet)
    paired = {oid: (candidate, full) for oid, _, full, candidate, _ in paired_probes(*packets)}
    rows = {arm: read(root / arm / "joint-research-receipt.json")["selected_rows"] for arm in ("stock", "forward", "repair")}
    result = {}
    for mode in ("c0", "fitted_c"):
        def owners(arm):
            return {oid: (sat, role) for oid, sat, role in rows[arm][mode]}

        forward, repair = owners("forward"), owners("repair")
        if not forward.items() <= repair.items():
            raise ValueError("The transfer lost forward owners")
        added = {oid: repair[oid] for oid in repair.keys()-forward.keys()}
        incumbent = {oid: sat for oid, (sat, _) in owners("stock").items()}
        result[mode] = {key: census(items, incumbent, paired) for key, items in (("forward", forward), ("added", added))}
    return result


if __name__ == "__main__":
    print(json.dumps(analyze(Path(sys.argv[1])), indent=2, sort_keys=True))
