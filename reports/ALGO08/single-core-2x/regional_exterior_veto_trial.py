"""Audit a frozen geographic veto using only the saved all-track probe packets."""

import gzip
from hashlib import sha256
import json
from pathlib import Path
from statistics import median
from time import process_time_ns

from tools.pipeline_eval.variants.experimental.regional_exterior_veto import evaluate


MEASUREMENTS = Path(__file__).parent / "measurements"
PINS = {
    "regional-reassignment.json.gz": (
        "735553ef3b9287884f6473bfc78bd8740e45c23927c79c56d95b0ba53376bb4a"
    ),
    "region-mirrors.json.gz": "ee8f80ec6267e7fe333d05ac794775fb54bc349cd143022a55599bf2f9af4728",
}


def load(name):
    contents = (MEASUREMENTS / name).read_bytes()
    if sha256(contents).hexdigest() != PINS[name]:
        raise ValueError("Saved probes differ from their predeclared digest")
    return json.loads(gzip.decompress(contents))


def saved_offers():
    rows = load("regional-reassignment.json.gz")
    for site, pair in load("region-mirrors.json.gz")["sites"].items():
        original = rows[f"{site}-edge"]
        for key in ("points", "offer", "native_sha256", "snapshots"):
            if pair["inside"][key] != original[key]:
                raise ValueError("Mirrored inside probes differ from the original edge packet")
        rows[f"{site}-mirror-outside"] = pair["outside"]
    return rows


def main():
    rows = saved_offers()

    inputs = {name: (row["points"], row["offer"]["width_km"]) for name, row in rows.items()}
    results = {name: evaluate(*arguments) for name, arguments in inputs.items()}
    cpu_clocks = []
    for _ in range(101):
        began = process_time_ns()
        for arguments in inputs.values():
            evaluate(*arguments)
        cpu_clocks.append((process_time_ns() - began) / len(inputs))

    categories = {
        "containing": "centered",
        "edge": "100m_inside",
        "omitted": "1500m_outside",
        "far": "far_outside",
        "mirror-outside": "100m_outside",
    }
    for name, row in rows.items():
        category = categories[name.split("-", 1)[1]]
        contains = category in {"centered", "100m_inside"}
        results[name].update(
            category=category, contains=contains, native_sha256=row["native_sha256"],
            offer_width_km=row["offer"]["width_km"],
            original_observations=row["original_points"],
            observations_by_receiver=row["receiver_points"],
            input_probe_cpu_s=row["cpu_s"],
        )
    print(json.dumps(dict(
        inputs=PINS, observations=results,
        incremental_cpu_ns_per_offer_median=median(cpu_clocks),
        timing_batches=len(cpu_clocks),
    ), allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
