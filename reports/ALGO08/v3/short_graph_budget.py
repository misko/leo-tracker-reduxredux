"""Translate the two measured dense graph routes at the fastest observed short reader rate."""

import argparse
import json
from pathlib import Path
from statistics import median

from acquisition_throughput import gates, minimum_rate


DATA = Path(__file__).resolve().parent / "measurements"


def read(name):
    return json.loads((DATA / name).read_bytes())


def prices(rows, rate, fraction, overhead, recovered_time):
    ordinary = gates(rows, rate, fraction, startup_s=overhead)
    costs = []
    for row in rows:
        acquire, solve, tail = row["stages"]
        old = sum(row["stages"])
        if row["case"] == "DS30-0022":
            # Saved publication includes Python, verified handoff, numerical result and eight figures.
            # Retain its full cost in this sensitivity and also charge one raw reader pass.
            new = row["compressed_MB"] / rate + recovered_time
        elif acquire:
            new = overhead + row["compressed_MB"] / rate + fraction * solve + tail
        else:
            new = old
        costs.append((new, old))
    ratios = [n/o for n,o in costs]
    return dict(median_and_sum=ordinary, with_projected_recovery=[median(ratios), sum(n for n,_ in costs)/sum(o for _,o in costs)],
                reader_needed_MB_s=[minimum_rate(rows, fraction, i, startup_s=overhead) for i in (0, 1)])


def model():
    inventory = read("acquisition-throughput.json")["rows"]
    calibration = read("full-short-seal-scaling.json")
    best = max((r["measurements"] for r in calibration["projections"]["receiver"] if r["arm"] == "full-short"),
               key=lambda r: r["reader_MB_s"])
    fused = read("dense-quadratic-fused.json")
    live = read("live-inference-profile-summary.json")["runs"]
    stock = live["installed"]["solve"]["cpu_s"]
    numerator = {label: row["solve"]["cpu_s"] for label, row in fused["records"].items()}
    orbit = read("full-short-orbit-transfer.json")
    rate = best["reader_MB_s"]
    charge = best["worker_overhead_s"] + calibration["shared_once_per_recording_tails_s"]["optimistic"]
    only, = [row for row in inventory if row["case"] == "DS30-0022"]
    return dict(recordings=len(inventory), reader_MB_s=rate, additional_charge_s=charge, installed_dense_s=stock,
                dense_detector=fused["identity"]["detector_sha256"], recovered_elapsed_s=orbit["process"]["elapsed_s"],
                interpolated_recovered_raw_s=only["compressed_MB"]/rate+orbit["process"]["elapsed_s"],
                historical_failed_raw_s=sum(only["stages"]), original_and_fused_s=numerator,
                scenarios={k: prices(inventory, rate, cpu/stock, charge, orbit["process"]["elapsed_s"])
                           for k,cpu in numerator.items()})


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    with args.output.open("x") as stream:
        json.dump(model(), stream, indent=2)
        stream.write("\n")
