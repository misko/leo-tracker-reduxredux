"""Reduce existing signed-clock evidence without opening any recording or archive."""

import argparse
from dataclasses import dataclass
import gzip
from hashlib import sha256
from itertools import product
import json
from math import isfinite
from pathlib import Path
from statistics import median


MEASUREMENTS = Path(__file__).resolve().parent / "measurements"
POSITIVE, WITHHOLD = "DS30-0016", "DS30-0107"
GATES = (1.6, 2.0)
PRIVATE, CACHED, COLD, WRAPPED = "private-tmpfs", "warm-backing", "cold-backing", "cold-research-stock-worker"
INTEGRATED_PIN = "eb115ec1dd7a734693e21d8be49e2f7de87fe48936b8db8d51e1216cf37a0dff"


@dataclass(frozen=True)
class Reference:
    case: str
    stratum: str
    file: str
    clock: str
    cache: str = ""
    exit: str = ""


REFERENCES = (
    Reference(WITHHOLD, PRIVATE, "continued-cfo-small-raw-0107", "runs/stock/process/clock", "runs/stock/process/cache_before"),
    Reference(WITHHOLD, PRIVATE, "eight-ms-0107-pair", "documents/stock-clock.json/clock", "documents/stock-clock.json/cache_before"),
    Reference(WITHHOLD, PRIVATE, "adaptive-withhold-0107", "pair/clocks/stock/clock", "pair/clocks/stock/cache_before"),
    Reference(WITHHOLD, PRIVATE, "strict-packed-0107", "verification/measured/pair/clocks/stock/clock", "verification/measured/pair/clocks/stock/cache_before"),
    Reference(WITHHOLD, PRIVATE, "history-risk-0107-raw", "documents/stock-clock.json/value/clock", "documents/stock-clock.json/value/cache_before"),
    Reference(WITHHOLD, PRIVATE, "stock-raw-repeat-0107", "stock/process/clock", "stock/process/cache_before"),
    Reference(POSITIVE, PRIVATE, "history-risk-0016-raw-failed", "measured_exits/stock/clock", "measured_exits/stock/cache_before"),
    Reference(POSITIVE, PRIVATE, "history-risk-0016-raw", "measured_exits/stock/clock", "measured_exits/stock/cache_before"),
    Reference(POSITIVE, PRIVATE, "stock-raw-repeat-0016", "stock/process/clock", "stock/process/cache_before"),
    Reference(POSITIVE, CACHED, "raw-0016-best", "original/stock/process/clock", "original/stock/process/cache_before"),
    Reference(POSITIVE, CACHED, "unified-short-layout", "observations/weak/rows/stock/clock", "observations/weak/rows/stock/cache/at_launch"),
    Reference(POSITIVE, CACHED, "weak-combined-raw.json", "runs/stock/process", "runs/stock/cache"),
    Reference(POSITIVE, CACHED, "combined-frontier-weak-bypass", "runs/stock/clock", "runs/stock/cache"),
    Reference(POSITIVE, CACHED, "combined-frontier-weak-warm", "runs/stock/clock", "runs/stock/cache"),
    Reference(POSITIVE, CACHED, "unified-short-bootstrap", "observations/weak/rows/stock/clock", "observations/weak/rows/stock/cache/at_launch"),
    Reference(POSITIVE, COLD, "combined-frontier-weak", "runs/stock/clock", "runs/stock/cache"),
    Reference(POSITIVE, WRAPPED, "full-short-DS30-0016-raw", "runs/stock/process/clocks", "runs/stock/cache/before", "runs/stock/process/exit_code"),
    # Cross-check actual repeated citations against the canonical launch rows.
    Reference(POSITIVE, PRIVATE, "combined-successor-original", "cases/DS30-0016/installed"),
    Reference(WITHHOLD, PRIVATE, "combined-successor-original", "cases/DS30-0107/installed"),
    Reference(POSITIVE, CACHED, "raw-0016-best", "prior/stock/clock"),
    Reference(WITHHOLD, PRIVATE, "adaptive-withhold-0107", "pair/historical/installed"),
)


def read(measurements, file):
    name = file if file.endswith(".json") else f"{file}.json.gz"
    data = (measurements / name).read_bytes()
    return json.loads(gzip.decompress(data) if name.endswith(".gz") else data), sha256(data).hexdigest(), name


def field(record, pointer):
    for name in pointer.split("/"):
        record = record[name]
    return record


def observations(measurements):
    identities = {}
    for ref in REFERENCES:
        doc, pin, name = read(measurements, ref.file)
        clock = field(doc, ref.clock)
        before = field(doc, ref.cache) if ref.cache else None
        exit_code = field(doc, ref.exit) if ref.exit else clock.get("exit_code", clock.get("status"))
        started = clock.get("started_unix_ns")
        if exit_code != 0 or any(not isfinite(clock[k]) or clock[k] <= 0 for k in ("elapsed_s", "cpu_s")):
            raise ValueError(f"Expected a successful complete stock worker in {name}")
        if before and (before["unavailable"] or before["observed_file_pages"] <= 0
                       or (before["cached_pages"] == before["observed_file_pages"]) != (ref.stratum in (PRIVATE, CACHED))):
            raise ValueError(f"Stock residency contradicts its enrolled stratum in {name}")
        source = dict(file=name, sha256=pin, clock=ref.clock)
        # These historical envelopes do not record child start. Their distinct
        # prelaunch cache sample provides an independently ordered launch witness.
        identity = (ref.case, started, None if started else before["ended_unix_ns"])
        row = {"case": ref.case, "stratum": ref.stratum, "start_unix_ns": started,
               "clock": {k: clock[k] for k in ("elapsed_s", "cpu_s", "input_blocks", "major_faults")}}
        if identity in identities:
            old = identities[identity]
            if any(old[key] != value for key, value in row.items()):
                raise ValueError(f"Conflicting duplicate stock process receipt in {name}")
            old["sources"].append(source)
        else:
            row["sources"] = [source]
            row["payload_residency"] = [before["cached_pages"], before["observed_file_pages"]]
            row["cache_check_end_unix_ns"] = before["ended_unix_ns"]
            identities[identity] = row
    return list(identities.values())


def ratios(stock, candidate):
    return (sum(stock) / sum(candidate),
            1 / median(c / b for c, b in zip(candidate, stock, strict=True)))


def candidate_prices(measurements, integrated_path):
    frame_positive, _, _ = read(measurements, "visit-frame-raw-0016-literal")
    frame_withhold, _, _ = read(measurements, "visit-frame-raw-0107")
    strict, _, _ = read(measurements, "strict-cairo-0107")
    data = integrated_path.read_bytes()
    if sha256(data).hexdigest() != INTEGRATED_PIN:
        raise ValueError("Integrated original candidate receipt changed")
    integrated = json.loads(gzip.decompress(data))
    prices = {}
    for order in ("positive_first", "withholding_first"):
        runs = [integrated["runs"][order][case]["result"]["document"] for case in (POSITIVE, WITHHOLD)]
        if any(not run["qualified"] or run["process"]["exit_code"] for run in runs):
            raise ValueError("Both integrated original candidate runs must be qualified")
        prices["integrated-original-" + order] = [run["process"]["elapsed_s"] for run in runs]
    prices["split-ready"] = [strict[key]["scopes"]["ready"][0] for key in ("positive_costs", "costs")]
    prices["split-first-use"] = [strict[key]["scopes"]["first"][0] for key in ("positive_costs", "costs")]
    prices["indexed-frame-child"] = [d["measured_children"]["frames"]["clock"]["elapsed_s"]
                                     for d in (frame_positive, frame_withhold)]
    return prices


def measure_sensitivity(combinations, candidates):
    budget = {str(gate): [min(b / gate for b in map(sum, combinations)),
                          max(b / gate for b in map(sum, combinations))] for gate in GATES}
    result = {}
    for label, candidate in candidates.items():
        rows = [ratios(stock, candidate) for stock in combinations]
        result[label] = dict(summed=[min(s for s, _ in rows), max(s for s, _ in rows)],
                             reciprocal_median=[min(m for _, m in rows), max(m for _, m in rows)],
                             gates={str(g): dict(summed=sum(s >= g for s, _ in rows),
                                                 reciprocal_median=sum(m >= g for _, m in rows),
                                                 both=sum(s >= g and m >= g for s, m in rows)) for g in GATES})
    return dict(combinations=len(combinations), summed_candidate_budget_s=budget, scores=result)


def audit(measurements, integrated_path):
    rows = observations(measurements)
    candidates = candidate_prices(measurements, integrated_path)
    scopes = {}
    for label, prefix in (("ancillary-fresh-pair", "stock-raw-repeat-"), ("prespecified-archived-pair", "history-risk-")):
        chosen = [next(row["clock"]["elapsed_s"] for row in rows if row["case"] == case
                       and row["sources"][0]["file"].startswith(prefix)
                       and not row["sources"][0]["file"].endswith("-failed.json.gz"))
                  for case in (POSITIVE, WITHHOLD)]
        scopes[label] = measure_sensitivity([chosen], candidates) | {"stock_elapsed_s": chosen}
    for label, allowed in (("private-tmpfs", (PRIVATE,)), ("all-fully-cached-original", (PRIVATE, CACHED))):
        per_case = [[r["clock"]["elapsed_s"] for r in rows if r["case"] == c and r["stratum"] in allowed]
                    for c in (POSITIVE, WITHHOLD)]
        scopes[label] = measure_sensitivity(list(product(*per_case)), candidates)
    return dict(cases=[POSITIVE, WITHHOLD], observations=rows, candidate_elapsed_s=candidates, sensitivity=scopes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--measurements", type=Path, default=MEASUREMENTS)
    parser.add_argument("--integrated", type=Path)
    args = parser.parse_args()
    data = audit(args.measurements, args.integrated or args.measurements / "integrated-original.json.gz")
    print(json.dumps(data, indent=2, sort_keys=True, allow_nan=False))
