"""Native density, residual, membership and phase-grid checks for015 experiments."""

from pathlib import Path
import numpy as np
from scipy.special import logsumexp
from scipy.stats import t as student,norm

import probe_ds23_iteration015_recovery as binding
import audit_ds23_iteration014_recovery as base_audit
import probe_ds23_iteration015_guard_parent as guard
import probe_ds23_iteration015_joint_step as joint
import probe_ds23_iteration015_joint_phase_alias as phase_alias
from audit_ds23_iteration013_recovery import check
from probe_ds23_single_curved_reentry import predictive_track_data
from leo.analysis.research.orbit_phase_geometry import phase_frequency_grid
from leo.analysis.research.retained_track_likelihood import PERIOD
from prototype_dsx01_continuous_position import latlon
from run_algo01_ds23_sample import read,write,sha

RAW=binding.runner.RAW


def phase_grid_check(d,kind,target):
    saved=d['arms']['c0'];x=np.asarray(saved['endpoint_east_north_km']);p=binding.paths.paths.build(d,kind,'c0',saved['phase_reference']);row=p.members.index(target['track_index']);data=predictive_track_data(d,p,x,row)
    y=data['values']-data['radio']@data['coefficient'][:data['radio_width']];cov=data['base_covariance'];inverse=np.linalg.inv(cov);constant=float(np.linalg.slogdet(cov)[1]+len(y)*np.log(2*np.pi));grid=np.linspace(-15,15,121);weights=np.full(len(grid),.25);weights[[0,-1]]=.125;rows=[]
    for nomination in target['grid_ranking']:
        j=next(j for j,n in enumerate(d['scan'].norads) if n==nomination['norad']);bank=dict(time_s=d['scan'].sky['time_s'],position_km=d['scan'].sky['position_km'][[j]],velocity_km_s=d['scan'].sky['velocity_km_s'][[j]])
        logdensity=[];aliases=[]
        for phase in grid:
            f,e=phase_frequency_grid(bank,data['times'],*latlon(x),phase_seconds=phase);raw=y-data['q']*f[0];alias=int(np.rint(-np.mean(raw)/PERIOD));raw=raw+alias*PERIOD
            scale=d['widths'][j];nu=d['model']['nu'];mean=d['all_means'][j]
            prior=norm.logpdf(phase,loc=mean,scale=scale) if nu is None else student.logpdf(phase,df=nu,loc=mean,scale=scale*np.sqrt((nu-2)/nu))
            logdensity.append(float(-.5*(raw@inverse@raw+constant)+prior) if np.min(e)>=0 else -np.inf);aliases.append(alias)
        score=float(-2*logsumexp(np.asarray(logdensity)+np.log(weights)));peak=int(np.argmax(logdensity));delta=score-nomination['score']
        if abs(delta)>2e-6 or grid[peak]!=nomination['phase_s'] or aliases[peak]!=nomination['alias']:raise ValueError('joint phase/alias grid nomination does not independently replay')
        rows.append(dict(case=d['scan'].case,norad=nomination['norad'],score_difference=delta,peak_phase_s=float(grid[peak]),alias=aliases[peak]))
    return rows


def main():
    out=RAW/'extended_endpoint_audit.json'
    if out.exists():raise FileExistsError('preserve015 extended replay')
    binding.configure('paths');binding.configure('cross_band_step')
    base_audit.binding=binding;base_audit.step=binding.cross_band;base_audit.RAW=RAW;base_audit.main()
    assert read(joint.OUT/'execution.json')['all_passed'] and read(phase_alias.OUT/'execution.json')['all_passed']
    rows=[];grids=[]
    for choice in read(guard.OUT/'RF_selection.json')['rows']:
        if not choice['use_guard']:continue
        case=choice['case'];d,cov,kind,_=guard.parent(case)
        for arm,s in d['arms'].items():rows.append(check(d,binding.paths.paths.build(d,kind,arm,s['phase_reference']),arm,s,'guard_parent'))
        folder=guard.PATHS;record=read(folder/(case+'.json'))
        for method,t in record['methods'].items():
            if 'arms' not in t:continue
            fragments=read(folder/(case+'_'+method+'_selection.json'))['selected'];scan,entries=binding.paths.paths.native.append_native_paths(d['scan'],d['entries'],fragments,binding.paths.paths.native.receiver_basis(d['scan']));dd=dict(d,scan=scan,entries=entries)
            for arm,s in t['arms'].items():
                p=binding.paths.paths.build(dd,kind,arm,s['phase_reference']);rows.append(check(dd,p,arm,s,'guard_'+method));covariance=binding.paths.paths.coverage(dd,kind,arm,s)
                if set(covariance['accepted_observation_ids'])!=set(t['coverage'][arm]['accepted_observation_ids']):raise ValueError('guard native membership changed')
    for case in read(RAW/'protocol.json')['cases']:
        d=binding.runner.engine.current_setup(case)
        for label in ['nulls','trials']:
            for i,t in enumerate(read(joint.OUT/(case+'.json'))[label]):
                dd=dict(d,node=t['node'],keep=np.asarray(t['mask'],bool),means=np.asarray(t['means']),entries=t['entries'])
                for arm,s in t['arms'].items():rows.append(check(dd,joint.build(d,t,arm,t['events']),arm,s,'joint_step_'+label+str(i)))
        d,cov,kind,_=binding.paths.paths.parent(case);record=read(phase_alias.OUT/(case+'.json'))
        for target in record['targets']:grids.extend(phase_grid_check(d,kind,target))
        for i,t in enumerate(record['trials']):
            dd=dict(d,node=t['node'],keep=np.asarray(t['mask'],bool),means=np.asarray(t['means']),entries=t['entries'])
            for arm,s in t['arms'].items():rows.append(check(dd,binding.runner.engine.baseline.build(dd,arm,s['phase_reference']),arm,s,'joint_phase_alias_'+str(i)))
    write(out,dict(rows=rows,phase_grid_checks=grids,all_passed=True,all_original_saved_flags_and_memberships_replayed=True,
        no_new_optimization_or_GPS=True,source_sha256=sha(Path(__file__))))
    print('015 additional endpoint arms',len(rows),'exact-phase grid nominees',len(grids),flush=True)


if __name__=='__main__':main()
