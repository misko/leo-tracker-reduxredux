"""Independent densities, original residual gates and membership for014 trials."""

from pathlib import Path
import numpy as np

import probe_ds23_iteration014_recovery as binding
import probe_ds23_iteration014_cross_band_step as step
from audit_ds23_iteration013_recovery import check
from run_algo01_ds23_sample import read,write,sha

RAW=binding.runner.RAW


def main():
    binding.configure('paths');step.binding.configure('support');out=RAW/'recovery_endpoint_audit.json'
    if out.exists():raise FileExistsError('preserve014 independent replay')
    assert read(RAW/'batch_execution.json')['all_passed']
    assert read(step.OUT/'execution.json')['all_passed']
    rows=[];memberships=[]
    for case in read(RAW/'protocol.json')['cases']:
        original=binding.runner.engine.current_setup(case);d,cov,kind,_=binding.paths.paths.parent(case);folder=RAW/'graph_seeded_paths'
        records=list(read(folder/(case+'.json'))['methods'].items());constrained=read(RAW/'temporal_feasibility'/(case+'.json'))
        if 'arms' in constrained:records.append(('constrained',constrained))
        for method,t in records:
            if 'arms' not in t:continue
            fragments=t.get('selected_paths') or read(folder/(case+'_'+method+'_selection.json'))['selected']
            scan,entries=binding.paths.paths.native.append_native_paths(d['scan'],d['entries'],fragments,binding.paths.paths.native.receiver_basis(d['scan']));dd=dict(d,scan=scan,entries=entries)
            for arm,saved in t['arms'].items():
                p=binding.paths.paths.build(dd,kind,arm,saved['phase_reference']);rows.append(check(dd,p,arm,saved,'temporal_'+method))
                replay=binding.paths.paths.coverage(dd,kind,arm,saved)
                if set(replay['accepted_observation_ids'])!=set(t['coverage'][arm]['accepted_observation_ids']):raise ValueError('native014 membership changed')
        initial=read(RAW/case/'inventory.json')['arms']
        for i,t in enumerate(read(RAW/'point_rich_extra_curve'/(case+'.json'))['trials']):
            dd=dict(original,node=t['node'],keep=np.asarray(t['mask'],bool),means=np.asarray(t['means']),entries=t['entries']);coverage={}
            for arm,saved in t['arms'].items():
                p=binding.runner.engine.support.build(original,t['node'],dd['keep'],arm,saved['phase_reference'],dd['means']);rows.append(check(dd,p,arm,saved,'extra_'+str(i)))
                coverage[arm]=step.coverage(dd,t,arm,p)
                if t['paired_valid'] and not set(initial[arm]['accepted_observation_ids'])<=set(coverage[arm]['accepted_observation_ids']):raise ValueError('extra014 loses original IDs')
            memberships.append(dict(case=case,kind='extra',trial=i,coverage=coverage))
        saved=read(step.OUT/(case+'.json'))
        for kind in ['nulls','trials']:
            for i,t in enumerate(saved[kind]):
                dd=dict(original,node=t['node'],keep=np.asarray(t['mask'],bool),means=np.asarray(t['means']),entries=t['entries']);coverage={}
                for arm,s in t['arms'].items():
                    p=step.build(original,t,arm,t['events']);rows.append(check(dd,p,arm,s,'cross_band_'+kind+'_'+t['model_base']))
                    if kind=='trials':
                        coverage[arm]=step.coverage(dd,t,arm,p)
                        if set(coverage[arm]['accepted_observation_ids'])!=set(t['coverage'][arm]['accepted_observation_ids']):raise ValueError('event014 membership changed')
                        if t['accepted'] and not set(initial[arm]['accepted_observation_ids'])<=set(coverage[arm]['accepted_observation_ids']):raise ValueError('accepted event014 loses original IDs')
                if coverage:memberships.append(dict(case=case,kind='cross_band',trial=i,coverage=coverage))
    write(out,dict(rows=rows,memberships=memberships,all_passed=True,no_new_optimization_or_GPS=True,source_sha256=sha(Path(__file__))))
    print('014 independently audited endpoint arms',len(rows),flush=True)


if __name__=='__main__':main()
