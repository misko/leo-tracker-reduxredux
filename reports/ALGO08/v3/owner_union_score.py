"""Score the frozen owner-union decisions against the original saved v3 publications."""

import argparse
from hashlib import sha256
import csv
import json
from pathlib import Path

from aperture_score import PHYSICAL, SIMULATED, face_clearance_km, references
from aperture_trial import ARMS, inputs, read
from mixture_score import section
from owner_union_trial import CASES
from primary_owner_census import canonical_owners, pinned_aperture


HERE = Path(__file__).resolve().parent


def compare_lanes(stock, candidate):
    common = stock.keys() & candidate.keys()
    return dict(shared=len(common), same_satellite=sum(stock[k] == candidate[k] for k in common),
                changed_satellite=sum(stock[k] != candidate[k] for k in common),
                missing=len(stock.keys() - candidate.keys()), added=len(candidate.keys() - stock.keys()))


def budget(full, replay):
    boundary = read(HERE / "measurements/acquisition-split-DS30-0008.json")
    detector = sum(g["cpu_s"] for g in boundary["detector_groups"].values())
    outside = boundary["outside_detector_cpu_s"]
    with (HERE / "first-55/stage-clocks.csv").open() as stream:
        archived, = [row for row in csv.DictReader(stream) if row["recording"] == "DS30-0008"]
    budget_cpu = float(archived["cpu_s"]) / 2
    full_lanes = replay["price"]["admitted"]["lanes"]
    estimates = {}
    for name in ("owned_only", "ideal_donor_floor", "exported_donor_proxy", "full_original_donor_window"):
        acquisition = outside + detector * replay["price"][name]["lanes"] / full_lanes
        estimates[name] = dict(acquisition_cpu_s=acquisition,
                               cpu_s_available_for_solver_and_publication=budget_cpu - acquisition,
                               total_cpu_s_before_publication=acquisition + replay["charged"]["cpu_s"])
    return dict(
        full_solver_cpu_s=full["cpu_s"], masked_solver_cpu_s=replay["charged"]["cpu_s"],
        detector_cpu_s=detector, outside_detector_cpu_s=outside, half_cpu_budget_s=budget_cpu,
        same_mean_call_cost=estimates,
    )


def score(directory, output):
    preserved = pinned_aperture()
    truth = references()
    results = {}
    for case in CASES:
        paths = {mode: directory / f"{case}-{mode}.json" for mode in ("prepare", "masked")}
        candidate = read(paths["masked"])
        baseline = read(paths["prepare"])
        native, _, _, expected, identity = inputs(case)
        if any(row["identity"] != identity or row["full_v3"] != expected for row in (candidate, baseline)):
            raise ValueError("Solver replay differs from the original saved comparison")
        if (candidate["masked_packet_sha256"] != baseline["masked_packet_sha256"] or
                candidate["price"] != baseline["price"] or candidate["source_sha256"] != baseline["source_sha256"]):
            raise ValueError("Preparation and solve imports used different owner selectors")
        reference = preserved[case]["full"]
        full_owners = canonical_owners(native, reference, identity, expected) if expected["status"] == "ok" else {}
        ownership = {arm: compare_lanes({row["observation_id"]: row["norad"]
                                         for row in full_owners.get(arm, {}).values()},
                                       candidate["owners"].get(arm, {})) for arm in ARMS}
        result = candidate["result"]
        scores = section(result["arms"], truth[case], expected["arms"])
        original_scores = section(expected["arms"], truth[case], expected["arms"])
        exact = all(expected.get(key) == result.get(key) for key in
                    ("status", "reason", "arms", "owners", "science", "orbit_policy"))
        pair = dict(identity=identity, mask_authority=candidate["mask_authority"], pricing=candidate["price"],
                    original_numerical_evidence=expected, masked_numerical_evidence=result,
                    full_preparation=baseline["preparation"], masked_preparation=candidate["preparation"],
                    masked_discovery=candidate["discovery"], masked_metrics=candidate["metrics"],
                    full_timing=dict(cpu_s=reference["cpu_s"], elapsed_s=reference["elapsed_s"]),
                    masked_timing=candidate["charged"], numerical_grid_complete=candidate["numerical_grid_complete"],
                    ownership=ownership, exact_terminal_and_science=exact, original_scores=original_scores,
                    masked_scores=scores, offer_clearance_km=face_clearance_km(identity["offer"], truth[case]),
                    masked_packet_sha256=candidate["masked_packet_sha256"],
                    source_sha256=candidate["source_sha256"], machine=candidate["machine"],
                    raw_receipt_sha256={mode: sha256(path.read_bytes()).hexdigest() for mode, path in paths.items()})
        if case == "DS30-0008":
            pair["cpu_ceiling"] = budget(reference, candidate)
        results[case] = pair
    if results["south-containing"]["masked_packet_sha256"] != results["south-far"]["masked_packet_sha256"]:
        raise ValueError("The omitted-region control differs from the frozen containing selector")
    with output.open("x") as stream:
        print(json.dumps(dict(cases=results, reference_sha256={path.name: sha256(path.read_bytes()).hexdigest()
                                                             for path in (PHYSICAL, SIMULATED)}),
                         indent=2, sort_keys=True, allow_nan=False), file=stream)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    score(**vars(parser.parse_args()))
