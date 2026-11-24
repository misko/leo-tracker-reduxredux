"""Join retrospective assignments only after the two blind stage readouts seal."""

import argparse
from pathlib import Path
from statistics import median

from pre_finish_margin import CASES, DENSE, GAP, PROTOCOL, digest, parse, write
from prefix_ambiguity_0008 import DENSE_SEAL, WITNESS, WITNESS_PIN


def census(rows):
    two = [row for row in rows if row["gap"] is not None]
    shortlist = [row for row in two if row["gap"] <= GAP]
    return dict(curves=len(rows), points=sum(row["points"] for row in rows),
                at_least_two_eligible=len(two), exact_tie=sum(row["exact_ties"] > 1 for row in two),
                no_eligible=sum(row["feasible"] == 0 for row in rows),
                original_compact_second_omitted=sum(not row["second_retained_by_original"] for row in two),
                flag_count=len(shortlist), flagged_points=sum(row["points"] for row in shortlist),
                median_gap=median(row["gap"] for row in two) if two else None)


def compare(curves, legacy, switched):
    book = {row["curve"]: row for row in curves}
    outcome = []
    for target in switched:
        name = target["curve"]
        final = legacy[name]["ids"]
        row = book.get(name)
        if row is None:
            outcome.append(dict(curve=name, id_match="absent", final_points=len(final)))
            continue
        order = [j[0] for j in row["sealed_gated_ranks"]]
        selection = {k: (1+order.index(target[k]) if target[k] in order else None) for k in ("old", "new")}
        initial = row["observation_ids"]
        exact = final == initial
        common = len(set(final) & set(initial))
        outcome.append(dict(curve=name, id_match="exact_order" if exact else "overlap_only",
                            final_points=len(final), initial_points=len(initial), common_points=common,
                            old=target["old"], new=target["new"], old_rank=selection["old"], new_rank=selection["new"],
                            pair_in_top_two=sorted(r for r in selection.values() if r is not None) == [1, 2],
                            original_top_two=row["sealed_gated_ranks"][:2], gap=row["gap"],
                            flagged=row["gap"] is not None and row["gap"] <= GAP))
    return outcome


def score(root):
    records = {}
    # Read both authenticated stage seals before opening the final assignment or switch books.
    for case in CASES:
        folder = root/case
        seal = parse(folder/"seal.json", digest(folder/"seal.json"))
        admission = parse(folder/"admission.json", seal["admission.json"])
        clock = parse(folder/"clock.json", seal["clock.json"])
        if admission["protocol"] != digest(PROTOCOL):
            raise ValueError("Prototype or prospective method changed")
        data = parse(folder/"stage.json", seal["stage.json"]) if "stage.json" in seal else None
        if data and (clock["exit_code"] or data["protocol"] != admission["protocol"] or data["wrapper"] != admission["wrapper"]):
            raise ValueError("Stage proof differs from its previous seal")
        records[case] = dict(clock=clock, admission=admission, stage=data, seal=digest(folder/"seal.json"))
    scores = {n: census(r["stage"]["curves"]) for n,r in records.items() if r["stage"] is not None}
    after_seal = None
    if records["dense"]["stage"] is not None:
        switched = parse(WITNESS, WITNESS_PIN)["unchanged_curve_rows"]
        parent = parse(DENSE/"prediction-seal.json", DENSE_SEAL)
        name = "full-20/routed/risk-route.json"
        former = parse(DENSE/name, parent[name])["solves"][0]["lean_final_fit"]["arms"]["c0"]["curves"]
        after_seal = compare(records["dense"]["stage"]["curves"], former, switched)
    write(root/"result.json", dict(scopes=records, disjoint_curve_census=scores,
         joined_dense_curve_witness=after_seal, margin_cut_raw_cost=GAP, dense_signed_ceiling_cpu_s=2.707,
         profiling_uses_reference_position=False, new_full_solves=0, new_waveform_reads=0))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    score(parser.parse_args().root)
