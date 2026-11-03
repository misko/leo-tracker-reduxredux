"""Pre-RF-only age coverage experiment, separate from RF localization."""

import argparse
import time
from pathlib import Path
from ds23_age_covered_phase_prior import transition,qualify
from probe_ds23_history_calibrated_phase import HISTORY
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/"reports/2026_10_19_algo03_age_covered_phase_prior"


def run(case):
    began=time.monotonic();OUT.mkdir(exist_ok=True);path=OUT/(case+".json")
    if path.exists():raise FileExistsError("preserve causal qualification")
    raw_path=HISTORY/(case+".json");forecast_path=HISTORY/(case+"_forecast.json")
    history=read(raw_path);forecast=read(forecast_path)
    if forecast["history_sha256"]!=sha(raw_path):raise ValueError("history digest mismatch")
    cutoff=history["cutoff_utc_ns"];rows=[];triplets=0
    for number,versions in history["past_versions"].items():
        if any(v["epoch"]>cutoff or v["collected_utc_ns"]>cutoff for v in versions):
            raise ValueError("post-scan elements forbidden")
        for k in range(2,len(versions)):
            candidates=transition(*versions[k-2:k+1],cutoff)
            if candidates:triplets+=1
            rows.extend(dict(norad=int(number),triplet_index=triplets,**r) for r in candidates)
    selection=qualify(rows,forecast["temporal_split_boundary_ns"],forecast["prefix_distribution"],forecast["all_past_distribution"])
    write(path,dict(case=case,selection=selection,transitions=rows,triplets=triplets,
        no_RF_GPS_or_post_scan_TLE_used=True,no_current_satellite_preselection=True,
        retrospective_TLE_labels_are_proxies_not_orbit_truth=True,
        label_can_be_back_propagated_before_its_own_epoch_but_all_label_versions_precede_actual_RF_cutoff=True,
        shrinkage_tail_and_mean_clipping_preserved=True,
        causal_history_sha256=sha(raw_path),causal_forecast_sha256=sha(forecast_path),
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/"tools/ds23_age_covered_phase_prior.py"),
        seconds=time.monotonic()-began))
    print(case,selection,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--case",required=True)
    run(parser.parse_args().case)
