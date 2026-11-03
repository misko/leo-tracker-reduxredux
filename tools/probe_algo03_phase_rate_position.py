"""RF test of an externally qualified causal phase-disagreement-rate mean.

Existing ALGO02 development evidence stays fixed. No GPS, satellite changes,
new observations, or gate trimming enter this paired mechanism test.
"""

import argparse
import time
from pathlib import Path
import numpy as np
from sgp4.alpha5 import from_alpha5
from algo02_scan import pair_passes
from ds23_phase_rate_forecast import adjust_scan_means,disagreement_rate
from investigate_algo01_ds23_0217 import problem
from investigate_ds23_adaptive_failures import phase_widths
from probe_ds23_height import context
from probe_ds23_history_calibrated_phase import refit as curved_refit
from probe_ds23_predictive_linear import OUT as INCUMBENT,refit as linear_refit
from run_algo01_ds23_sample import ROOT,read,write,sha

OUT=ROOT/"reports/2026_10_19_algo03_phase_rate_position"
PRIOR=ROOT/"reports/2026_10_19_algo03_phase_rate_forecast_v2"


def previous_lines(text):
    lines=[line for line in text.splitlines() if line.startswith(("1 ","2 "))]
    if len(lines)%2:raise ValueError("paired previous TLE lines required")
    result={}
    for k in range(0,len(lines),2):
        a,b=lines[k:k+2]
        if not a.startswith("1 ") or not b.startswith("2 ") or a[2:7]!=b[2:7]:
            raise ValueError("paired previous TLE identity required")
        number=from_alpha5(a[2:7])
        if number in result:raise ValueError("unique previous TLE identity required")
        result[number]=(a,b)
    return result


def run(case,null=False):
    OUT.mkdir(exist_ok=True);path=OUT/(case+("_null" if null else "")+".json")
    if path.exists():raise FileExistsError("preserve scientific outputs")
    began=time.monotonic();prior=read(PRIOR/(case+".json"))
    source=read(INCUMBENT/(case+".json"));old=source["results"]["all_linear"]["policy_arms"]
    if not null and not prior["selection"]["qualified"]:
        write(path,dict(case=case,prior_qualified=False,policy_arms=old,no_inference_needed=True))
        return
    scan,node,keep,powers,ordinary,model,_,_=context(case,"archived")
    base=problem(scan,node,"c0",keep);_,receipts=phase_widths(scan,base.labels)
    previous=previous_lines(scan.previous_tle_path.read_text())
    target=scan.receipt["origin_utc_ns"]+150_000_000_000
    rates=[disagreement_rate(previous[r["norad"]],tuple(scan.elements[str(r["norad"])]["lines"]),target)
           if r["norad"] in previous else 0. for r in receipts]
    beta=0. if null else prior["selection"]["beta"]
    means=adjust_scan_means(ordinary,receipts,rates,beta)
    entries=source["results"]["all_linear"]["entries"]
    curved={a:curved_refit(scan,node,keep,a,powers,means,model["multiplier"],model["nu"])
            for a in ("c0","fitted_c")}
    linear={a:linear_refit(scan,node,keep,powers,means,model,a,entries) for a in ("c0","fitted_c")}
    cv=pair_passes(curved);lv=pair_passes(linear,include_linear=True)
    policy=linear if cv and lv else (curved if cv else old)
    write(path,dict(case=case,null_control=null,prior_qualified=True,beta=beta,
        curved_arms=curved,linear_arms=linear,curved_paired_valid=cv,linear_paired_valid=lv,
        policy_arms=policy,incumbent_arms=old,mask=keep,powers=powers,entries=entries,
        phase_mean_before_s=ordinary,phase_mean_after_s=means,phase_rate_receipts=receipts,
        phase_disagreement_rates_s_s=rates,original_points_labels_aliases_and_priors_preserved=True,
        no_GPS_or_post_scan_TLE_used=True,no_linear_to_calibration_feedback=True,
        same_observations_c_priors_and_5x48_budgets=True,
        prior_sha256=sha(PRIOR/(case+".json")),incumbent_sha256=sha(INCUMBENT/(case+".json")),
        source_sha256=sha(Path(__file__)),helper_sha256=sha(ROOT/"tools/ds23_phase_rate_forecast.py"),
        previous_TLE_sha256=sha(scan.previous_tle_path),seconds=time.monotonic()-began))
    print(case,"beta",beta,"C",cv,"L",lv,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument("--case",required=True)
    parser.add_argument("--null-control",action="store_true");args=parser.parse_args()
    run(args.case,args.null_control)
