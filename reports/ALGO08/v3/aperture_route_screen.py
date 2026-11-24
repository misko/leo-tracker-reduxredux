"""Apply the unchanged held-cycle score to complete saved 8 and 12 ms packets."""

import argparse
from collections import Counter
import gzip
from hashlib import sha256
import json
from math import remainder, sqrt
from pathlib import Path
import sys


HERE = Path(__file__).resolve().parent
if __name__ == "__main__":
    sys.path.insert(0, str(HERE))

MEASUREMENTS = HERE / "measurements"
PINS = {
    "eight-ms-physical.json": "d5db26385ce031957206e47a0cf12ee2f93b04e2898daff2f10d7fd4e0452a7a",
    "eight-ms-north.json": "16ee7ed27cad9fac9403f57342e277a3551a76afee651e0e8e7c3f30f6f4971d",
    "dense-full-short-raw.json.gz": "51521b26848532823922cc43a198b7f91d59d3f1d81e155e5862b04b53193f38",
}
SOURCES = {"anchor_cycle_route.py": "fd6cd122b01fd6865cde965c6f6f8d72d97bb804642e835398de168ce333ab13",
           "anchor_exposure.py": "aec435ae4bcd86892566bfa6a21ec5fedb3c3b6174fe4f9b4640c986bd6cf8cd",
           "anchor_holds.py": "b0607a337c832b8a766b8e07e1f23417456e4046491a5acd26c8f7930cfbb7f5"}


def checked_bytes(path, pin):
    data = path.read_bytes()
    if sha256(data).hexdigest() != pin.removeprefix("sha256:"):
        raise ValueError(f"The sealed source changed at {path}")
    return data


def archived(name):
    data = checked_bytes(MEASUREMENTS / name, PINS[name])
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data)


def cost(original, short):
    """Optimistic expectation-level break-even allowing a paid short-aperture retry."""
    spare = original - short
    return dict(original_primary_cpu_s=original, scout_primary_cpu_s=short, gross_cpu_s=spare,
                whole_primary_retry_break_even=max(0., spare/original))


def held(data):
    from anchor_cycle_route import select_route
    from anchor_exposure import enroll, positive
    from anchor_holds import history_rows

    result = select_route(data, audit=True)
    rows = data["source"]["probes"]
    history = history_rows(rows)
    original_counts = Counter()
    history_counts = Counter()
    for before, after, event in zip(rows, history, enroll(data), strict=True):
        original_counts[(event[2], event[4])] += positive(before)
        history_counts[(event[2], event[4])] += positive(after)
    return dict(route=result["route"], log_score_gain_by_radio=result["log_score_gain_by_radio"],
                complete_cycles={k: x["held"] for k, x in result["radio"].items()},
                original={f"{radio}-{mode}": count for (radio, mode), count in original_counts.items()},
                history={f"{radio}-{mode}": count for (radio, mode), count in history_counts.items()},
                scored_anchor_predictions=result["prediction_digest"])


def native_from_saved(run):
    from empty_bootstrap import bind_native

    root = Path(run["output_root"])
    (path,) = root.glob("fast-scan-automatic-work/*/detections.json")
    if not path.resolve(strict=True).is_relative_to("/dev/shm"):
        raise ValueError("Only existing local signed detector documents are enrolled")
    packet = json.loads(checked_bytes(path, run["native_sha256"]))
    source = packet["source"]
    bind_native(packet, source["session_id"], source["input_manifest_sha256"],
                packet["provenance"]["detector_sha256"][7:], expected=run["native_sha256"])
    return packet


def history_comparison(original, short):
    from anchor_holds import history_rows

    counts, cfo_values = Counter(), []
    for left, right in zip(*(history_rows(packet["source"]["probes"]) for packet in (original, short)), strict=True):
        a, b = left["candidates"], right["candidates"]
        counts.update(only_12=bool(a and not b), only_8=bool(b and not a), shared=bool(a and b))
        if a and b:
            (x,), (y,) = a, b
            delta = y["fractional_tracking_cfo_hz"]-x["fractional_tracking_cfo_hz"]
            dx = y["integer_epoch_sample"]+y["fractional_epoch_offset_samples"]
            dx -= x["integer_epoch_sample"]+x["fractional_epoch_offset_samples"]
            counts["rank_zero_timing_cfo_match"] += (x["candidate_rank"] == y["candidate_rank"] == 0
                                                     and abs(delta) <= 250 and abs(remainder(dx, 13_333)) <= 2)
            counts["exact_shared"] += x == y
            cfo_values.append(delta)
    rms = sqrt(sum(d*d for d in cfo_values)/len(cfo_values)) if cfo_values else None
    return dict(counts=counts, signed_cfo_delta_rms_hz=rms,
                max_abs_cfo_delta_hz=max(map(abs, cfo_values), default=None))


def run(path):
    from anchor_exposure import bind, enroll
    from empty_bootstrap import CONTINUATION, EXTRA_SOURCES
    from tools.pipeline_eval.variants import carrier_continuation

    for name, pin in SOURCES.items():
        checked_bytes(HERE/name, pin)
    checked_bytes(Path(carrier_continuation.__file__), EXTRA_SOURCES[CONTINUATION])
    cases = {}
    for case in ("physical", "north"):
        runs = archived(f"eight-ms-{case}.json")["runs"]
        labels = ("12ms", "8ms")
        files = {arm: native_from_saved(runs[arm]) for arm in labels}
        bind(*files.values())
        if any(a[4] != b[4] for a,b in zip(*(enroll(packet) for packet in files.values()), strict=True)):
            raise ValueError("The full-anchor schedule changed")
        compare = {arm: held(packet) | {"native_sha256": runs[arm]["native_sha256"]} for arm, packet in files.items()}
        price = cost(*(runs[arm]["native"]["native_cpu_ns"]["short_primary"]/1e9 for arm in labels))
        cases[case] = dict(held=compare, costs=price, comparison=history_comparison(*files.values()))
    dense = archived("dense-full-short-raw.json.gz")
    dense_pool = dense["candidate"]["recipe"]["receiver_audit"]["native"]["native_cpu_ns"]["short_primary"]/1e9
    ratio = max(case["costs"]["whole_primary_retry_break_even"] for case in cases.values())
    result = dict(cases=cases, dense_scenario=dict(original_primary_cpu_s=dense_pool, transferred_fraction=ratio,
                 projected_gross_cpu_s=ratio*dense_pool, raw_timing=False), source_pins=PINS | SOURCES,
                 continuation_sha256=EXTRA_SOURCES[CONTINUATION], solver_calls=0, waveform_calls=0)
    with path.open("x") as f:
        json.dump(result, f, sort_keys=True, indent=2, allow_nan=False)
        f.write("\n")


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    run(cli.parse_args().output)
