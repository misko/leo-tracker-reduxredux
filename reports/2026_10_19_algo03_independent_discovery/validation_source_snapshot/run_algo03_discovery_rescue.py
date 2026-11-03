"""Frozen RF-triggered validation of independent-discovery rescue.

All six non-development triggers are included before looking at position error.
Subprocesses isolate the research path bindings. No evaluation GPS is imported.
"""

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path

from probe_algo03_independent_discovery import OUT
from run_algo01_ds23_sample import ROOT,read,write,sha


def run(workers=30):
    path=OUT/"validation_protocol.json"
    if path.exists():
        raise FileExistsError("preserve frozen validation")
    triggers=read(OUT/"trigger_inventory.json")
    cases=[r["case"] for r in triggers["triggers"] if r["case"]!="DS23-0081"]
    sources=["probe_algo03_independent_discovery.py","probe_algo03_discovery_rescue.py",
             "run_algo03_discovery_rescue.py"]
    protocol=dict(cases=cases,development_case="DS23-0081",workers=workers,
        rule=triggers["rule"],trigger_sha256=sha(OUT/"trigger_inventory.json"),
        all_RF_triggered_non_development_scans_included_before_accuracy_evaluation=True,
        no_GPS_or_position_error_in_trigger_or_branch_selection=True,
        search_starts=13,RF_seeds_per_start=4,screen_rounds=2,screen_steps=12,fully_fitted_finalists=2,
        full_rounds=5,full_steps=48,paired_c_original_populations_and_weights_match=True,
        normalized_c0_loss_contest_pays_two_log_number_of_starts_plus_one=True,
        original_ALGO02_priors_gates_and_maximum_gate_rounds_unchanged=True,
        accepted_incumbent_kept_when_rescue_unavailable_or_unqualified=True,
        original_ALGO02_execution_failures_are_not_rescued_or_removed_from_coverage=True,
        sources={s:sha(ROOT/"tools"/s) for s in sources})
    write(path,protocol)
    receipts=[];began=time.monotonic()
    def one(case,index,stage):
        script="probe_algo03_discovery_rescue.py" if stage=="rescue" else "probe_algo03_independent_discovery.py"
        args=[sys.executable,str(ROOT/"tools"/script),"--case",case]
        if stage!="rescue":args += ["--start-index",str(index),"--stage",stage]
        directory=OUT/case;directory.mkdir(exist_ok=True)
        start=time.monotonic();log=directory/f"validation_{stage}_{index:02d}.log"
        try:
            with log.open("w") as stream:
                p=subprocess.run(args,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT,
                    timeout=600 if stage=="screen" else 1200,
                    env=dict(os.environ,PYTHONPATH="src:tools",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1"))
            code=p.returncode
        except subprocess.TimeoutExpired:
            code=124
        return dict(case=case,index=index,stage=stage,code=code,seconds=time.monotonic()-start,
                    log=str(log.relative_to(ROOT)),log_sha256=sha(log))
    def execute(jobs):
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for future in as_completed([pool.submit(one,*job) for job in jobs]):
                row=future.result();receipts.append(row)
                write(OUT/"validation_execution.json",dict(receipts=receipts,elapsed_s=time.monotonic()-began,
                    all_terminal=False,protocol_sha256=sha(path)))
                print(row,flush=True)
    execute([(c,k,"screen") for c in cases for k in range(13)]+[(c,0,"incumbent") for c in cases])
    complete=[];finalists=[]
    for case in cases:
        rows=[r for r in receipts if r["case"]==case]
        if len(rows)!=14 or any(r["code"] for r in rows):continue
        screens=[read(OUT/case/f"start_{k:02d}_screen.json") for k in range(13)]
        ranked=sorted(screens,key=lambda r:r["arms"]["c0"]["negative_twice_elbo"])[:2]
        finalists.extend((case,r["start_index"],"fit") for r in ranked);complete.append(case)
    execute(finalists)
    eligible=[c for c in complete if all(r["code"]==0 for r in receipts if r["case"]==c)]
    execute([(c,0,"rescue") for c in eligible])
    write(OUT/"validation_execution.json",dict(receipts=receipts,elapsed_s=time.monotonic()-began,
        all_terminal=True,protocol_sha256=sha(path),
        unavailable_cases=[c for c in cases if not (OUT/c/"rescue.json").exists()]))


if __name__=="__main__":
    run()
