"""Restore installed winners on exactly the matching empty short lanes."""

from collections import Counter, defaultdict

from matched_donor_0049 import bind_derived
from signed_cfo_time_readout import bind_pair, canonical, opportunities


def restore_empty_lanes(stock, sparse):
    left, right = map(opportunities, (stock, sparse))
    bind_pair(stock, sparse, left, right)
    probes, inserted = [], []
    coverage = defaultdict(Counter)
    for oid, lane in right.items():
        row, original = lane["row"], lane["factor"]
        aperture = "short" if lane["short"] else "anchor"
        count = coverage[f"rx{lane['radio']}/{aperture}"]
        count["opportunities"] += 1
        count["original_winners"] += int(original is not None)
        empty = not row["candidates"]
        if len(row["candidates"]) != int(original is not None):
            raise ValueError("The original unfiltered sparse lane must hold a single selected winner or be empty")
        count["original_empty"] += int(empty)
        donor = left[oid]["factor"]
        if lane["short"] and empty and donor is not None:
            count["inserted"] += 1
            inserted.append(dict(observation_id=oid, receiver=lane["radio"], counter=lane["counter"],
                                 visit=row["visit_index"], rf_hz=row["actual_rf_hz"], installed_tuple=donor))
            row = dict(row, candidates=[donor])
        probes.append(row)
    if not inserted:
        raise ValueError("No installed winner on a candidate-empty short opportunity")
    recipe = dict(schema="private-0049-empty-lane-restoration-v1", scope="saved research counterfactual",
                  installed_native_sha256=canonical(stock), sparse_native_sha256=canonical(sparse),
                  selected="maximum passed installed fractional margin, native rank tiebreak",
                  eligibility="literally empty candidate row on the same signed nonanchor opportunity",
                  anchors="unchanged", unchanged_opportunities=True, insertion_sha256=canonical(inserted))
    packet, custody = bind_derived(sparse, probes, recipe)
    return packet, dict(custody, coverage=coverage, inserted=inserted, inserted_count=len(inserted),
                        original_winners=sum(c["original_winners"] for c in coverage.values()),
                        unchanged_lanes=len(right)-len(inserted), replaced=0, dropped=0)
