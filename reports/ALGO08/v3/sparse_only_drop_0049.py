"""Select sparse-only 8 ms lane exclusions with an installed row as the oracle."""

from collections import Counter, defaultdict

from matched_donor_0049 import bind_derived
from signed_cfo_time_readout import bind_pair, canonical, opportunities


def exclude_sparse_only(stock, sparse):
    left, right = map(opportunities, (stock, sparse))
    bind_pair(stock, sparse, left, right)
    probes, removed = [], []
    coverage = defaultdict(Counter)
    for oid, item in right.items():
        row, original = item["row"], item["factor"]
        aperture = "short" if item["short"] else "anchor"
        count = coverage[f"rx{item['radio']}/{aperture}"]
        count["opportunities"] += 1
        count["original_winners"] += int(original is not None)
        if len(row["candidates"]) != int(original is not None):
            raise ValueError("The unfiltered sparse packet must hold one selected native factor or be empty")
        drop = item["short"] and original is not None and not left[oid]["row"]["candidates"]
        if drop:
            removed.append(dict(observation_id=oid, receiver=item["radio"], counter=item["counter"],
                                visit=row["visit_index"], rf_hz=row["actual_rf_hz"], original=original))
            row = dict(row, candidates=[])
        count["removed"] += int(drop)
        probes.append(row)
    if not removed:
        raise ValueError("No short winner paired with a literally empty installed lane")
    recipe = dict(schema="private-0049-sparse-only-exclusion-v1",
                  installed_native_sha256=canonical(stock), sparse_native_sha256=canonical(sparse),
                  full_anchor_rows="unchanged", source="installed empty native row on original signed opportunity",
                  unchanged_opportunities=True, exclusion_sha256=canonical(removed))
    packet, custody = bind_derived(sparse, probes, recipe)
    return packet, dict(custody, coverage=coverage, removed=removed, removed_count=len(removed),
                        replaced=0, keeper_identity="original sparse tuple")
