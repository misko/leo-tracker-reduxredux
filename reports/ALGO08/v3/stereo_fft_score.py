"""Bind exact stereo controls to the saved clock and FFT plan comparisons."""

import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import median


BASE = Path(__file__).resolve().with_name("measurements")
NAMES = ("weak", "dense")
FACTOR_REFERENCE = "dc132cbaac6cb3eddb21ec4c7df950b03eb1713461dac2d50ff0a92ac3e9a13b"


def summarize(record):
    runs = record["repeats"]
    methods = runs[0]["clocks"].keys()
    clocks = {method: {metric: median(row["clocks"][method][metric] for row in runs)
                       for metric in ("cpu_s", "wall_s", "median_stereo_cpu_ms")} for method in methods}
    baselines = ("installed", "scalar_dispatch")
    ratios = {control: [r["clocks"]["paired_fft"]["cpu_s"] / r["clocks"][control]["cpu_s"] for r in runs]
              for control in baselines}
    return dict(median_clocks=clocks, paired_per_repeat_ratio=ratios,
                clears_20_percent_gate=all(median(value) <= .80 for value in ratios.values())
                and not record["differences"])


def score(directory, output):
    raw = {group: (directory / f"{group}.json").read_bytes() for group in NAMES}
    rolled = (BASE / "directed-verifier.json.gz").read_bytes()
    if sha256(rolled).hexdigest() != FACTOR_REFERENCE:
        raise ValueError("The earlier exact same-window factor reference changed")
    known = json.loads(gzip.decompress(rolled))["groups"]
    profile = (BASE / "receiver-polyphase-timing.json").read_bytes()
    previous = json.loads(profile)["runs"]
    plan = (directory / "fftw-plans.json").read_bytes()
    out = {}
    for name, blob in raw.items():
        result = json.loads(blob)
        comparator = previous[name]
        if result["inputs"] != known[name]["input_digests"] or result["inputs"] != comparator["inputs"]:
            raise ValueError("New and previous timing panels use different I/Q")
        searches = comparator["stages"][0]
        pair_scopes = searches["time_search"]["cpu_s"] + searches["carrier_search"]["cpu_s"]
        overall = sum(row[0] for row in comparator["comparisons"]["half_grid"]["total_cpu_s"])
        out[name] = dict(**result, summary=summarize(result),
                         exact_installed_factors_by_rank=known[name]["baseline_factors_by_rank"],
                         timing_and_carrier_profile_proxy=dict(profiled_stage_cpu_s=pair_scopes,
                                                               uninstrumented_reference_cpu_s=overall,
                                                               combined_share_proxy=pair_scopes/overall))
    receipt = dict(cohorts=out, plans=json.loads(plan), raw_sha256={key: sha256(blob).hexdigest() for key, blob in raw.items()},
                   profile_sha256=sha256(profile).hexdigest(), plan_sha256=sha256(plan).hexdigest(),
                   factor_reference_sha256=FACTOR_REFERENCE)
    with output.open("x") as stream:
        print(json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False), file=stream)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("directory", type=Path)
    cli.add_argument("output", type=Path)
    score(**vars(cli.parse_args()))
