"""Evaluate shared phase-error priors without radio or evaluation GPS."""

import argparse
from pathlib import Path
from ds23_shared_phase_events import qualify
from probe_ds23_history_calibrated_phase import HISTORY
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/"reports/2026_10_19_algo03_shared_phase_events"


def run(case):
    OUT.mkdir(exist_ok=True);path=OUT/(case+".json")
    if path.exists():raise FileExistsError("preserve causal qualification")
    raw_path=HISTORY/(case+".json");forecast_path=HISTORY/(case+"_forecast.json")
    raw=read(raw_path);forecast=read(forecast_path)
    if forecast["history_sha256"]!=sha(raw_path):raise ValueError("history digest changed")
    cutoff=raw["cutoff_utc_ns"];mapping={}
    for number,versions in raw["past_versions"].items():
        if any(v["epoch"]>cutoff or v["collected_utc_ns"]>cutoff for v in versions):
            raise ValueError("post-scan elements forbidden")
        for k in range(2,len(versions)):
            a,b,c=versions[k-2:k+1]
            if not(a["epoch"]<b["epoch"]<c["epoch"]<=c["collected_utc_ns"] and
                   a["collected_utc_ns"]<=b["collected_utc_ns"]<=c["collected_utc_ns"]):continue
            key=(int(number),c["collected_utc_ns"])
            if key in mapping:raise ValueError("ambiguous history transition identity")
            mapping[key]=b["collected_utc_ns"]
    groups={}
    for row in forecast["transitions"]:
        groups.setdefault(mapping[row["norad"],row["validation_time_ns"]],[]).append(row)
    for rows in groups.values():
        if len({r["norad"] for r in rows})!=len(rows):raise ValueError("repeated satellite in publication event")
    selection=qualify(groups,forecast["temporal_split_boundary_ns"],forecast["prefix_distribution"],forecast["all_past_distribution"])
    write(path,dict(case=case,selection=selection,no_RF_GPS_or_post_scan_TLE_used=True,
        no_current_satellite_preselection=True,history_sha256=sha(raw_path),forecast_sha256=sha(forecast_path),
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/"tools/ds23_shared_phase_events.py"),
        future_updates_are_training_proxies_not_orbit_truth=True))
    print(case,selection.get("qualified"),selection.get("rho"),selection.get("validation_gain"),flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--case",required=True)
    run(parser.parse_args().case)
