"""Exact native lookup repair; audit old endpoints and resume only failed0209."""

from pathlib import Path
import shutil
import numpy as np

import run_ds23_dbg01_iteration_011 as runner
import run_ds23_dbg01_iteration_010 as older
import probe_ds23_graph_seeded_paths as paths
from ds23_exact_native_time_union import exact_time_union
from run_algo01_ds23_sample import read,write,sha

OLD=runner.RAW/'graph_seeded_paths'
OUT=runner.RAW/'graph_seeded_paths_v2'
ORIGINAL_APPEND=paths.native.append_native_paths


def append_exact(scan,entries,fragments,basis):
    changed,new_entries=ORIGINAL_APPEND(scan,entries,fragments,basis)
    return exact_time_union(changed),new_entries


def configure():
    runner.configure();paths.runner=runner;paths.OUT=OUT;paths.native.append_native_paths=append_exact


def audit_arm(d,kind,fragments,arm,saved):
    basis=paths.native.receiver_basis(d['scan']);old_scan,entries=ORIGINAL_APPEND(d['scan'],d['entries'],fragments,basis)
    new_scan=exact_time_union(old_scan);dd_old=dict(d,scan=old_scan,entries=entries);dd_new=dict(d,scan=new_scan,entries=entries)
    old_p=paths.build(dd_old,kind,arm,saved['phase_reference']);new_p=paths.build(dd_new,kind,arm,saved['phase_reference'])
    x=np.asarray(saved['endpoint_east_north_km']);a,b=old_p.calculate(x),new_p.calculate(x)
    objective_delta=b['negative_twice_elbo']-a['negative_twice_elbo'];saved_delta=b['negative_twice_elbo']-saved['negative_twice_elbo']
    coefficient_delta=float(np.max(abs(a['coefficient']-b['coefficient'])))
    if max(abs(objective_delta),abs(saved_delta),coefficient_delta)>1e-5:raise ValueError('native time-union repair changed a saved inference objective')
    before=paths.coverage(dd_old,kind,arm,saved);after=paths.coverage(dd_new,kind,arm,saved)
    if set(before['accepted_observation_ids'])!=set(after['accepted_observation_ids']):raise ValueError('published native membership changes after time correction')
    if not all(np.array_equal(new_scan.times[ix],t['times']) for t,ix in zip(new_scan.tracks,new_scan.index,strict=True)):raise ValueError('time lookup is not exact')
    return dict(arm=arm,objective_delta=objective_delta,saved_objective_delta=saved_delta,coefficient_delta=coefficient_delta,
        old_accepted=before['associated'],new_accepted=after['associated'],unique_IDs_identical=True,
        old_global_times=len(old_scan.times),new_global_times=len(new_scan.times),
        all_original_native_times_values_basis_and_observation_IDs_unchanged=True)


def audit_previous():
    result=[]
    for module,cases in [(older,['DS23-0080','DS23-0257']),(runner,['DS23-0163'])]:
        module.configure();paths.runner=module;paths.OUT=module.RAW/'graph_seeded_paths'
        for case in cases:
            d,cov,kind,_=paths.parent(case)
            for name,t in read(paths.OUT/(case+'.json'))['methods'].items():
                if 'arms' not in t:continue
                fragments=read(paths.OUT/(case+'_'+name+'_selection.json'))['selected']
                result.extend(dict(case=case,method=name,**audit_arm(d,kind,fragments,a,s)) for a,s in t['arms'].items())
            if module is older and case=='DS23-0080':
                t=read(module.RAW/'temporal_feasibility'/(case+'.json'))
                result.extend(dict(case=case,method='published_constrained_policy',**audit_arm(d,kind,t['selected_paths'],a,s)) for a,s in t['arms'].items())
    return result


def main():
    configure();OUT.mkdir(exist_ok=True)
    if (OUT/'protocol.json').exists():raise FileExistsError('preserve native-time repair')
    write(OUT/'protocol.json',dict(source_sha256=sha(Path(__file__)),exact_time_helper_sha256=sha(Path(exact_time_union.__code__.co_filename)),
        original_append_helper_sha256=sha(Path(ORIGINAL_APPEND.__code__.co_filename)),
        cases=['DS23-0163','DS23-0209'],original0209failure='post-fit extension lookup exceeded old graph-only time grid',
        fix='union original global times with every appended native timestamp, recompute exact lookup for every original and new track',
        no_timestamp_interpolation_or_CFO_or_basis_or_likelihood_change=True,
        original_failed_outputs_preserved=True,reuse0163byte_exact_after_objective_and_membership_parity=True,
        prior010policies_independently_replayed_for_parity=True,rerun_only_failed0209_same_RF_proposals_and_fit_budget=True,
        no_GPS_future_TLE_new_RF_or_rule_threshold_change=True))
    checks=audit_previous();write(OUT/'prior_endpoint_parity.json',dict(rows=checks,all_passed=True))
    for p in OLD.glob('DS23-0163*.json'):shutil.copyfile(p,OUT/p.name)
    configure();receipt=paths.one('DS23-0209')
    for suffix in ['discovery','independent_selection']:
        a=OLD/('DS23-0209_'+suffix+'.json');b=OUT/a.name
        if read(a)!=read(b):raise ValueError('native-time repair changed a previously frozen RF proposal')
    write(OUT/'execution.json',dict(rows=[dict(case='DS23-0163',status='complete',reused=True),receipt],all_terminal=True,all_passed=True,
        all_RF_proposals_preserved_no_case_resampled=True,prior_parity_arms=len(checks)))


if __name__=='__main__':main()
