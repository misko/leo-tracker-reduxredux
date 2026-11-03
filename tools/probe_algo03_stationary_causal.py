"""Conditional multi-scan RF replay, separate from single-scan ALGO03.

Only same-declared-station RF positions ending before the current cutoff,
plus the current scan's own qualified RF position, enter its estimate.
No evaluation coordinate or pose coordinate is read by inference.
"""

import argparse
from pathlib import Path
from ds23_stationary_consensus import causal_estimates
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/"reports/2026_10_19_algo03_stationary_causal_v3"
SOURCE=ROOT/"reports/2026_10_19_algo02_ds23_full"


def run():
    OUT.mkdir(exist_ok=True);path=OUT/"inference.json"
    if path.exists():raise FileExistsError("preserve causal replay")
    sample=read(SOURCE/"sample.json")
    protocol=dict(cases=[m["dataset_label"] for m in sample["selected"]],
        methods=["mean","spatial_median"],selection="Both fixed estimators reported; no GPS-based selection",
        declared_stationarity_is_an_explicit_research_assumption=True,
        operator_roof_authority_supports_but_does_not_measure_stationarity=True,
        not_a_single_scan_ALGO03_candidate=True,no_reference_or_pose_coordinates_enter_inference=True,
        prior_recording_last_observation_must_precede_current_cutoff=True,
        original_ALGO02_failures_remain_failures_of_fresh_RF_localization=True,
        history_only_outputs_are_explicitly_separate=True,
        no_runtime_deadline_or_instant_real_time_availability_claim=True,
        observation_end_uses_all_GLRT_midpoints_plus_10ms_half_probe=True,
        sample_sha256=sha(SOURCE/"sample.json"),source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/"tools/ds23_stationary_consensus.py"))
    write(OUT/"protocol.json",protocol);records={a:[] for a in ("c0","fitted_c")};receipts=[]
    for member in sample["selected"]:
        case=member["dataset_label"];directory=SOURCE/case
        path=directory/"algo02_result.json";result=read(path) if path.exists() else None
        receipt=read(directory/"receipt.json") if (directory/"receipt.json").exists() else None
        cutoff=receipt["cutoff_utc_ns"] if receipt else member["captured_utc_ns"]
        end=None
        if result and result["status"]=="accepted":
            if result["GPS_used"] or result["future_TLE_used"]:raise ValueError("invalid RF inference provenance")
            observations=read(directory/"observations.json")
            end=receipt["origin_utc_ns"]+int((max(o["time_s"] for o in observations)+.01)*1e9)
        receipts.append(dict(case=case,status=result["status"] if result else "no_result",
            result_sha256=sha(path) if path.exists() else None,original_RF_position_available=end is not None,
            observation_timing_sha256=sha(directory/"observations.json") if end is not None else None,
            cutoff_timing_is_qualified=receipt is not None))
        for arm in records:
            position=result["policy_arms"][arm]["endpoint_east_north_km"] if end is not None else None
            records[arm].append(dict(case=case,cutoff_utc_ns=cutoff,last_observation_utc_ns=end,
                stationary_segment="radio_pluto_5d4d_declared_roof_20261001",position=position))
    output={method:{a:causal_estimates(rows,method,declared_stationary=True) for a,rows in records.items()}
            for method in protocol["methods"]}
    write(OUT/"inference.json",dict(results=output,records=records,input_receipts=receipts,
        protocol_sha256=sha(OUT/"protocol.json"),no_GPS_or_pose_coordinates_read=True))
    print("conditional causal replay completed",len(receipts),"records",flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--assume-stationary",action="store_true")
    args=parser.parse_args()
    if not args.assume_stationary:parser.error("explicit --assume-stationary research assumption required")
    run()
