"""Compare disjoint clocks for ready packed, retrofit and owned-writer boundaries."""

import argparse
import gzip
from hashlib import sha256
import json
from math import ceil
from pathlib import Path
from statistics import median

MEASURES = Path(__file__).resolve().parent / "measurements"
CASES = ("DS30-0016", "DS30-0107")
PINS = {
    "integrated-original": "eb115ec1dd7a734693e21d8be49e2f7de87fe48936b8db8d51e1216cf37a0dff",
    "raw-denominator-audit": "a9509fb5125a5635963fcc40b7bc2afbaace98768153fb4a0b3a07c4f9374645",
    "strict-cairo-0016": "92eb659eeb74b1e1ec90cdf083673fb75f9e4640324aaf0cd976b143337e64a7",
    "strict-cairo-0107": "8e30886adeb6ec4b475a6f023fa0ed32b79bdc3e6b267710f1e75fef34850145",
    "owned-capture-DS30-0016": "e9f92d0f19436bcbccca520c470f364ab311c916ec92c2dbea9b3fe3c58d87b5",
    "north-direct-multichunk": "ffc4255b8bcbbe251ae4ba34a16e74198d69c6402b211b85ec8aa1fa354619ba",
    "ci16-packed-storage-0016": "8e33cb40ee53bc544204e22f147a649a3c12700c09d73b52f0d2bd901e4b2c00",
    "ci16-packed-storage-0008": "5ac99fe6ae717d37b419c530ba7b7afbc5f1574eaea8b3fd1360ec2758aa767a",
}


def read(name):
    data = (MEASURES / f"{name}.json.gz").read_bytes()
    if sha256(data).hexdigest() != PINS[name]:
        raise ValueError(f"An archived timing changed for {name}")
    return json.loads(gzip.decompress(data))


def acquisition(phases):
    return phases["authenticated_raw_acquisition"]["elapsed_s"]


def replace_acquisition(process, current, strict, setup):
    if not 0 < current <= process or strict <= 0 or setup < 0:
        raise ValueError("Invalid disjoint raw acquisition replacement")
    return process - current + strict + setup


def metrics(stock, candidates):
    denominator, numerator = sum(stock), sum(candidates)
    return dict(summed_s=numerator, summed_speedup=denominator/numerator,
                paired_median_speedup=1/median(c / s for s, c in zip(stock, candidates, strict=True)),
                remaining_to_half_s=numerator - denominator/2)


def member_cases():
    rows = {}
    for case in ("DS30-0016", "DS30-0008"):
        doc = read("ci16-packed-storage-" + case[5:])
        data = (doc["final"] if case == "DS30-0016" else doc)["data"]
        used = data["runs"]
        if any(p["ordinary"]["first_analysis"]["probes_sha256"] != p["packed-ci16"]["first_analysis"]["probes_sha256"]
               for p in used):
            raise ValueError("Capture comparison must use the same ordered detector")
        modes = {}
        for arm in ("ordinary", "packed-ci16"):
            modes[arm] = dict(writer_s=median(r[arm]["capture"]["timing"]["wall_ns"] for r in used) / 1e9,
                selective_first_analysis_s=median(r[arm]["first_analysis"]["timing"]["wall_ns"] for r in used) / 1e9,
                joint_s=median(r[arm]["capture_to_first"]["wall_ns"] for r in used) / 1e9,
                bytes=used[0][arm]["capture"]["total_bytes"])
        saving = [(p["ordinary"]["capture_to_first"]["wall_ns"]-p["packed-ci16"]["capture_to_first"]["wall_ns"])/1e9
                  for p in used]
        stages = dict(conversion_s=data["legacy_conversion"]["wall_ns"] / 1e9,
                      independent_recovery_s=data["legacy_recovery"]["timing"]["wall_ns"] / 1e9,
                      selective_first_analysis_s=data["legacy_first_analysis"]["timing"]["wall_ns"] / 1e9)
        rows[case] = dict(modes=modes, paired_joint_saving_s=saving, first_use_existing=sum(stages.values()), stages=stages)
    return rows


def score():
    raw = read("raw-denominator-audit")
    records = [max((r for r in raw["observations"] if r["case"] == case and r["stratum"] == "private-tmpfs"),
                   key=lambda r: r["start_unix_ns"]) for case in CASES]
    fresh = [r["clock"]["elapsed_s"] for r in records]
    positive, tiny = read("strict-cairo-0016"), read("strict-cairo-0107")
    historic_stock = [positive["stock"]["elapsed_s"], tiny["costs"]["stock"]["elapsed_s"]]
    strict = [acquisition(positive["witness"]["phases"]), acquisition(tiny["candidate"]["phases"])]
    ready = [positive["breakdown"]["ready_elapsed_s"], tiny["costs"]["scopes"]["ready"][0]]
    frozen_child = [positive["candidate"]["elapsed_s"], tiny["costs"]["scopes"]["child"][0]]
    setup = [total - child for total, child in zip(ready, frozen_child, strict=True)]
    convert = [positive["breakdown"]["conversion_and_readback_s"], tiny["costs"]["scopes"]["first"][0] - ready[1]]
    history = dict(ready=metrics(historic_stock, ready), first_use=metrics(historic_stock,
        [c + a for c, a in zip(convert, ready, strict=True)]), stock_elapsed_s=historic_stock,
        acquisition_s=strict, candidate_setup_s=setup, conversion_and_readback_s=convert)
    writer = read("owned-capture-DS30-0016")
    owned = {arm: dict(write_s=(sum(row["writer"][arm]["wall_ns"] for row in writer["source"]) +
                            writer["commit"][arm]["wall_ns"])/1e9,
                       independent_readback_s=writer["readback"][arm]["clock"]["wall_ns"]/1e9,
                       bytes=writer["storage"][arm]) for arm in ("ordinary", "packed")}
    result = {}
    for order, cases in read("integrated-original")["runs"].items():
        docs = [cases[case]["result"]["document"] for case in CASES]
        if not all(d["qualified"] for d in docs):
            raise ValueError("Integrated clock lacks qualified original science")
        processes = [d["process"]["elapsed_s"] for d in docs]
        acquired = [acquisition(d["receiver"]["phases"]) for d in docs]
        ready_both = [replace_acquisition(*values) for values in zip(processes, acquired, strict, setup, strict=True)]
        ready_positive = [ready_both[0], processes[1]]
        prior_first_compare = owned["ordinary"]["write_s"] + fresh[0]
        original_owned = owned["ordinary"]["write_s"] + processes[0]
        paid_owned = owned["packed"]["write_s"] + owned["packed"]["independent_readback_s"] + ready_positive[0]
        saved = processes[0] - ready_positive[0]
        result[order] = dict(original=metrics(fresh, processes), observed_processes_s=processes, observed_acquisition_s=acquired,
            prepared_projection_positive_only=metrics(fresh, ready_positive),
            prepared_projection_both=metrics(fresh, ready_both),
            estimated_positive_saved_s=saved,
            existing_first_use_positive=metrics(fresh, [ready_positive[0]+convert[0], ready_positive[1]]),
            existing_first_use_both=metrics(fresh, [x+c for x,c in zip(ready_both, convert, strict=True)]),
            existing_positive_repeated_break_even_analyses=ceil(convert[0]/saved) if saved > 0 else None,
            owned_write_to_exit_positive_projection=dict(stock_s=prior_first_compare, integrated_original_s=original_owned,
                candidate_s=paid_owned, stock_to_candidate_speedup=prior_first_compare/paid_owned,
                integrated_original_minus_candidate_s=original_owned-paid_owned))
    north = read("north-direct-multichunk")["complete"]
    north_times = {key: {name: body[name] for name in ("capture", "publication", "total")}
                   for key, body in north["timing"]["arms"].items()}
    return dict(source_sha256=PINS, cases=CASES, selected_stock_cases=records, fresh_stock_s=fresh,
                qualitative_boundary="projection replaces only acquisition and charges each qualifying source once",
                historical_strict=history, owned_0016=owned, north_complete=north_times,
                sampled_member_costs=member_cases(), modeled_integrated=result)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    with args.output.open("x") as stream:
        json.dump(score(), stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
