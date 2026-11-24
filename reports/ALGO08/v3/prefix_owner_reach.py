"""Measure how far final assignment changes extend beyond a measured receiver intervention."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path


INPUTS = {
    "before": "c1f7486fb931e782049f6191d6751354cbb908cc739a05248c058e5ef2e9ac3a",
    "after": "f70566671491da7eb1b5b572e60ffd5eb5ab65c398757de9e1e40137d2784c95",
    "detector": "161d3ff4a85777f81217a929fdf0c999eb09f48575322ab46dcdcd773a95e23a",
}


def index_opportunities(source):
    visits = {}
    for row in source["probes"]:
        identity = f"{source['session_id']}:{row['receiver_id']}:{row['valid_start_counter']}"
        key = "sha256:" + sha256(identity.encode()).hexdigest()
        if key in visits:
            raise ValueError("Duplicate observation identity")
        visits[key] = row["visit_index"]
    return visits


def changes_by_visit(before, after, visits):
    def assignments(rows):
        result = {key: (satellite, role) for key, satellite, role in rows}
        if len(result) != len(rows) or result.keys() - visits.keys():
            raise ValueError("Ambiguous or unbound assignment")
        return result

    original, updated = assignments(before), assignments(after)
    changes = []
    for key in sorted(original.keys() | updated.keys()):
        old, new = original.get(key), updated.get(key)
        if old == new:
            continue
        kind = "added" if old is None else "removed" if new is None else "reassigned"
        changes.append((visits[key], kind, old, new))
    return changes


def summarize(changes, prefix, total, member=64):
    if not 0 < prefix < total or member <= 0 or any(not 0 <= row[0] < total for row in changes):
        raise ValueError("Invalid intervention or visit bounds")
    tails = []
    for extended in (0, 1, 2, 4, 8, 16, 32, 64):
        stop = min(total, prefix + member * extended)
        residual = Counter(row[1] for row in changes if row[0] >= stop)
        tails.append(dict(freeze_from_visit=stop, unreachable_changes=sum(residual.values()), kinds=dict(residual)))
    suffix = [row for row in changes if row[0] >= prefix]
    swaps = Counter((old[0], new[0]) for _, kind, old, new in suffix if kind == "reassigned")
    return dict(changes=len(changes), inside_prefix=len(changes)-len(suffix), outside_prefix=len(suffix),
                last_changed_visit=max((row[0] for row in changes), default=None),
                touched_suffix_members=len({row[0] // member for row in suffix}),
                satellite_transitions=[dict(old=old, new=new, count=count)
                                       for (old, new), count in swaps.most_common()], tails=tails)


def run(paths):
    docs = {}
    for key, path in paths.items():
        data = path.read_bytes()
        if sha256(data).hexdigest() != INPUTS[key]:
            raise ValueError(f"Incorrect signed source for {key}")
        docs[key] = json.loads(data)
    a, b = docs["before"], docs["after"]
    source = docs["detector"]["source"]
    for receipt in (a["receipt"], b["receipt"]):
        if receipt["session_id"] != source["session_id"] or receipt["window_count"] != 6772:
            raise ValueError("The solver and opportunities have different identities")
    visits = index_opportunities(source)
    result = {}
    for arm in ("c0", "fitted_c"):
        result[arm] = summarize(changes_by_visit(a["selected_rows"][arm], b["selected_rows"][arm], visits),
                                prefix=192, total=6772)
    clocks = {}
    for mode, receipt in (("before", a), ("after", b)):
        route = receipt["route_details"]
        clocks[mode] = dict(cold_cpu_s=route["cold_clocks"]["cpu_s"],
                            cold_winner_rank=route["cold"]["branch"], first_pair_accepted=route["pair_passes"],
                            repair_cpu_s=sum(route.get(key, {}).get("cpu_s", 0.0)
                                             for key in ("repair_prepare_clocks", "repair_fit_clocks")),
                            pre_evidence_cpu_s=route["candidate_pre_evidence_clocks"]["cpu_s"],
                            signed_cpu_s=route["signed_total_clocks"]["cpu_s"],
                            evidence_cpu_s=route["standard_evidence_clocks"]["cpu_s"])
    return dict(case="DS30-0008", input_sha256=INPUTS, arms=result, clocks=clocks)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for key in INPUTS:
        parser.add_argument(key, type=Path)
    print(json.dumps(run(vars(parser.parse_args())), indent=2, allow_nan=False))
