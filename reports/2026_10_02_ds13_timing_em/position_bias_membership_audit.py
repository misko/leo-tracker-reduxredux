"""Separate final-track groups from other likelihood evidence; audit screen coverage."""
import copy
import json
from pathlib import Path
import numpy as np
from curvature_position_profile import ROOT,finite_difference
from position_bias_contributors import contributions


def run():
    from all_visible_bank import load_expanded_scan
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from later_tle_comparison import predict
    from rf_calibration_diagnostic import CalibrationObjective
    from position_profile_grid import geodesic_position,run_profile
    from plot_all_glrt_doppler_overlay import serializable
    from finite_set_fit import snapshot_files,assert_snapshot_unchanged
    source=ROOT/'curvature-filter-roof-profile'
    parent=json.loads((source/'receipt.json').read_text())
    latest=json.loads((ROOT/'later-tle-timing-aligned-v2/receipt.json').read_text())
    catalogue=parse_element_sets(Path(latest['latest_snapshot']['path']).read_text())
    lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    output=ROOT/'position-bias-membership-audit';output.mkdir(exist_ok=False)
    hashes=snapshot_files([__file__,source/'receipt.json',ROOT/'later-tle-timing-aligned-v2/receipt.json'])
    assert_snapshot_unchanged(parent['source_hashes'])
    g=np.array(parent['combined']['filtered']['derivatives'][0]['gradient_score_per_m']);unit=g/np.linalg.norm(g)
    results=[]
    for scan in parent['results']:
        label=scan['scan'];session=scan['session'];lat,lon=scan['roof_lat_lon']
        data=load_expanded_scan(session)
        original=next(s for s in latest['scans'] if s['scan']==label)
        numbers=scan['variants']['filtered']['candidates']
        selected=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in numbers])
        indices=[lookup[int(n)] for n in numbers]
        p,v,valid=propagate_candidate_states(catalogue,indices,original['origin_utc_ns'],data.nodes,np.array([0.]))
        assert list(valid)==indices
        data=copy.copy(data);data.position=data.position.copy();data.velocity=data.velocity.copy()
        data.position[selected]=p[:,0];data.velocity[selected]=v[:,0]
        variant='unfiltered' if scan['variants']['filtered'].get('identical_to_unfiltered') else 'filtered'
        def read(name):
            path=source/f'{label}-{variant}-{name}.json';hashes.update(snapshot_files([path]));return json.loads(path.read_text())
        fit=read('roof');objective=CalibrationObjective(data,np.array(fit['parameters']),selected,False,8.)
        objective.base.deadline=float('inf');objective.likelihood.detection_probability=fit['detection_probability']
        value,_=objective.evaluate(np.array(fit['vector']));assert abs(value-fit['objective'])<1e-7
        weights=-objective.likelihood.last_result['prediction_gradient'].copy()
        support=objective.likelihood.last_result['row_association_probability'].copy()
        derivatives=[]
        for plus,minus in (('E+50N+0','E-50N+0'),('E+0N+50','E+0N-50')):
            hi,lo=read(plus),read(minus)
            derivatives.append((predict(data,hi['parameters'],selected,hi['rf_coefficient_hz_per_ghz'])-
                                predict(data,lo['parameters'],selected,lo['rf_coefficient_hz_per_ghz']))/100.)
        terms=contributions(weights,np.stack(derivatives,axis=-1))
        records=[]
        for j,number in enumerate(numbers):
            tracks=[t for t in latest['tracks'] if t['scan']==label and t['catalog_number']==number]
            for rx in (0,1):
                peer=[t for t in tracks if t['receiver']==rx]
                final_rows=np.concatenate([t['rows'] for t in peer]).astype(int) if peer else np.array([],int)
                groups=np.unique(data.group[final_rows])
                in_final=np.isin(data.group,groups)&(data.receiver==rx)
                for name,m in (('final_track_groups',in_final),('other_groups',(data.receiver==rx)&~in_final)):
                    grad=terms[m,j].sum(axis=0)
                    records.append(dict(satellite=number,receiver=rx,subset=name,east=grad[0],north=grad[1],
                        downhill_pressure=float(grad@unit),support=float(support[m,j].sum()),
                        final_track_present=bool(peer)))
        result=dict(scan=label,unassessed_candidates=sorted(set(numbers)-{t['catalog_number'] for t in scan['tracks']}),rows=records)
        print(label,'unassessed',result['unassessed_candidates'],flush=True)
        results.append(result)
        if label=='B':
            driver=62739
            chosen=selected[data.numbers[selected]!=driver];cells=[];center=None
            for e,n in ((0.,0.),(50.,0.),(-50.,0.),(0.,50.),(0.,-50.)):
                pos=geodesic_position(lat,lon,np.degrees(np.arctan2(e,n)),np.hypot(e,n))
                start=fit if center is None else center;vector=None
                for attempt in range(5):
                    fitted=run_profile(data,start['parameters'],chosen,start['rf_coefficient_hz_per_ghz'],pos,
                        probability_override=fit['detection_probability'],start_vector=vector,budget_s=8.)
                    vector=fitted['vector']
                    if fitted['success']:break
                assert fitted['success']
                if center is None:center=fitted
                (output/f'B-without-62739-E{e:+g}N{n:+g}.json').write_text(json.dumps(serializable(fitted),indent=2))
                cells.append(dict(east_m=e,north_m=n,objective=fitted['objective']))
                print('B without 62739',e,n,fitted['objective']-center['objective'],flush=True)
            result['ablation']=dict(removed=62739,cells=cells,derivative=finite_difference(cells,50.))
        (output/'partial.json').write_text(json.dumps(serializable(results),indent=2))
    assert_snapshot_unchanged(hashes)
    (output/'receipt.json').write_text(json.dumps(serializable(dict(results=results,source_hashes=hashes,
        scope='Final membership means every alias row in a final track group, not just its chosen peak. '
        'Other groups are not automatically spurious; includes valid support excluded by track extraction. '
        'Curvature diagnostic coverage is audited explicitly; absent candidates were not assessed, not passed.')),indent=2))


if __name__=='__main__':run()
