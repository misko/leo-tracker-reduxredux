"""Attribute the already saved objective calls without another fit."""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path


def forward(x, lower, upper, step):
    result = []
    for axis in range(2):
        up, down = upper[axis]-x[axis], x[axis]-lower[axis]
        signed = min(step, up) if up >= step or up >= down else -min(step, down)
        shifted = x.copy()
        shifted[axis] += signed
        result.append(shifted)
    return result


def classify(trace, half_width, *, include_requests=False):
    found = Counter()
    charged = Counter()
    after_refresh = Counter()
    classes = []
    fit, requested = trace["result"], trace["full_calls"]
    history = fit["history"]
    lower, upper = [-half_width]*2, [half_width]*2
    current, following = history[0]["parameters"], 1
    if requested[0]["point"] != current or requested[0]["score"] != history[0]["score"]:
        raise ValueError("The fit started without its original objective")

    def charge(name, items):
        found[name] += len(items)
        charged[name] += sum(row["cpu_ns"] for row in items)
        if include_requests:
            classes.extend([name] * len(items))

    charge("initial", requested[:1])
    cursor = 1
    fresh = False
    while cursor < len(requested):
        pair = requested[cursor:cursor+2]
        if [item["point"] for item in pair] == forward(current, lower, upper, .001):
            charge("derivative", pair)
            after_refresh["another_refresh_without_trial"] += fresh
            fresh = True
            cursor += 2
            continue
        trial = requested[cursor]
        if (following < len(history) and trial["point"] == history[following]["parameters"]
                and trial["score"] == history[following]["score"]):
            charge("accepted_trial", [trial])
            after_refresh["first_trial_accepted"] += fresh
            current = trial["point"]
            following += 1
        else:
            charge("rejected_trial", [trial])
            after_refresh["first_trial_rejected"] += fresh
        fresh = False
        cursor += 1
    after_refresh["stopped_without_trial"] += fresh
    exact = trace["proposals"].get("exact_linearizations", fit["jacobian_refreshes"])
    if (following != len(history) or found["derivative"] != 2*exact
            or found["rejected_trial"] != fit["rejected_trials"] or sum(found.values()) != fit["evaluations"]):
        raise ValueError("Coordinate replay does not reproduce the released request classes")
    result = dict(calls=found, cpu_ns=charged, immediately_after_each_exact_refresh=after_refresh)
    if include_requests:
        result["request_classes"] = classes
    return result


def run(path, binding):
    raw = path.read_bytes()
    source = json.loads(binding.read_bytes())
    data = json.loads(raw)
    if sha256(binding.read_bytes()).hexdigest() != data["binding_sha256"]:
        raise ValueError("The scoped fit changed its frozen region")
    offer = json.loads(Path(source["request"]["offer"]).read_bytes())
    scope = data["scope"]
    return dict(source_sha256=sha256(raw).hexdigest(), summaries={
        mode: [classify(trace, offer["width_km"]/2) for trace in results["optimizer"]]
        for mode, results in scope["results"].items()
    })


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = run(args.directory / "result.json", args.directory / "binding.json")
    with args.output.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
