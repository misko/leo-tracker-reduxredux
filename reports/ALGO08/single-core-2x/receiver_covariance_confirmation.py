"""Run the frozen primary covariance threshold on two contiguous physical passages."""

import argparse
import gzip
import json
import sys
from contextlib import ExitStack
from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.contracts.fast_scan_native import FastScanPolicyV2
from leo.scanner.fast_scan_analysis import valid_window_support
from leo.storage.fast_scan import FastSegmentSource
from tools.algo08_scan import PINS
from tools.pipeline_eval.variants.carrier_continuation import Continuation
from tools.pipeline_eval.variants.experimental.receiver_benchmark import Receiver, digest
from tools.pipeline_eval.variants.experimental.receiver_covariance_trial import (
    ProbeReceiver,
    continuation,
    factor_bytes,
    pilot_assets,
    trial,
)
from tools.pipeline_eval.variants.experimental.receiver_ingress import compressed_input_buffer

ARMS = ("frozen", "control", "primary")


def check_plan(plan, triage):
    if tuple(plan["arms"]) != ARMS or plan["repeats"] != 2:
        raise ValueError("Confirmation uses only the three declared primary arms")
    limits = {edge: value["limits"] for edge, value in triage["calibration"].items()}
    if plan["limits"] != limits:
        raise ValueError("The confirmation changed its noise thresholds")
    if (plan["frozen_sha256"], plan["probe_sha256"]) != (triage["frozen"], triage["instrumented"]):
        raise ValueError("The confirmation changed its native receiver builds")
    schedules = [item["stop_sequence"] - item["start_sequence"] for item in plan["strata"]]
    if len(schedules) != 2 or min(schedules) <= 0 or sum(schedules) > 100:
        raise ValueError("Confirmation is bounded to two strata and 100 scheduled physical visits")


def read_stratum(stratum):
    manifest = Path(stratum["manifest"])
    start, stop = stratum["start_sequence"], stratum["stop_sequence"]
    offset = stratum["segment_global_start"]
    windows = FastSegmentSource(dict(path=str(manifest.parent),
                                     manifest_digest="sha256:" + stratum["manifest_sha256"]),
                                start_sequence=start, stop_sequence=stop)
    receivers = tuple(windows.receiver_ids)
    if receivers != (0, 1) or windows.reader.manifest.sample_rate_hz != 10_000_000:
        raise ValueError("Expected original stereo native-rate input")
    touched = [chunk for chunk in windows.reader.manifest.chunks
               if chunk.first_sequence < stop and chunk.first_sequence + chunk.window_count > start]
    if len(touched) != 1 or touched[0].index_sha256 != stratum["chunk_index_sha256"]:
        raise ValueError("The passage must stay within its declared sealed chunk")
    if not offset + start <= stratum["anchor_visit"] < offset + stop:
        raise ValueError("The declared capture anchor falls outside the passage")
    rows, excluded = [], []
    visits = range(offset + start, offset + stop)
    policy = FastScanPolicyV2()
    with compressed_input_buffer():
        for visit, window in zip(visits, windows.windows(), strict=True):
            acq, target = window.acquisition, window.target
            if acq["global_visit"] != visit:
                raise ValueError("The frozen capture is out of scheduled order")
            row = dict(case=stratum["case"], visit=visit, key=f"{stratum['case']}:{visit}",
                       edge=target["edge"], acquisition=acq, target=target, sha256=window.iq_sha256)
            if valid_window_support(acq, window.sample_rate_hz, window.samples.shape,
                                    receivers, policy):
                rows.append((row, window.samples))
            else:
                excluded.append(dict(visit=visit, sha256=window.iq_sha256))
    return rows, excluded


def fields(candidate):
    return tuple(candidate[name] for name in (
        "candidate_rank", "integer_epoch_sample", "fractional_epoch_offset_samples",
        "fractional_tracking_cfo_hz", "fractional_exact_score", "fractional_control_score",
    ))


def lane_key(row):
    return row["visit_index"], row["receiver_id"]


def link_publication(group, start, ledger, published):
    """Reuse only the prior sealed prefix to check selections against publication."""
    indices = {lane_key(row): row for row in ledger["rows"]}
    expected = {lane_key(row): row for row in published}
    contexts = {arm: Continuation() for arm in ARMS}
    for row in ledger["rows"]:
        if row["visit_index"] >= start:
            break
        factors = tuple(map(fields, row["candidates"]))
        for history in contexts.values():
            continuation(row, history, factors)
    results = {arm: [] for arm in ARMS}
    differences = []
    for row in group["rows"]:
        key = row["visit"], row["lane"]
        old = indices[key]
        if any(old[name] != value for name, value in row["probe"].items()):
            raise ValueError("Confirmed lanes differ from the saved publication clock or RF lane")
        if (tuple(map(factor_bytes, row["arms"]["frozen"]["factors"])) !=
                tuple(factor_bytes(fields(c)) for c in old["candidates"])):
            raise ValueError("Fresh frozen factors differ from the published lane ledger")
        selected = expected[key]["candidates"]
        if len(selected) > 1:
            raise ValueError("Expected a single linked continuation selection per lane")
        saved_factor = fields(selected[0]) if selected else None
        for arm, history in contexts.items():
            factor, votes = continuation(row["probe"], history, row["arms"][arm]["factors"])
            results[arm].append(dict(
                visit=row["visit"], lane=row["lane"], factor=factor, votes=votes,
            ))
            if factor_bytes(factor) != factor_bytes(saved_factor):
                if arm == "frozen":
                    raise ValueError("Frozen passage did not reproduce its published selection")
                differences.append(dict(arm=arm, visit=row["visit"], lane=row["lane"],
                                        publication=saved_factor, trial=factor))
    selections = {arm: sum(row["factor"] is not None for row in rows)
                  for arm, rows in results.items()}
    return dict(selected=selections, differences=differences,
                sha256={arm: canonical_digest(rows) for arm, rows in results.items()}, rows=results)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for arg in ("plan", "triage", "frozen", "probe", "assets", "ledger", "published"):
        parser.add_argument(arg, type=Path)
    args = parser.parse_args()
    raw_plan, raw_triage = args.plan.read_bytes(), args.triage.read_bytes()
    plan, triage = json.loads(raw_plan), json.loads(gzip.decompress(raw_triage))
    if digest(raw_triage) != plan["triage_receipt_sha256"]:
        raise ValueError("Original covariance receipt does not match the frozen plan")
    check_plan(plan, triage)
    for name in ("frozen", "probe"):
        if digest(getattr(args, name).read_bytes()) != plan[f"{name}_sha256"]:
            raise ValueError(f"The {name} binary changed")
    visited = {sha for group in triage["groups"].values() for _, sha in group["inputs"]["windows"]}
    calibration = {edge: dict(limits=value) for edge, value in plan["limits"].items()}
    groups = {}
    with ExitStack() as stack:
        stock, receivers = {}, {}
        for edge, pilot in pilot_assets(args.assets):
            name = f"{edge}.f32"
            if digest((args.assets / name).read_bytes()) != PINS[name]:
                raise ValueError("Released pilot asset changed")
            stock[edge] = Receiver(args.frozen, pilot)
            receivers[edge] = ProbeReceiver(args.probe, pilot)
            stack.callback(stock[edge].close)
            stack.callback(receivers[edge].close)
        for stratum in plan["strata"]:
            rows, excluded = read_stratum(stratum)
            accepted = {row["sha256"] for row, _ in rows}
            if not accepted or visited.intersection(accepted):
                raise ValueError("Confirmation waveforms overlap the original or another stratum")
            visited.update(accepted)
            result = trial(rows, stock, receivers, calibration, arms=ARMS)
            groups[stratum["case"]] = dict(plan=stratum, excluded=excluded, **result)
    full_ledger, full_publication = args.ledger.read_bytes(), args.published.read_bytes()
    ledger = json.loads(gzip.decompress(full_ledger))
    published = json.loads(full_publication)["source"]["probes"]
    if (digest(full_publication) != ledger["saved_detections_sha256"] or
            canonical_digest(published) != ledger["ordered_selected_sha256"] or
            ledger["detector_sha256"] != plan["frozen_sha256"]):
        raise ValueError("The saved ledger and its publication do not match")
    main_case = plan["strata"][0]
    first = main_case["segment_global_start"] + main_case["start_sequence"]
    linked = link_publication(groups[main_case["case"]], first, ledger, published)
    result = dict(plan_sha256=digest(raw_plan), limits=plan["limits"], groups=groups,
                  linked=dict(ledger_sha256=digest(full_ledger),
                              published_sha256=digest(full_publication), **linked))
    sys.stdout.buffer.write(gzip.compress(json.dumps(result, allow_nan=False).encode(), mtime=0))


if __name__ == "__main__":
    main()
