"""Check the actual frozen v5 request validator against every blind-study tile center."""

import json
import sys

from .run_v5_panel import ARCHIVE, BLIND, HERE, read


def main():
    config = read(ARCHIVE / "plans/science.json")
    sys.path.insert(0, config["source"]["root"])
    from leo.operations.localization_v3_job import validate_request

    path = ARCHIVE / "results/DS26-0036-r0/baseline/experimental-request.json"
    job = read(path)["job"]
    validate_request(job)
    result = {"accepted_control": job["search_center"], "panels": {}}
    for panel in ["recorded", "field", "field2", "synthetic"]:
        root = BLIND / ("public_" + panel)
        ids = read(root / "manifest.json")["queries"]
        checked, accepted = 0, 0
        for qid in ids:
            q = read(root / "queries" / (qid + ".json"))
            for region in q["regions"]:
                checked += 1
                try:
                    validate_request(dict(job, search_center=region["center"]))
                except ValueError as exc:
                    if "requires the production regional frame" not in str(exc):
                        raise
                else:
                    accepted += 1
        result["panels"][panel] = dict(queries=len(ids), single_tile_requests=checked,
                                       accepted_centers=accepted)
    (HERE / "v5-region-contract.json").write_text(json.dumps(result, indent=2) + "\n")


if __name__ == "__main__":
    main()
