"""Evaluation-only local checkpoint; publication requires generalization."""

import numpy as np
from pathlib import Path
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha
from report_algo01_ds23_sample import position_error


def metrics(records):
    result={}
    for arm in ("c0","fitted_c"):
        old=np.array([position_error(r["incumbent_arms"][arm]["endpoint_latlon"]) for r in records])
        new=np.array([position_error(r["policy_arms"][arm]["endpoint_latlon"]) for r in records])
        result[arm]=dict(count=len(records),incumbent_mean_km=float(old.mean()),incumbent_median_km=float(np.median(old)),
            trial_mean_km=float(new.mean()),trial_median_km=float(np.median(new)),
            improved=int(sum(new<old-1e-8)),regressed=int(sum(new>old+1e-8)),unchanged=int(sum(abs(new-old)<=1e-8)))
    return result


def run():
    cases=[m["dataset_label"] for m in read(SOURCE/"sample.json")["selected"]]
    path=ROOT/"reports/2026_10_19_algo03_joint_orbit_prior"
    execution=read(path/"execution.json")
    records=[]
    missing=[]
    qualified=0
    for case in cases:
        result=path/(case+"_position.json")
        prior=path/(case+"_prior.json")
        if not result.exists():
            missing.append(case)
            continue
        r=read(result)
        qualified+=read(prior)["selection"]["qualified"]
        if "incumbent_arms" not in r:
            r["incumbent_arms"]=read(ROOT/"reports/2026_10_19_ds23_predictive_linear"/(case+".json"))["results"]["all_linear"]["policy_arms"]
        records.append(r)
    summary=dict(position=metrics(records),completed=len(records),total=len(cases),missing=missing,
        prior_qualified_scans=qualified,execution_failures=[r for r in execution if r["code"]],
        evaluation_only_reference_not_used_for_hyperparameters=True,
        original20_development_only_generalization_not_established=True,
        positive_report_not_authorized_by_this_checkpoint=True,summary_source_sha256=sha(Path(__file__)))
    write(path/"local_summary.json",summary)
    print("joint prior",summary)
    history=ROOT/"reports/2026_10_19_algo03_rf_supported_history"
    output=history/("result.json" if (history/"result.json").exists() else "partial.json")
    if output.exists():
        records=read(output)["records"]
        summary=dict(position=metrics(records),completed=len(records),total=len(cases),
            selected_fractions={r["case"]:r["selected_fraction"] for r in records},
            stationary_history_assumption_unverified=True,not_single_scan_ALGO03=True,
            generalization_not_established=True,no_publication_yet=True)
        write(history/"local_summary.json",summary)
        print("history support",summary)


if __name__=="__main__":
    run()
