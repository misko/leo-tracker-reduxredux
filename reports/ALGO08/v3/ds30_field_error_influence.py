"""Measure outlier sensitivity and score the offered center on the first 16 signed DS30 pairs."""

import argparse
import json
from pathlib import Path

from .ds30_centered_error import EXPORT, INITIAL, study
from .ds30_oracle_routing import CAMPAIGN, PLAN, checked
from .full_successor_score import ARMS, compare_centers, paired_rows, roster, squared_error_influence


def evaluate(campaign, snapshot):
    custody = study(campaign, snapshot)["original_scope"]
    plan = json.loads(checked(campaign/"plan.json", PLAN))
    offer_pin = plan["offered_region_sha256"]
    offer = json.loads(checked(campaign/"offer.json", offer_pin))
    rows = [row for line in checked(snapshot/"rows-with-relocations.jsonl", EXPORT).splitlines()
            if (row := json.loads(line))["case"] in INITIAL]
    assigned = roster()
    pairs = paired_rows(rows, {case: assigned[case] for case in INITIAL})
    return dict(source=custody, offered_region_sha256=offer_pin, prior=compare_centers(pairs, assigned, offer),
                squared_error_influence={arm: squared_error_influence(pairs, arm) for arm in ARMS},
                shared_errors_km={arm: {a["case"]: [a[arm+"_error_km"], b[arm+"_error_km"]] for a, b in pairs
                                        if a[arm+"_error_km"] is not None and b[arm+"_error_km"] is not None}
                                  for arm in ARMS})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--campaign", type=Path, default=CAMPAIGN)
    parser.add_argument("--snapshot", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.campaign, args.snapshot), indent=2, allow_nan=False))
