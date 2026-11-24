"""Evaluate a frozen candidate-only frequency confidence law on saved native pairs."""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import groupby
import json
from math import isfinite, log, sqrt
from pathlib import Path
from random import Random
from statistics import fmean

import signed_cfo_time_readout as authority
from signed_cfo_time import SAMPLE_RATE, difference


DEVELOPMENT = ("DS30-0016", "DS30-0049")
HELD = ("DS30-0019", "DS30-0274", "DS30-0220")
PROTOCOL = "f5ba2e4f0"
STOCK_0016 = "e852ffcf8b887e7cab66bcb5f8ad4911caaaa9398264d3b5f351b02862b17850"


@dataclass(frozen=True, slots=True)
class Positive:
    variance: float
    status: str
    discrepancy2: float | None
    stream: tuple
    block: int


def relative_variance(factor, aperture_ms):
    m = factor["fractional_margin"]
    if not isfinite(m) or m <= 0 or aperture_ms not in (8, 20):
        raise ValueError("A finite positive native margin and enrolled aperture are required")
    return (20 / aperture_ms)**2 * (.025 / m)


def input_pair(case):
    authority.CASES["DS30-0220"] = 1
    sparse, _, offer = authority.candidate(case)
    if case == "DS30-0016":
        archive = authority.document(authority.HERE/"measurements/stock-raw-repeat-0016.json.gz", STOCK_0016)
        folder, expected = authority.WEAK_STOCK, archive["stock"]["digest"]
        stock_offer = archive["admission"]["request"]["offer_sha256"]
    else:
        folder, archive = authority.campaign(case, "installed")
        expected, stock_offer = archive["native_sha256"], archive["raw_identity"]["region_sha256"]
    stock = authority.read_native(folder, expected)
    if (stock_offer.removeprefix("sha256:") != offer.removeprefix("sha256:")
            or stock["provenance"]["detector_sha256"] != "sha256:"+authority.FULL):
        raise ValueError("The installed full receiver and matched original offer are required")
    return stock, sparse, offer


def compare(stock, sparse, offer):
    left, right = (authority.opportunities(native) for native in (stock, sparse))
    authority.bind_pair(stock, sparse, left, right)
    anchor = sparse["clock_anchor"]["sample_counter"]
    counts = defaultdict(Counter)
    radios = defaultdict(Counter)
    schema = set()
    rows = []
    for ident, short in right.items():
        full_factor, short_factor = left[ident]["factor"], short["factor"]
        name = "short" if short["short"] else "anchor"
        counter = counts[name]
        counter["issued"] += 1
        delta2 = None
        if full_factor is not None and short_factor is not None:
            delta, epoch, match, relaxed = difference(full_factor, short_factor)
            status = "same_atom" if match else "disagreement"
            counter.update({"relaxed_atom": relaxed, "exact_factor": full_factor == short_factor,
                            "frequency_disagreement": abs(delta) > 250,
                            "epoch_disagreement": abs(epoch) > 2})
            if match:
                delta2 = delta * delta
        else:
            status = "sparse_only" if short_factor else "installed_only" if full_factor else "both_empty"
        counter[status] += 1
        if name == "short":
            radios[short["radio"]][status] += 1
            if short_factor is not None:
                schema.update(short_factor)
                row = short["row"]
                stream = tuple(row[k] for k in ("receiver_id", "edge", "channel", "actual_rf_hz"))
                rows.append(Positive(relative_variance(short_factor, 8), status, delta2, stream,
                                     (short["counter"]-anchor)//(10*SAMPLE_RATE)))
    input_authority = dict(offer_sha256=offer, raw=sparse["source"]["raw_recording_authority_digest"],
                           issued_visits=sparse["provenance"]["window_count"],
                           approved_visits=sparse["provenance"]["processed_windows"],
                           excluded_visits=sparse["provenance"]["invalid_capture"],
                           candidate_native_sha256=authority.canonical(sparse), stock_native_sha256=authority.canonical(stock),
                           candidate_factor_schema=sorted(schema))
    return rows, dict(counts=dict(counts), radios=dict(radios), input=input_authority)


def learn(rows):
    good = [row for row in rows if row.status == "same_atom"]
    rank = sorted(row.variance for row in good)
    if len(rank) < 20:
        raise ValueError("At least twenty development matches are required for a 95% gate")
    # Threshold is inclusive. A boundary tie cannot consume extra good lanes.
    base = rank[len(rank) - len(rank)//20 - 1]
    next_ = next((value for value in rank if value > base), None)
    if next_ is None:
        raise ValueError("The development margins do not admit a nontrivial fixed threshold")
    return dict(scale_hz2=fmean(r.discrepancy2/r.variance for r in good),
                constant_hz2=fmean(r.discrepancy2 for r in good), reject_at_variance=next_, matches=len(rank))


def auc_tally(rows):
    good, bad, concordant = 0, 0, 0.
    pairs = sorted((row for row in rows if row.status != "sparse_only"), key=lambda row: row.variance)
    for _value, tied in groupby(pairs, key=lambda row: row.variance):
        count = Counter(row.status for row in tied)
        g, b = count["same_atom"], count["disagreement"]
        concordant += b * (good + g/2)
        good += g
        bad += b
    return concordant, good * bad


def ratio(a, b):
    return a / b if b else None


def stratified_random(streams, model):
    vals = ("same_atom", "disagreement", "sparse_only", "discrepancy2")
    random = {v: [0., 0.] for v in vals}
    for rows in streams.values():
        n = len(rows)
        k = sum(row.variance >= model["reject_at_variance"] for row in rows)
        for v in vals:
            sample = [(row.discrepancy2 or 0.) if v == "discrepancy2" else (row.status == v) for row in rows]
            mean = fmean(sample)
            random[v][0] += k * mean
            if n > 1:
                random[v][1] += k * (n-k) / (n-1) * fmean((a-mean)**2 for a in sample)
    return {name: dict(expectation=pair[0], equal_budget_sd=sqrt(pair[1])) for name,pair in random.items()}


def interval(values):
    seq = sorted(value for value in values if value is not None)
    return [seq[int((len(seq)-1)*p)] for p in (.025,.975)] if seq else None


def block_intervals(blocks):
    groups = list(blocks.values())
    if len(groups) < 4:
        return None
    random = Random(4054)
    estimates = []
    for _ in range(1000):
        n, reject, mismatch, flagged, loss, total, bought = map(sum, zip(*random.choices(groups, k=len(groups))))
        estimates.append((ratio(n-reject, n), ratio(flagged, mismatch), ratio(loss, n), ratio(bought, total)))
    return dict(zip(("specificity", "disagreement_recall", "nll_improvement", "squared_disagreement_capture"),
                    map(interval, zip(*estimates)), strict=True))


def score(rows, model):
    streams = defaultdict(list)
    blocks = defaultdict(lambda: [0]*7)
    flag = Counter()
    squared, standardized, coverage = [], [], 0
    for row in rows:
        streams[row.stream].append(row)
        rejected = row.variance >= model["reject_at_variance"]
        flag[row.status] += rejected
        state = blocks[row.block]
        if row.status == "disagreement":
            state[2] += 1
            state[3] += rejected
        if row.status == "same_atom":
            var, const, err = model["scale_hz2"]*row.variance, model["constant_hz2"], row.discrepancy2
            gain = 0.5 * (log(const/var) + err/const - err/var)
            state[0] += 1
            state[1] += rejected
            state[4] += gain
            state[5] += err
            state[6] += err * rejected
            standardized.append(err/var)
            coverage += err <= 1.96**2 * var
            squared.append((row.variance, err))
    totals = Counter(row.status for row in rows)
    n, bad = totals["same_atom"], totals["disagreement"]
    losses = [block[4] for block in blocks.values()]
    sum_sq = sum(row[5] for row in blocks.values())
    paid_sq = sum(row[6] for row in blocks.values())
    ranked = sorted(squared, reverse=True)
    bins = [ranked[i*n//4:(i+1)*n//4] for i in range(4)]
    control = stratified_random(streams, model)
    wins, comparisons = auc_tally(rows)
    stratified = list(map(auc_tally, streams.values()))
    by_radio = {str(i): ratio(*auc_tally([row for row in rows if row.stream[0] == i])) for i in (0,1)}
    return dict(
        short_positive=len(rows), flagged=dict(flag), flagged_lanes=sum(flag.values()),
        specificity=ratio(n-flag["same_atom"], n), disagreement_recall=ratio(flag["disagreement"], bad),
        disagreement_auc=ratio(wins, comparisons), within_stream_auc=ratio(*map(sum, zip(*stratified))) if streams else None,
        per_radio_auc=by_radio, rms_hz=sqrt(sum_sq/n) if n else None,
        normalized_rms=sqrt(fmean(standardized)) if n else None, normal_95_coverage=ratio(coverage, n),
        nll_improvement=ratio(sum(losses), n),
        squared_disagreement_capture=ratio(paid_sq, sum_sq),
        random=dict(controls=control,
                    discrepancy2_capture=ratio(control["discrepancy2"]["expectation"], sum_sq),
                    specificity=1-control["same_atom"]["expectation"]/n if n else None,
                    disagreement_recall=ratio(control["disagreement"]["expectation"], bad)),
        ten_second_blocks=len(blocks), block_95=block_intervals(blocks),
        quartiles=[dict(count=len(q), rms_hz=sqrt(fmean(err for _,err in q)) if q else None) for q in bins])


def run():
    results, rows = {}, {}

    def enroll(case):
        try:
            inputs = input_pair(case)
        except (OSError, ValueError, KeyError) as exc:
            results[case] = {"admission_failure": str(exc)}
        else:
            rows[case], results[case] = compare(*inputs)

    for case in DEVELOPMENT:
        enroll(case)
    if any(case not in rows for case in DEVELOPMENT):
        raise ValueError(f"Development enrollment failed: {results}")
    model = learn([measurement for case in DEVELOPMENT for measurement in rows[case]])
    for case in HELD:
        enroll(case)
    for case, metrics in results.items():
        if case not in rows:
            continue
        row = metrics["counts"]["short"]
        stock_positive = row["same_atom"]+row["disagreement"]+row["installed_only"]
        metrics["ceiling"] = dict(stock_positive=stock_positive,
                                  candidate_detection_presence=ratio(stock_positive-row["installed_only"], stock_positive),
                                  stock_reference_atom=ratio(row["same_atom"], stock_positive))
        metrics["precision"] = scored = score(rows[case], model)
        interval_ = scored["block_95"]
        metrics["passes"] = bool(interval_ and interval_["nll_improvement"] and scored["specificity"] >= .90
                                 and (scored["within_stream_auc"] or 0.) >= .60
                                 and interval_["nll_improvement"][0] > 0)
    return dict(protocol=PROTOCOL, formula="(20 / aperture)^2 * .025 / margin", model=model, cases=results,
                development=DEVELOPMENT, held=HELD, eligible_held=[case for case in HELD if case in rows],
                qualifies=all(results[case].get("passes") for case in HELD), waveform_reads=0, solver_runs=0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = run()
    with args.output.open("x") as stream:
        json.dump(result, stream, sort_keys=True, indent=2, allow_nan=False)
        stream.write("\n")
