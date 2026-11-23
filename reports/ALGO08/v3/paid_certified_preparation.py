"""Audit release preparation and price it without performing further fits."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path

from aperture_trial import read, write
from paid_certified_trial import CASES, MODES, check_binding


def compare(fit, original, released):
    before, after = (row["prepared"][0] for row in (original, released))
    old = fit["prepared"][0]
    checks = dict(same_prepared_values=before["prepared_sha256"] == after["prepared_sha256"],
                  same_fit_graph=all(old[key] == after[key] for key in ("status", "observations", "arcs", "graph_points", "curved")))
    replay = {clock: fit[clock] - old[clock] + after[clock] for clock in ("cpu_s", "elapsed_s")} if all(checks.values()) else None
    return dict(checks=checks, fit_with_original_instrumentation={clock: fit[clock] for clock in ("cpu_s", "elapsed_s")},
                projected_solve=replay, preparation=dict(original=before, released=after),
                tle_records=dict(original=original["tle_records"], released=released["tle_records"]))


def score(fits, audit, output):
    raw = fits.read_bytes()
    sealed = json.loads(gzip.decompress(raw))
    rows = sealed["runs"]
    inputs = {}
    comparisons = {}
    for case in CASES:
        comparisons[case] = {}
        for mode in MODES:
            fit = rows[case][mode]
            snapshots = []
            for scope in ("original-instrumentation", "released"):
                path = audit / f"{case}-{mode}-{scope}.json"
                observed = read(path)
                check_binding(observed["identity"], fit["identity"], mode)
                if (observed["preparation_audit"] != scope or observed["attempts"] or observed["fallback"]
                        or observed["reason"] != "preparation_audit_only" or len(observed["prepared"]) != 1):
                    raise ValueError("Expected a single normalized preparation with zero fits")
                inputs[path.name] = sha256(path.read_bytes()).hexdigest()
                snapshots.append(observed)
            paired = compare(fit, *snapshots)
            prediction = paired["projected_solve"]
            prior = sealed["scores"][case][mode]["projected_acquisition_and_solve_cpu_s"]
            paired["projected_acquisition_and_solve_cpu_s"] = (
                prior - fit["cpu_s"] + prediction["cpu_s"] if prediction is not None else None
            )
            comparisons[case][mode] = paired
    write(output, dict(cases=comparisons, verification=dict(fits_sha256=sha256(raw).hexdigest(), inputs=inputs)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("fits", "audit", "output"):
        parser.add_argument(name, type=Path)
    score(**vars(parser.parse_args()))
