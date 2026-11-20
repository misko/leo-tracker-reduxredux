"""Replay the two earlier compact estimators and import completed v5 r0 endpoints."""

import hashlib
import json
from pathlib import Path
import time

import numpy as np

import bench
import cold_replay as cold
import winner_to_fix


def selected_panel(members):
    rows = sorted((r for r in members if r["availability"] == "available"),
                  key=lambda row: int(row["dataset_label"].split("-")[1]))
    labels = []
    for index in range(4):
        block = rows[index * len(rows) // 4 : (index + 1) * len(rows) // 4]
        for edge in ("lower", "upper"):
            subset = [r["dataset_label"] for r in block if r["recording_id"].endswith(edge)]
            labels.append(min(subset, key=lambda label: hashlib.sha256(
                ("sol62-small-v1/" + label).encode()).digest()))
    return sorted(labels)


def verified_input(path, digest):
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != digest.removeprefix("sha256:"):
        raise ValueError(f"Content mismatch for {path}")
    return json.loads(raw)


def compact_arms(doc, bank):
    descriptors = cold.descriptors(doc, bank)
    if descriptors is None:
        return {key: {"status": "abstain", "reason": "no curvature"}
                for key in ("c0", "fitted_c")}
    bias = cold.bias_vote(descriptors)
    _, xy, candidates, cost = cold.grid_vote(descriptors, bias)
    retained = np.flatnonzero(cost < 12.)
    arms = {}
    for key in ("c0", "fitted_c"):
        fit = cold.solve(descriptors, retained, candidates, bias, xy, fitted_c=key == "fitted_c")
        if fit["status"] == "estimate":
            fit["latlon"] = bench.latlon(fit["xy"])
        arms[key] = fit
    return arms


def v5_result(case):
    directory = cold.WORK / "results" / (case + "-r0")
    execution = cold.read(directory / "baseline-execution.json")
    path = directory / "baseline" / "worker-result.json"
    arms = {}
    status = execution["status"]
    if status == "complete":
        report = cold.read(path)
        for key, arm in report["arms"].items():
            arms[key] = dict(status="estimate", latlon=arm["endpoint_latlon"],
                             rms_hz=arm["residual_rms_hz"], tracks=arm["tracks"])
    else:
        arms = {key: dict(status=status) for key in ("c0", "fitted_c")}
    return dict(case=case, status=status, arms=arms, wall_s=execution["process"]["wall_seconds"])


def main():
    science = cold.read(cold.WORK / "plans/science.json")
    members = science["cohorts"]["DS26"]["members"]
    if selected_panel(members) != bench.CASES:
        raise ValueError("Panel no longer matches the declared sampling procedure")
    by_case = {r["dataset_label"]: r for r in members}
    controls = {"v5_r0": [], "graph_compact": [], "stream_compact": []}
    receipts = []
    for case in bench.CASES:
        member = by_case[case]
        graph_receipt = cold.read(cold.GRAPHS / (case + "-receipt.json"))
        graph = verified_input(cold.GRAPHS / (case + ".json"), graph_receipt["output_sha256"])
        native = verified_input(cold.INPUT / case / "native.json", member["input_sha256"])
        winners, metadata, half_probe = winner_to_fix.winners(native)
        winners = [r for r in winners if r[4] + half_probe <= metadata["duration_s"] + 1e-8]
        if metadata["causal_cutoff_utc_ns"] != graph["metadata"]["causal_cutoff_utc_ns"]:
            raise ValueError(f"Mismatched observation times for {case}")
        bank, sky = cold.build_bank(case, metadata, check_approximation=False)
        for method in ("graph_compact", "stream_compact"):
            begin = time.perf_counter()
            doc = graph if method == "graph_compact" else winner_to_fix.track_document(winners)[0]
            arms = compact_arms(doc, bank)
            controls[method].append(dict(case=case, arms=arms, wall_s=time.perf_counter()-begin))
        controls["v5_r0"].append(v5_result(case))
        receipts.append(dict(case=case, native_sha256=member["input_sha256"],
                             graph_sha256=graph_receipt["output_sha256"], winner_count=len(winners),
                             snapshot=sky["snapshot"], regional_candidates=sky["regional"]))
    result = dict(
        controls=controls, receipts=receipts,
        timing_scope=dict(v5_r0="Recorded complete-worker wall time, includes scientific evidence and figures.",
                          graph_compact="Prepared file and orbit table in memory through both numerical arms.",
                          stream_compact="Chronological detector winners and orbit table in memory through both arms."))
    (bench.ROOT / "controls.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")


if __name__ == "__main__":
    main()
