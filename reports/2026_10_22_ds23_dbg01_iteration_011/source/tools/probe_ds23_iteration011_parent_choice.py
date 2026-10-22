"""Same-mask RF tie-break between default and support-aware graph parents."""

import argparse
from pathlib import Path
import numpy as np
import shutil

import run_ds23_dbg01_iteration_011 as runner
import probe_ds23_graph_seeded_paths as paths
import report_ds23_dbg01_iteration_004 as graph
from ds23_family_cavity import unused_student_gap
from probe_ds23_family_cavity_position import unused_count
from run_algo01_ds23_sample import read,write,sha

OUT=runner.RAW/'same_mask_parent_choice'
PATHS=OUT/'paths'
ORIGINAL_PARENT=paths.parent


def entry_signature(entries):
    return [(e['component'],e['candidate_index'],e['alias'],tuple(e['observation_ids'])) for e in entries]


def choose(default,support,scores):
    if default is None or support is None:return dict(eligible=False,choose_support=False,reason='two qualified parents required')
    if not np.array_equal(default['mask'],support['mask']) or entry_signature(default['entries'])!=entry_signature(support['entries']):
        return dict(eligible=False,choose_support=False,reason='masks or predictive factors differ; no raw score comparison')
    gains={a:scores['default'][a]-scores['support'][a] for a in ['c0','fitted_c']}
    return dict(eligible=True,gains=gains,penalty=float(2*np.log(2)),choose_support=bool(min(gains.values())>2*np.log(2)))


def select():
    runner.configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve parent choice experiment')
    cases=read(runner.RAW/'protocol.json')['cases']
    write(OUT/'protocol.json',dict(cases=cases,source_sha256=sha(Path(__file__)),
        only_identical_observation_mask_and_predictive_factors_compared=True,
        both_parents_must_already_pass_original_paired_gates=True,
        RF_score='original normalized full-data bound minus unused Student prior constant',
        binary_parent_preference_penalty=float(2*np.log(2)),both_c_arms_must_improve=True,
        no_additional_parent_fits_no_GPS_following_TLE_or_new_RF=True))
    rows=[]
    for case in cases:
        d=runner.engine.current_setup(case);default=read(runner.RAW/'single_curve_reentry'/(case+'_positions.json'))['selected']
        support=read(runner.RAW/'support_aware_reentry'/(case+'_audited.json'))['selected'];scores={};checks=[]
        if default is not None and support is not None and np.array_equal(default['mask'],support['mask']):
            for name,t in [('default',default),('support',support)]:
                scores[name]={}
                for a,r in t['arms'].items():
                    dd=dict(d,node=t['node'],keep=np.asarray(t['mask'],bool),means=np.asarray(t['means']),entries=t['entries'])
                    p=runner.engine.support.build(d,t['node'],np.asarray(t['mask'],bool),a,r['phase_reference'],np.asarray(t['means'])) if name=='support' else runner.engine.baseline.build(dd,a,r['phase_reference'])
                    value=p.calculate(np.asarray(r['endpoint_east_north_km']))['negative_twice_elbo']
                    if abs(value-r['negative_twice_elbo'])>1e-5:raise ValueError('parent objective replay failed')
                    scores[name][a]=value-unused_count(p,t['entries'])*unused_student_gap(d['model']['nu'])
                    checks.append(dict(parent=name,arm=a,objective_difference=value-r['negative_twice_elbo']))
        rows.append(dict(case=case,scores=scores,checks=checks,**choose(default,support,scores)))
    write(OUT/'RF_selection.json',dict(rows=rows,choices_frozen_before_new_child_fits_and_geographic_scoring=True))
    print(rows,flush=True)


def selected_parent(case):
    decision=next(r for r in read(OUT/'RF_selection.json')['rows'] if r['case']==case)
    if not decision['choose_support']:return ORIGINAL_PARENT(case)
    original=runner.engine.current_setup(case);t=read(runner.RAW/'support_aware_reentry'/(case+'_audited.json'))['selected'];graph.RAW=runner.RAW
    d,arms,cov=graph.residual_and_coverage(original,t,'support')
    protected={r['candidate_index'] for r,sl in zip(original['base'].rows,original['base'].slices,strict=True) if original['keep'][sl].any()}|{e['candidate_index'] for e in original['entries']}
    return dict(d,arms=arms,original_protected=protected),cov,'support',t


def apply():
    runner.configure();paths.runner=runner;paths.OUT=PATHS;paths.parent=selected_parent;PATHS.mkdir(exist_ok=True)
    if (PATHS/'execution.json').exists():raise FileExistsError('preserve parent-choice child results')
    rows=[]
    for r in read(OUT/'RF_selection.json')['rows']:
        if r['choose_support']:rows.append(paths.one(r['case']))
        else:
            for p in (runner.RAW/'graph_seeded_paths_v2').glob(r['case']+'*.json'):shutil.copyfile(p,PATHS/p.name)
            rows.append(dict(case=r['case'],status='complete',reused_current_parent=True))
    write(PATHS/'execution.json',dict(rows=rows,all_terminal=True,all_passed=True,no_GPS_used=True))


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--stage',choices=['select','apply'],required=True);args=parser.parse_args()
    select() if args.stage=='select' else apply()


if __name__=='__main__':main()
