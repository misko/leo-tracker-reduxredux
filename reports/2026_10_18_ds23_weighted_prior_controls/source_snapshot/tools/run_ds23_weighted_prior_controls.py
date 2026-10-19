"""Bounded subprocess evaluation of four frozen weighted-prior controls."""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor,as_completed
from pathlib import Path

from probe_ds23_weighted_priors import OUT,CONTROLS
from run_algo01_ds23_sample import OUT as SOURCE,ROOT,read,sha,write


def worker(case):
    start=time.monotonic()
    env=dict(os.environ,PYTHONPATH="src:tools",OPENBLAS_NUM_THREADS="1",OMP_NUM_THREADS="1")
    path=OUT/(case+".log")
    with path.open("a") as stream:
        result=subprocess.run([str(ROOT/".venv/bin/python"),str(ROOT/"tools/probe_ds23_weighted_priors.py"),
                               "--case",case],cwd=ROOT,env=env,stdout=stream,stderr=stream)
    return dict(case=case,code=result.returncode,seconds=time.monotonic()-start,
                source_sha256=sha(ROOT/"tools/probe_ds23_weighted_priors.py"))


def run():
    OUT.mkdir(parents=True,exist_ok=True)
    cases=[r["dataset_label"] for r in read(SOURCE/"sample.json")["selected"]]
    protocol=dict(cases=cases,controls=CONTROLS,workers=2,
        source_sha256=sha(ROOT/"tools/probe_ds23_weighted_priors.py"),
        original_sample_sha256=sha(SOURCE/"sample.json"),
        development_probes=["DS23-0217","DS23-0045"],GPS_used_for_rule_selection=False,
        control_values_fixed_before_cohort_results=True,unchanged_regional_box_width_km=25,
        base_weights="frozen cross-RX 1/.6/.2 on retained independent owner support",
        original_causal_inputs_and_discrete_labels_frozen=True,
        budgets=dict(phase_rounds=5,steps_per_round=48,paired_gate_rounds=4),
        target_mean_and_median_km=.5)
    write(OUT/"protocol.json",protocol)
    receipts=[]
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures={pool.submit(worker,c):c for c in cases}
        for future in as_completed(futures):
            receipt=future.result();receipts.append(receipt)
            write(OUT/"execution.json",receipts)
            print(receipt["case"],"code",receipt["code"],"seconds",round(receipt["seconds"],1),flush=True)


if __name__=="__main__":run()
