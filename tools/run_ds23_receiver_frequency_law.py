"""Two bounded workers evaluate a predeclared receiver-law policy on all20.

Only radio evidence can choose the per-scan law. This runner produces local
scientific evidence, not a publication or a claim of generalization.
"""

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from probe_ds23_receiver_frequency_law import OUT, INCUMBENT
from run_algo01_ds23_sample import ROOT, OUT as ORIGINAL, read, write, sha


def worker(case):
    output = OUT / (case + ".json")
    if output.exists():
        result = read(output)
        if result["source_sha256"] != sha(ROOT / "tools/probe_ds23_receiver_frequency_law.py"):
            raise ValueError("existing experiment belongs to another source")
        return dict(case=case, code=0, result_sha256=sha(output), verified_existing=True)
    started = time.monotonic()
    try:
        with (OUT / (case + ".log")).open("w") as stream:
            result = subprocess.run(["nice", "-n", "5", str(ROOT / ".venv/bin/python"),
                str(ROOT / "tools/probe_ds23_receiver_frequency_law.py"), "--case", case],
                cwd=ROOT, env=dict(os.environ, PYTHONPATH="src:tools", OPENBLAS_NUM_THREADS="1",
                OMP_NUM_THREADS="1", MKL_NUM_THREADS="1"), stdout=stream, stderr=stream, timeout=300)
        return dict(case=case, code=result.returncode, seconds=time.monotonic()-started,
                    result_sha256=sha(output) if output.exists() else None)
    except subprocess.TimeoutExpired:
        return dict(case=case, code=124, seconds=time.monotonic()-started)


def run():
    OUT.mkdir(exist_ok=True)
    if (OUT / "protocol.json").exists():
        raise FileExistsError("preserve declared experiment")
    cases = sorted(r["dataset_label"] for r in read(ORIGINAL / "sample.json")["selected"])
    write(OUT / "protocol.json", dict(cases=cases, workers=2, timeout_s=300,
        hypothesis="receiver smooth correction is additive Hz, not proportional to RF",
        additional_nuisance_dimensions=0, prior_at_reference_RF_unchanged=True,
        original_curved_data_and_added_linear_IDs_labels_aliases_frozen=True,
        policy_options=["fixed_additive_Hz", "curved_predictive_RF_selection"],
        RF_selection="new curved c0 normalized objective improves by >2*log(2) and paired gates pass; otherwise ALGO02",
        RF_selection_uses_exact_same_curved_observations=True,
        RF_not_GPS_selects_every_per_scan_choice=True,
        cohort="original20 development scans; independent qualification still required",
        source_sha256={n: sha(ROOT / "tools" / n) for n in
            ("ds23_receiver_frequency_law.py", "probe_ds23_receiver_frequency_law.py", "run_ds23_receiver_frequency_law.py")}))
    receipts = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(worker, case): case for case in cases}
        for future in as_completed(futures):
            try:
                result = future.result()
            except Exception as error:
                result = dict(case=futures[future], code=1, reason=repr(error))
            receipts.append(result)
            write(OUT / "execution.json", receipts)
            print(result, flush=True)


if __name__ == "__main__":
    run()
