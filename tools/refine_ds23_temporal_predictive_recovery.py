"""One prespecified whole-path residual screen before a cold predictive refit."""

from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path

import numpy as np

import probe_ds23_temporal_predictive_recovery as parent
from probe_ds23_frequency_events import summary,refit
from probe_ds23_reentry_family_cavity import audit_baseline
from run_ds23_combined_recovery_full import valid
from run_algo01_ds23_sample import read,write,sha

OUT=parent.OUT/'whole_path_screen'


def whole_path_filter(fragments,paired_gates):
    """Keep the complete original candidate or reject it in both arms."""
    accepted=[{r['component'] for r in gates if r['compatible']} for gates in paired_gates.values()]
    if len(accepted)!=2:raise ValueError('both c arms required')
    keys=set.intersection(*accepted)
    return [fragment for fragment in fragments if fragment['key'] in keys]


def one(case):
    output=OUT/(case+'.json')
    if output.exists():return dict(case=case,cached=True)
    d=parent.runner.engine.current_setup(case);discovery=read(parent.OUT/(case+'_discovery.json'))
    original=read(parent.runner.RAW/case/'inventory.json')['arms'];methods={}
    for method,proposal in discovery['methods'].items():
        fragments=proposal['selected'];scan,entries=parent.temporal.append_fragments(d['scan'],d['entries'],fragments)
        dd=dict(d,scan=scan,entries=entries);checks={}
        for arm,saved in d['arms'].items():
            p=parent.runner.engine.baseline.build(dd,arm,saved['phase_reference'])
            checks[arm]=summary(p,np.asarray(saved['endpoint_east_north_km']),entries)['linear_gates'][len(d['entries']):]
        selected=whole_path_filter(fragments,checks)
        selection=dict(case=case,method=method,checks=checks,selected=selected,
            full_original_paths_preserved=True,geographic_score_inspected_for_selection=False)
        write(OUT/(case+'_'+method+'_selection.json'),selection)
        if not selected:
            methods[method]=dict(accepted=False,reason='no whole path passes both incumbent residual checks');continue
        scan,entries=parent.temporal.append_fragments(d['scan'],d['entries'],selected)
        arms={a:refit(scan,d['node'],d['keep'],a,d['powers'],d['means'],d['model'],[],entries) for a in ['c0','fitted_c']}
        dd=dict(d,scan=scan,entries=entries)
        audits={a:audit_baseline(dd,a,r) for a,r in arms.items()}
        cov={a:parent.coverage(d,a,r,r['linear_gates'][len(d['entries']):]) for a,r in arms.items()}
        preserved={a:set(original[a]['accepted_observation_ids'])<=set(cov[a]['accepted_observation_ids']) for a in arms}
        accepted=bool(valid(arms) and all(preserved.values()))
        methods[method]=dict(accepted=accepted,paired_valid=bool(valid(arms)),incumbent_IDs_preserved=preserved,
            arms=arms,coverage=cov,audits=audits,new_paths=len(selected),new_points=sum(len(f['times']) for f in selected))
        print(case,method,'whole paths',len(selected),'accepted',accepted,flush=True)
    write(output,dict(case=case,methods=methods,protocol_sha256=sha(OUT/'protocol.json')))
    return dict(case=case,status='complete',accepted={k:r['accepted'] for k,r in methods.items()})


def main():
    parent.runner.configure();OUT.mkdir(exist_ok=True)
    record=dict(cases=read(parent.OUT/'protocol.json')['cases'],
        source_sha256=sha(Path(__file__)),parent_protocol_sha256=sha(parent.OUT/'protocol.json'),
        helper_sha256=sha(Path(parent.temporal.__file__)),
        hypothesis='high Gaussian compatibility does not guarantee structure-free predictive residuals',
        rule='screen every whole discovered path using unchanged residual/alias/horizon gates at both incumbent endpoints; '
            'freeze retained paths; one cold 5x48 refit; both final gates and all incumbent IDs must survive',
        maximum_new_refits_per_case=2,no_iterative_pruning_or_point_trimming=True,
        matched_c_arms_original_covariance_and_other_priors=True,GPS_or_following_TLE_used=False)
    path=OUT/'protocol.json'
    if path.exists():
        if read(path)!=record:raise ValueError('preserve frozen whole-path protocol')
    else:write(path,record)
    rows=[]
    with ProcessPoolExecutor(max_workers=2) as pool:
        for future in as_completed([pool.submit(one,case) for case in record['cases']]):
            rows.append(future.result());print(rows[-1],flush=True)
    write(OUT/'execution.json',dict(rows=rows,all_terminal=True,RF_selection_complete_before_geographic_scoring=True))


if __name__=='__main__':main()
