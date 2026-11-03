"""Recover only terminal time-limited pilots using equivalent fold scheduling."""

from pathlib import Path
import probe_ds23_predictive_position_descent as engine
from ds23_parallel_family_score import score_position
from run_algo01_ds23_sample import ROOT,read,write,sha

ORIGINAL_OUT=engine.OUT
OUT=ORIGINAL_OUT/'parallel_recovery'
BULK=Path('/srv/bulk/leo/research/ds23-predictive-position-descent-parallel-20261021')


def main():
    original=read(ORIGINAL_OUT/'evaluation.json')
    if not original['all_terminal']:raise ValueError('original pilot still live; do not duplicate it')
    cases=[r['case'] for r in original['rows'] if r['status']=='failed']
    if len(cases)>3:raise ValueError('parallel recovery is bounded to at most three case workers')
    OUT.mkdir(exist_ok=True)
    request=dict(original_sha256=sha(ORIGINAL_OUT/'evaluation.json'),cases=cases,
        original_completed_pilots_preserved=True,only_terminal_failed_jobs_retried=True,
        same_objective_bounds_gradients_priors_optimizer_and240second_budget=True,
        fold_processes=8,case_workers=min(3,len(cases)),maximum_science_cores=24,
        source_tools={n:sha(ROOT/'tools'/n) for n in [Path(__file__).name,'ds23_parallel_family_score.py',
            'ds23_fast_family_prediction.py','ds23_pruned_training_moments.py']})
    path=OUT/'request.json'
    if path.exists() and read(path)!=request:raise ValueError('frozen parallel recovery request changed')
    if not path.exists():write(path,request)
    engine.OUT=OUT;engine.BULK=BULK;engine.CASES=cases;engine.score_position=score_position
    engine.main()


if __name__=='__main__':main()
