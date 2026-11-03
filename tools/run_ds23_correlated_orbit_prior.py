"""Bounded original20 experiment; pre-RF history alone selects coupling."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from learn_ds23_joint_orbit_prior import OUT
from run_algo01_ds23_sample import ROOT,OUT as SOURCE,read,write,sha


def worker(case):
    began=time.monotonic()
    output=OUT/(case+"_position.json")
    if output.exists():
        return dict(case=case,code=0,result_sha256=sha(output),verified_existing=True)
    env=dict(os.environ,PYTHONPATH="src:tools",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1",MKL_NUM_THREADS="1")
    with (OUT/(case+".log")).open("w") as stream:
        commands=[]
        if not (OUT/(case+"_prior.json")).exists():
            commands.append("learn_ds23_joint_orbit_prior.py")
        commands.append("probe_ds23_correlated_orbit_prior.py")
        for script in commands:
            try:
                result=subprocess.run(["nice","-n","5",str(ROOT/".venv/bin/python"),str(ROOT/"tools"/script),"--case",case],
                    cwd=ROOT,env=env,stdout=stream,stderr=stream,timeout=300)
            except subprocess.TimeoutExpired:
                return dict(case=case,code=124,failed_stage=script,seconds=time.monotonic()-began)
            if result.returncode:
                return dict(case=case,code=result.returncode,failed_stage=script,seconds=time.monotonic()-began)
    return dict(case=case,code=0,result_sha256=sha(output),seconds=time.monotonic()-began)


def run():
    OUT.mkdir(exist_ok=True)
    if (OUT/"protocol.json").exists():
        raise FileExistsError("preserve declared cohort")
    cases=sorted(r["dataset_label"] for r in read(SOURCE/"sample.json")["selected"])
    write(OUT/"protocol.json",dict(cases=cases,workers=2,per_stage_timeout_s=300,
        hypothesis="causal phase and physical orbit errors need not be independent",
        coordinates=["phase_at_midpoint","reference_aligned_mean_motion","inclination","RAAN"],
        marginal_scales_and_original_ALGO02_phase_distribution_preserved=True,
        correlation_candidates=[0.,.25,.5,.75,1.],training_penalty="6*log(N)",
        qualification="later causal TLE density gain greater than log(N_validation), at least30train+30validation",
        phase_shape_distribution="original Student phase plus conditional Gaussian shape",
        no_RF_GPS_future_TLE_selects_correlation=True,
        same_original_calibration_and_offered_linear_points_labels_aliases_masks=True,
        same_c0_fitted_c_5phase_48step_budget=True,
        correlation_not_qualified_means_exact_ALGO02=True,
        failed_curved_pair_means_original_ALGO02_failed_linear_pair_means_qualified_curved_pair=True,
        full_native_prior_precision_used_for_shared_predictive_covariance=True,
        scope="original20 development; no generalization claim until independent evaluation",
        source_sha256={n:sha(ROOT/"tools"/n) for n in ("ds23_joint_orbit_prior.py","learn_ds23_joint_orbit_prior.py",
            "ds23_correlated_orbit_problem.py","probe_ds23_correlated_orbit_prior.py","run_ds23_correlated_orbit_prior.py")}))
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,case):case for case in cases}
        for future in as_completed(futures):
            try:
                result=future.result()
            except Exception as error:
                result=dict(case=futures[future],code=1,error=repr(error))
            receipts.append(result)
            write(OUT/"execution.json",receipts)
            print(result,flush=True)


if __name__=="__main__":
    run()
