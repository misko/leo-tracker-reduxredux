"""Stationary-site diagnostic: shrink only within current RF/gate support.

History is RF-derived and chronological. It is not a single-scan algorithm,
and stationarity has not been independently established. The fixed six-unit
RF budget is an engineering loss tolerance, not a calibrated confidence bound.
"""

from pathlib import Path
import numpy as np
from probe_ds23_height import context
from probe_ds23_history_gate_replay import at_fixed_position
from probe_ds23_predictive_linear import OUT as GAUSSIAN
from probe_ds23_robust_predictive_linear import OUT as PREVIOUS
from probe_ds23_stationary_history_diagnostic import spatial_median
from run_algo01_ds23_sample import ROOT, OUT as SOURCE, read, write, sha

OUT=ROOT/"reports/2026_10_19_algo03_rf_supported_history"


def select_supported(trials, incumbent_score, maximum_increase=6.):
    passing=[t for t in trials if all(t["arms"][a]["compatible"] for a in ("c0","fitted_c")) and
        t["arms"]["c0"]["negative_twice_elbo"] <= incumbent_score+maximum_increase]
    return max(passing,key=lambda t:t["fraction"]) if passing else None


def run():
    OUT.mkdir(exist_ok=True)
    if (OUT/"result.json").exists():
        raise FileExistsError("preserve completed diagnostic")
    members=sorted(read(SOURCE/"sample.json")["selected"],key=lambda m:m["captured_utc_ns"])
    cache={r["case"]:r for r in read(PREVIOUS/"history_gate_replay.json")["records"]}
    write(OUT/"protocol.json",dict(cases=[r["dataset_label"] for r in members],
        fractions=[1.,.75,.5,.25,0.],maximum_c0_normalized_RF_loss_increase=6.,
        loss_budget_is_engineering_not_a_calibrated_confidence_level=True,
        same_fraction_both_c_arms_and_both_must_pass_current_gates=True,
        history_center="spatial median of current and all earlier independent c0 RF positions",
        fewer_than_three_scans_keeps_individual_position=True,
        current_curve_masks_labels_aliases_and_measurements_preserved=True,
        no_GPS_or_future_RF_in_history_or_selection=True,
        stationary_site_assumption_unverified_no_motion_model=True,
        not_single_scan_ALGO02_or_established_ALGO03=True,
        original20_development_scans_not_all_DS23=True,
        source_sha256=sha(Path(__file__)),cached_individual_replay_sha256=sha(PREVIOUS/"history_gate_replay.json")))
    positions=[]
    results=[]
    for member in members:
        case=member["dataset_label"]
        data=read(GAUSSIAN/(case+".json"))
        original=data["results"]["all_linear"]
        pair=original["policy_arms"]
        assert cache[case]["gaussian_input_sha256"]==sha(GAUSSIAN/(case+".json"))
        null=cache[case]["controls"]["individual_null"]
        assert null["paired_valid"]
        positions.append(pair["c0"]["endpoint_east_north_km"])
        center,_=spatial_median(positions)
        scan,node,keep,powers,means,model,_,_=context(case,"archived")
        entries=original["entries"] if original["paired_valid"] else []
        trials=[dict(fraction=0.,arms=null["arms"])]
        if len(positions)>=3:
            for fraction in (1.,.75,.5,.25):
                arms={}
                for arm in ("c0","fitted_c"):
                    start=np.array(pair[arm]["endpoint_east_north_km"])
                    point=(1-fraction)*start+fraction*center
                    arms[arm]=at_fixed_position(scan,node,keep,powers,means,model,arm,entries,point)
                trials.append(dict(fraction=fraction,arms=arms))
        selected=select_supported(trials,null["arms"]["c0"]["negative_twice_elbo"])
        assert selected is not None
        results.append(dict(case=case,scans_used=len(positions),latest_RF_utc_ns=member["captured_utc_ns"],
            center_east_north_km=center,selected_fraction=selected["fraction"],
            policy_arms=selected["arms"],incumbent_arms=pair,trials=trials,
            gaussian_sha256=sha(GAUSSIAN/(case+".json"))))
        write(OUT/"partial.json",dict(records=results))
        print(case,"RF-supported fraction",selected["fraction"],"history",len(positions),flush=True)
    write(OUT/"result.json",dict(records=results,no_GPS_used=True,stationarity_unverified=True,
        no_current_observation_removed_and_no_gate_relaxation=True,
        every_c_arm_receives_same_history_center_fraction_and_loss_budget=True,
        source_sha256=sha(Path(__file__))))


if __name__=="__main__":
    run()
