"""Pure posterior-weighted satellite/RX geometry labels, independent of fitting.

Call separately for receive-time, fitted-orbit-time and reference-position
directions. Responsibilities remain tied to their labeled inference model.
"""
import numpy as np

def geometry_flags(unit_enu,theta,frames):
    """Input NxKx3 unit directions; output flag/angle arrays NxKx2(RX)."""
    unit=np.asarray(unit_enu,float);theta=np.asarray(theta,float);frames=np.asarray(frames,float)
    if unit.ndim!=3 or unit.shape[2]!=3 or frames.shape!=(2,3,3) or theta.shape!=(5,):raise ValueError('expected NxKx3 directions,5 cone parameters,2x3x3 frames')
    if not np.allclose(np.linalg.norm(unit,axis=2),1,atol=1e-7):raise ValueError('directions must be normalized')
    projected=np.einsum('nkj,rqj->nkrq',unit,frames)
    p,q,z=np.moveaxis(projected,-1,0);roll=theta[3:];x=p*np.cos(roll)+q*np.sin(roll);y=-p*np.sin(roll)+q*np.cos(roll)
    margin=z-np.sqrt((x/np.tan(theta[0]))**2+(y/np.tan(theta[1]))**2+1e-24)
    angle=np.degrees(np.arccos(np.clip(z,-1,1)))
    opposite=np.stack((unit[:,:,0]>1e-12,unit[:,:,0]<-1e-12),axis=-1)
    return dict(opposite_east_west=opposite,behind_nominal_boresight=z<-1e-12,outside_empirical_ellipse=margin<0,nearer_other_receiver_axis=angle>angle[:,:,::-1]+1e-10,below_horizon=np.broadcast_to(unit[:,:,2,None]<0,z.shape),nominal_angle_deg=angle,ellipse_margin=margin)

def mark_arrays(unit_enu,numbers,receiver,weights,theta,frames,scenario):
    """Aggregate per satellite/RX for one clearly labeled geometry scenario."""
    unit_enu=np.asarray(unit_enu,float);flags=geometry_flags(unit_enu,theta,frames);weights=np.asarray(weights,float);receiver=np.asarray(receiver)
    if weights.shape!=unit_enu.shape[:2] or receiver.shape!=(len(weights),):raise ValueError('responsibility/receiver dimensions differ')
    if np.any(weights<0) or not np.isfinite(weights).all():raise ValueError('finite nonnegative weights required')
    result=[]
    for j,number in enumerate(numbers):
        for rx in (0,1):
            mask=receiver==rx;mass=float(weights[mask,j].sum())
            row=dict(scenario=scenario,satellite=int(number),receiver=rx,windows=int(mask.sum()),signal_mass=mass,mapping_provisional=True,elevation_nominal_not_measured=True,cone_empirical_not_hardware=True)
            row['hard_winner_rows']=int(np.sum(weights[mask,j]>=.5))
            if mass:
                row['weighted_mean_angle_deg']=float(weights[mask,j]@flags['nominal_angle_deg'][mask,j,rx]/mass)
                for name in ('opposite_east_west','behind_nominal_boresight','outside_empirical_ellipse','nearer_other_receiver_axis','below_horizon'):
                    value=float(weights[mask,j]@flags[name][mask,j,rx]);row[name+'_mass']=value;row[name+'_fraction']=value/mass
            else:
                row['weighted_mean_angle_deg']=None
                for name in ('opposite_east_west','behind_nominal_boresight','outside_empirical_ellipse','nearer_other_receiver_axis','below_horizon'):row[name+'_mass']=0.;row[name+'_fraction']=None
            result.append(row)
    return result

def mark_case(case_doc_path):
    """Read completed runner selections, reconstruct source and write geometry only."""
    import csv,json,importlib.util
    from dataclasses import replace
    from pathlib import Path
    from leo.contracts.regional_position import PositionScore
    here=Path(__file__).resolve().parent;cones=here.parent;reports=cones.parent
    def load_module(name,path):
        spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
    oracle=load_module('marker_oracle',reports/'2026_10_07_sigma1_root_cause/oracle.py')
    cone=load_module('marker_cone',cones/'cone_objective.py')
    case_doc_path=Path(case_doc_path);case=case_doc_path.parent.name;receipt=json.loads(case_doc_path.read_text())
    if not receipt.get('selections'):raise ValueError('runner has not saved selections')
    if receipt.get('status')!='complete':raise ValueError('mark only completed selected receipts')
    doc,old,obs,prior,bank,checkpoint,prefix=oracle.load(case);theta,frames,support=cone.cone_bundle();rows=[];audits=[];plotdata=dict(theta=theta,frames=frames,receiver=obs.receiver,times_s=obs.times_s)
    for selected in receipt['selections']:
        option=selected['option'];strength={'control':0.,'cone050':.5,'cone100':1.}[option];basin=selected['basin']
        assoc=checkpoint.get(prefix+':'+basin+':association')['result'];cal=checkpoint.get(prefix+':'+basin+':calibration')['result'];subbank=bank.select(assoc['selected_indices']);assert subbank.numbers.tolist()==receipt['basins'][basin]['numbers']
        objective=cone.ConeObjective(obs,subbank,prior,replace(PositionScore(**doc['configuration']['scores']['V16']),relative_sigma_s=1.),receiver_baseline_hz=np.asarray(cal['receiver_baseline_hz']),strength=strength,theta=theta,frames=frames,support=support)
        vector=np.asarray(selected['vector']);value,_,terms=objective.evaluate(vector)
        if 'objective' in selected:assert abs(value-selected['objective'])<1e-6
        weights=terms.responsibilities
        for location in ('selected','reference-diagnostic'):
            for timing in ('fitted-orbit-time','receive-time'):
                trial=vector.copy()
                if location=='reference-diagnostic':trial[:2]=oracle.reference_point(prior,doc['reference_latitude_deg'],doc['reference_longitude_deg'])
                if timing=='receive-time':trial[7:]=0
                unit=cone.directions(subbank,obs,prior,trial,objective.basis,derivatives=False)
                if isinstance(unit,tuple):unit=unit[0]
                if location=='reference-diagnostic' and timing=='receive-time' and selected['arm']=='fitted-c' and option in ('control','cone100'):
                    plotdata[option+'_unit']=unit;plotdata[option+'_weights']=weights;plotdata[option+'_numbers']=subbank.numbers
                scenario=location+':'+timing;marked=mark_arrays(unit,subbank.numbers,obs.receiver,weights,theta,frames,scenario)
                empirical,_=support.evaluate(unit)
                for row in marked:
                    j=int(np.flatnonzero(subbank.numbers==row['satellite'])[0]);mask=obs.receiver==row['receiver'];mass=row['signal_mass'];row.update(case=case,option=option,arm=selected['arm'],basin=basin,weights_source=option+':'+selected['arm']+':selected-fit',reference_used_only_for_geometry=location=='reference-diagnostic')
                    row['weighted_empirical_support']=float(weights[mask,j]@empirical[mask,j]/mass) if mass else None
                    row['empirical_support_neutral_mass']=float(weights[mask,j]@(empirical[mask,j]<=1e-12));row['empirical_support_neutral_fraction']=row['empirical_support_neutral_mass']/mass if mass else None
                    row['selected_fit_converged']=selected.get('converged');row['selected_fit_stationarity']=selected.get('stationarity');row['selected_fit_boundary']=selected.get('boundary')
                rows.extend(marked)
        audits.append(dict(option=option,arm=selected['arm'],basin=basin,objective_repriced=value,signal_mass=float(weights.sum()),converged=selected.get('converged'),stationarity=selected.get('stationarity'),boundary=selected.get('boundary')))
    with (here/('markers-'+case+'.csv')).open('w') as f:
        writer=csv.DictWriter(f,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    authority=json.loads((here/'geometry.json').read_text());binding=authority['captures'][doc['session_id']]
    assert binding['input_sha256']==doc['input_manifest_sha256'];assert binding['analysis_sha256']==doc['analysis_manifest_sha256']
    summary=dict(case=case,selected_receipt_path=str(case_doc_path),session_id=doc['session_id'],source_binding=binding,geometry_uncertainty=dict(mapping_provisional=True,elevation_nominal_not_measured=True,cone_empirical_not_hardware=True),audits=audits,scenarios={},examples={})
    for option in ('control','cone050','cone100'):
        for arm in ('fitted-c','zero-c'):
            for scenario in sorted({r['scenario'] for r in rows}):
                group=[r for r in rows if r['option']==option and r['arm']==arm and r['scenario']==scenario];mass=sum(r['signal_mass'] for r in group);key=option+':'+arm+':'+scenario
                names=('opposite_east_west','behind_nominal_boresight','outside_empirical_ellipse','nearer_other_receiver_axis','below_horizon')
                summary['scenarios'][key]=dict(signal_mass=mass,weighted_empirical_support=sum(r['signal_mass']*(r['weighted_empirical_support'] or 0) for r in group)/mass if mass else None,empirical_support_neutral_fraction=sum(r['empirical_support_neutral_mass'] for r in group)/mass if mass else None,**{name+'_fraction':sum(r[name+'_mass'] for r in group)/mass if mass else None for name in names})
                summary['examples'][key]={name:sorted((r for r in group if r['signal_mass']>=10 and r[name+'_fraction']>.5),key=lambda r:r[name+'_mass'],reverse=True)[:12] for name in names}
    np.savez_compressed(here/('plotdata-'+case+'.npz'),**plotdata)
    (here/('markers-'+case+'.json')).write_text(json.dumps(summary,indent=2));return summary

if __name__=='__main__':
    import argparse
    from pathlib import Path
    parser=argparse.ArgumentParser();parser.add_argument('--case',choices=('1939','2139'),required=True);args=parser.parse_args()
    result=mark_case(Path(__file__).resolve().parent.parent/args.case/'polished.json')
    print(result['case'],len(result['audits']),'selected fits marked; no fitting performed')
