"""Fixed null-prior ablation with the same local-search evaluation budget."""

import argparse
import json
from pathlib import Path

import ds7_wave2_search_adapter as adapter

from tools.ds7_null_mixture import NullMixtureJoint


def estimate(request):
    baseline = adapter.fast.baseline
    previous = baseline.JointObjective
    models = []

    def objective(documents, config):
        model = NullMixtureJoint(documents, config, baseline)
        models.append(model)
        return model

    baseline.JointObjective = objective
    try:
        result = adapter.estimate(request)
        if result["status"] == "ok":
            diagnostics = result["diagnostics"]
            state = diagnostics["east_north_km"] + diagnostics["timing_offsets_s"]
            values = models[0].null_responsibilities(state)
            diagnostics["null_prior_mass"] = request["config"]["null_prior_mass"]
            diagnostics["null_responsibilities"] = values
            diagnostics["mean_null_responsibility"] = sum(values) / len(values)
            diagnostics["null_policy"] = "per-track constant frequency with stationary offset"
        return result
    finally:
        baseline.JointObjective = previous


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=Path, required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    response = estimate(json.loads(args.request.read_text()))
    with args.response.open("x") as stream:
        json.dump(response, stream, allow_nan=False)


if __name__ == "__main__":
    main()
