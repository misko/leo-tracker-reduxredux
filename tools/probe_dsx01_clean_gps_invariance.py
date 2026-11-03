"""Adversarial diagnostic: move imported evaluation constants to another continent.

Runs only after normal inference. No altered GPS value enters report scoring.
Fresh discovery and all current objective recipes must remain unchanged.
"""

import hashlib
import json
import sys

import numpy as np
from associate_merged_track_catalogue import write
from map_dsx01_clean_region import SPECS, factory, loss, refresh_quality
from run_dsx01_clean_region import OUTPUT, fresh_discovery, load_scan, standard_problem


def fingerprint(value):
    def encode(x):
        return (
            x.tolist()
            if isinstance(x, np.ndarray)
            else x.item()
            if isinstance(x, np.generic)
            else x
        )

    return hashlib.sha256(json.dumps(value, sort_keys=True, default=encode).encode()).hexdigest()


def run(case="DSX01-S01"):
    directory = OUTPUT / case
    atlas = json.loads((directory / "atlas.json").read_text())
    node = min(atlas["nodes"], key=lambda r: r["score"])
    scan, sigma = load_scan(case)
    scan.strict_causal_history = json.loads((directory / "causal_history.json").read_text())
    refresh_quality(
        scan, standard_problem(scan, node["seed"], sigma, aliases=node["aliases"]), node["point"]
    )

    def scores():
        return {
            name: {
                arm: [
                    loss(factory(scan, node, sigma, name, arm == "fitted_c"), point)
                    for point in [[0, 0], [4, -6]]
                ]
                for arm in ["c0", "fitted_c"]
            }
            for name in SPECS
        }

    before = scores()
    discovery_before = fresh_discovery(scan, sigma, budget=8)
    changed = []
    for module_name, module in list(sys.modules.items()):
        if module is None or "/tools/" not in str(getattr(module, "__file__", "")):
            continue
        for key, value in list(vars(module).items()):
            if (
                isinstance(value, (tuple, list))
                and len(value) == 2
                and all(isinstance(x, (int, float)) for x in value)
            ):
                if (
                    abs(value[0] - 37.849061591561885) < 1e-9
                    and abs(value[1] + 122.48574968092912) < 1e-9
                ):
                    setattr(module, key, (-33.86, 151.21))
                    changed.append(f"{module_name}.{key}")
            elif isinstance(value, (int, float)):
                if abs(value - 37.849061591561885) < 1e-9:
                    setattr(module, key, -33.86)
                    changed.append(f"{module_name}.{key}")
                elif abs(value + 122.48574968092912) < 1e-9:
                    setattr(module, key, 151.21)
                    changed.append(f"{module_name}.{key}")
    after = scores()
    discovery_after = fresh_discovery(scan, sigma, budget=8)
    maximum = max(
        abs(before[m][a][i] - after[m][a][i])
        for m in SPECS
        for a in ["c0", "fitted_c"]
        for i in range(2)
    )
    identical = fingerprint(discovery_before) == fingerprint(discovery_after)
    write(
        OUTPUT / "gps_invariance.json",
        dict(
            case=case,
            changed_constants=changed,
            replacement_evaluation_coordinate=[-33.86, 151.21],
            fresh_discovery_bit_identical=identical,
            recipe_count=len(SPECS),
            objective_checks=len(SPECS) * 4,
            maximum_objective_difference=maximum,
            limitation=(
                "targeted regression check, not proof against every possible hidden dependency"
            ),
        ),
    )
    if not changed or maximum != 0 or not identical:
        raise SystemExit("GPS invariance failed")
    print(len(changed), maximum, identical, flush=True)


if __name__ == "__main__":
    run()
