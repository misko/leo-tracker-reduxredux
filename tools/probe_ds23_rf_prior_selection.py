"""RF-only prior-model selection on one common, quality-gated observation mask."""

import argparse
from pathlib import Path

import numpy as np

from evaluate_ds23_family_weighting import OUT as WEIGHTS
from investigate_algo01_ds23_0217 import problem
from probe_ds23_weighted_priors import OUT as CONTROLS_OUT,refit
from run_algo01_ds23_sample import OUT as SOURCE,ROOT,final_scan,read,sha,write

OUT=ROOT/"reports/2026_10_18_ds23_rf_prior_selection"
MODELS=("baseline","phase_floor3","fragment300","receiver50","combined")
ARMS=("c0","fitted_c")


def common_mask(original,masks):
    result=np.asarray(original,bool).copy()
    for mask in masks:
        if np.asarray(mask).shape!=result.shape:raise ValueError("matching observation masks required")
        result &= np.asarray(mask,bool)
    return result


def choose_by_rf(candidates):
    """Use c0 objective only; ties prefer the baseline, then declared order."""
    return min(MODELS,key=lambda name:(candidates[name]["c0"]["score"],MODELS.index(name)))


def run(case):
    OUT.mkdir(parents=True,exist_ok=True)
    path=OUT/(case+".json")
    if path.exists():return
    scan=final_scan(case);original=read(SOURCE/case/"result.json")
    node=original["final_node"]
    source=read(CONTROLS_OUT/(case+".json"))
    weight_source=read(WEIGHTS/case/"result.json")["results"]["cross_rx_support"]
    keep=common_mask(original["final_mask"],[weight_source["mask"]]+
                     [r["mask"] for r in source["results"].values()])
    weights=np.array(weight_source["weights"])
    base=problem(scan,node,"c0",keep)
    history=[]
    for epoch in range(3):
        candidates={model:{arm:refit(scan,node,keep,arm,weights,model) for arm in ARMS} for model in MODELS}
        failed={r["component"] for model in MODELS for arm in ARMS
                for r in candidates[model][arm]["gates"]["tracks"] if not r["compatible"]}
        history.append(dict(epoch=epoch,points=int(keep.sum()),failed=sorted(failed)))
        if not failed or epoch==2:break
        for row,sl in zip(base.rows,base.slices,strict=True):
            if row["component"] in failed:keep[sl]=False
    chosen=choose_by_rf(candidates)
    write(path,dict(case=case,models=candidates,chosen=chosen,arms=candidates[chosen],
        common_mask=keep,history=history,valid=not failed,selection_rule="minimum c0 RF objective on common data",
        every_model_has_same_observations_labels_aliases_and_weights=True,
        paired_c_model_selection=True,GPS_used=False,source_sha256=sha(Path(__file__)),
        input_sha256=dict(controls=sha(CONTROLS_OUT/(case+".json")),weights=sha(WEIGHTS/case/"result.json")),
        no_claim_of_calibrated_model_probabilities=True))
    print(case,"selected",chosen,"points",int(keep.sum()),"valid",not failed,flush=True)


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",required=True)
    run(parser.parse_args().case)
