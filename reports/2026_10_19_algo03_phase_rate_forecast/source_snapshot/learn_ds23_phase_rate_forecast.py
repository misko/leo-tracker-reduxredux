"""Qualify the phase-rate mean feature on all pre-RF causal candidate histories."""

import argparse
from pathlib import Path
from ds23_phase_rate_forecast import disagreement_rate, qualify
from probe_ds23_history_calibrated_phase import HISTORY
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha

OUT=ROOT/"reports/2026_10_19_algo03_phase_rate_forecast"


def run(case):
    OUT.mkdir(exist_ok=True)
    path=OUT/(case+".json")
    if path.exists():
        raise FileExistsError("preserve causal qualification")
    raw_path=HISTORY/(case+".json");forecast_path=HISTORY/(case+"_forecast.json")
    history=read(raw_path);forecast=read(forecast_path)
    assert forecast["history_sha256"]==sha(raw_path)
    cutoff=history["cutoff_utc_ns"]
    assert all(v["epoch"]<=cutoff and v["collected_utc_ns"]<=cutoff
               for versions in history["past_versions"].values() for v in versions)
    by_transition={}
    for number,versions in history["past_versions"].items():
        for k in range(2,len(versions)):
            a,b,c=versions[k-2:k+1]
            if not(a["epoch"]<b["epoch"]<c["epoch"]<=c["collected_utc_ns"] and
                   a["collected_utc_ns"]<=b["collected_utc_ns"]<=c["collected_utc_ns"]):
                continue
            by_transition[int(number),c["collected_utc_ns"]]=(a,b)
    rows=[]
    for old in forecast["transitions"]:
        a,b=by_transition[old["norad"],old["validation_time_ns"]]
        rate=disagreement_rate(tuple(a["lines"]),tuple(b["lines"]),old["validation_time_ns"])
        rows.append(dict(old,rate_feature_s=-old["age_s"]*rate,phase_disagreement_rate_s_s=rate))
    selection=qualify(rows,forecast["temporal_split_boundary_ns"],forecast["prefix_distribution"],forecast["all_past_distribution"])
    write(path,dict(case=case,selection=selection,transitions=rows,
        no_RF_GPS_or_post_scan_TLE_used=True,latest_elements_and_phase_prior_scales_unchanged=True,
        no_current_satellite_preselection=True,cutoff_utc_ns=cutoff,source_sha256=sha(Path(__file__)),
        helper_sha256=sha(ROOT/"tools/ds23_phase_rate_forecast.py"),
        causal_history_sha256=sha(raw_path),causal_forecast_sha256=sha(forecast_path),
        later_TLE_updates_are_prediction_proxies_not_orbit_truth=True))
    print(case,"phase-rate forecast",selection["qualified"],"beta",selection["beta"],
          "validation gain",selection["validation_gain"],flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case")
    args=parser.parse_args()
    if args.case:
        run(args.case)
    else:
        for member in read(SOURCE/"sample.json")["selected"]:
            run(member["dataset_label"])
