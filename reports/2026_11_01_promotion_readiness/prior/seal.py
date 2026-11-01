"""Write local artifact and numerical-source receipts; no commit/publish."""
import importlib.metadata
import os
import platform
import subprocess
import sys
import time
from pathlib import Path
import ablate as a


def main():
    files={}
    for module in list(sys.modules.values()):
        value=getattr(module,'__file__',None)
        if value:
            p=Path(value).resolve()
            if p.is_file() and p.is_relative_to(a.REPO) and p.suffix=='.py':files[str(p)]=a.e.sha(p)
    artifacts={str(p.relative_to(a.OUT)):a.e.sha(p) for p in sorted(a.OUT.rglob('*'))
        if p.is_file() and p.name!='run_manifest.json'}
    inputs={}
    for case in ('DS26-0058','DS26-0062','DS26-0060'):
        root=a.e.ROOTS[case[:4]]
        for p in (root/'inputs'/f'{case}.json',root/'catalogues'/f'{case}.json',
                root/'position'/case/'result.json'):
            inputs[str(p)]=a.e.sha(p)
    a.e.write(a.OUT/'run_manifest.json',dict(created_utc_ns=time.time_ns(),
        revision=subprocess.check_output(['git','rev-parse','HEAD'],cwd=a.REPO,text=True).strip(),
        cwd=str(a.REPO),python=sys.executable,python_version=platform.python_version(),
        environment={k:os.environ.get(k) for k in ('PYTHONDONTWRITEBYTECODE','OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','PYTHONPATH')},
        packages={k:importlib.metadata.version(k) for k in ('numpy','scipy','sgp4','matplotlib')},
        numerical_source_hashes=files,primary_input_hashes=inputs,artifact_hashes=artifacts,
        design='spec.json; execution_amendment.json records implementation-only prefit repair',
        commands=['ablate.py freeze','ablate.py run','local_sensitivity.py','rf_comparisons.py',
            'python -m unittest reports/2026_11_01_promotion_readiness/prior/test_ablate.py -v',
            'family_diagnostic.py','render.py','seal.py'],
        all_inference_causal_72h=True,truth_used_only_for_postfit_endpoint_error=True,
        production_changed=False,commit_or_push=False))


if __name__=='__main__':main()
