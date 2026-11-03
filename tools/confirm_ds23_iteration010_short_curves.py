"""Twenty scan-disjoint tests of short whole-curve recovery on the incumbent."""

from concurrent.futures import ProcessPoolExecutor,as_completed
import csv
from pathlib import Path
import numpy as np

import probe_ds23_iteration010_short_curves as experiment
from run_algo01_ds23_sample import read,write,sha

runner=experiment.binding.runner
OUT=runner.RAW/'short_confirmation20'


def choose_cases(rows):
    closed=set(runner.CLOSED)|{'DS23-0080','DS23-0257'}
    pool=sorted({r['case'] for r in rows if r['policy']=='equal_assignment_priors' and r['arm']=='fitted_c' and r['case'] not in closed})
    return sorted(np.random.default_rng(2026102210).choice(pool,20,replace=False).tolist())


def incumbent_parent(case):
    d=runner.engine.current_setup(case);cov={a:runner.engine.baseline.inventory(d,a) for a in ['c0','fitted_c']}
    active={r['candidate_index'] for r,sl in zip(d['base'].rows,d['base'].slices,strict=True) if d['keep'][sl].any()}
    d=dict(d,original_protected=active|{e['candidate_index'] for e in d['entries']})
    return d,cov,'default',None


def configure():
    experiment.OUT=OUT/'short_whole_curves';experiment.binding.configure()
    experiment.binding.paths.parent=incumbent_parent


def one(case):
    configure()
    try:return experiment.one(case)
    except Exception as exc:
        import traceback
        row=dict(case=case,status='failed',error=repr(exc),traceback=traceback.format_exc());write(experiment.OUT/(case+'_failed.json'),row);return row


def main():
    OUT.mkdir(exist_ok=True);(OUT/'short_whole_curves').mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve frozen confirmation cohort')
    positive=read(runner.RAW/'short_whole_curves/DS23-0257.json')['selected']
    if not positive or not positive['accepted']:raise ValueError('no qualified whole-curve development result')
    rows=list(csv.DictReader(runner.engine.baseline.BENCHMARK.open()));cases=choose_cases(rows)
    protocol=dict(cases=cases,seed=2026102210,workers=6,maximum_seconds_per_case=480,
        selection_uses_only_case_IDs_and_availability_no_error_values=True,
        excludes_all_closed_debug_queue_cases_and_current0080and0257=True,
        preselected_scan_disjoint_but_previously_studied_same_site_not_new_location_validation=True,
        incumbent_parent_only_no_additional_long_curve_reentry_or_temporal_paths=True,
        identical_short_curve_nomination_masks_priors_gates_and_budgets_to_development=True,
        maximum2RF_short_targets_and3whole_subset_fits_per_case=True,
        primary_selection='maximum added points among paired-gate passing trials preserving all parent accepted IDs; exact incumbent fallback',
        original_GPS_used_only_in_later_reporting=True,no_following_TLE_or_new_RF_or_IQ=True,
        source_sha256=sha(Path(__file__)),experiment_sha256=sha(Path(experiment.__file__)),
        adapter_sha256=sha(Path(experiment.promote.__code__.co_filename)),
        benchmark_sha256=sha(runner.engine.baseline.BENCHMARK))
    write(OUT/'protocol.json',protocol);results=[]
    with ProcessPoolExecutor(max_workers=6) as pool:
        for future in as_completed([pool.submit(one,c) for c in cases]):
            result=future.result();results.append(result);write(OUT/'progress.json',dict(requested=len(cases),completed=len(results),rows=results))
            print(result,flush=True)
    write(OUT/'execution.json',dict(rows=results,all_terminal=True,all_passed=all(r['status']=='complete' for r in results)))


if __name__=='__main__':main()
