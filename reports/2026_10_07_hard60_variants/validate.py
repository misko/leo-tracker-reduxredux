"""Replay search/selection and recompute selected scores with the original oracle."""
import argparse
from dataclasses import asdict,replace
import numpy as np
import run_variants as run
from rf_model import RFObjective,Domain
from leo.analysis.regional_position_score import PositionObjective
from leo.analysis.regional_position_search import SpatialSearch,distinct_basins


def validate(labels,tag):
    grids=[];audits=[];reuses=[]
    for label in labels:
        expected=run.read(run.CONTROL/'protocol.json')['input_metadata'][label]
        assert run.data.digest(run.OLD/'inputs'/label/'inputs.json')==expected
        _,obs,bank,prior,score=run.data.load(label)
        score=replace(score,relative_sigma_s=2.)
        for phase in run.PHASES:
            folder=run.HERE/'results'/label/phase
            search,result=run.read(folder/'search.json'),run.read(folder/'result.json')
            lookup={(p['east_km'],p['north_km']):p['score'] for p in search['search']['evaluations']}
            replay,meta=run.engine.edge_grid.search(lambda points:[lookup[tuple(p)] for p in points],
                levels=[40.,20.,10.,5.],budget=400,edge_policy='nearest')
            assert asdict(replay)=={**search['search'],'evaluations':tuple(search['search']['evaluations'])}
            assert meta==search['edge'] and len(replay.evaluations)==400
            supported=SpatialSearch(tuple(p for p in replay.evaluations if p.score<1e100),replay.deferred_cells,replay.stop_reason)
            assert [asdict(b) for b in distinct_basins(supported,count=3,minimum_separation_km=12.5)]==result['basins']
            if phase=='two_starts':
                for p in replay.evaluations:
                    row=run.read(folder/'points'/f'{p.east_km:g}_{p.north_km:g}.json')
                    assert 'two_start_runs' in row
                    if row['status']=='complete':
                        assert row['score']==min(r['objective'] for r in row['two_start_runs'])
                        for r in row['two_start_runs']:assert max(abs(np.asarray(r['vector'])[[3,5]]))<=60.+1e-6
                    if row.get('first_start_reuse'):
                        source=row['first_start_reuse'];assert run.data.digest(source['path'])==source['sha256']
            else:
                assert run.data.digest(folder/'search.json')==run.data.digest(run.control_folder(label)/'search.json')
            candidates=[];regions={}
            for b in result['basins']:
                xy=[b['east_km'],b['north_km']];radius=max(25.,b['spacing_km']/np.sqrt(2))
                region=run.read(folder/'regions'/f'{xy[0]:g}_{xy[1]:g}_{radius:g}.json')
                regions[tuple(xy)]=region
                if region['status']=='complete':
                    assert sum(r['arm']=='zero-c' for r in region['runs'])==sum(r['arm']=='fitted-c' for r in region['runs'])==3
                for key in ('reused_source','reused_calibration_source'):
                    if key in region:
                        s=region[key];assert run.data.digest(s['path'])==s['sha256'];reuses.append(s)
                if 'reused_calibration_source' in region:
                    old=run.read(region['reused_calibration_source']['path'])
                    if old['status']=='complete':
                        assert old['calibration']==region['calibration'] and old['association']==region['association']
                for c in region['candidates']:
                    v=np.asarray(c['vector'])
                    assert max(abs(v[[3,5]]))<=60.+1e-6
                    if c['arm']=='zero-c':assert v[6]==0.
                    np.testing.assert_allclose(c['objective'],c['data_nll']+c['timing_penalty']+c.get('rf_penalty',0.),atol=1e-6,rtol=0)
                    np.testing.assert_allclose(c['selection_score'],c['objective']+region['calibration_penalty'],atol=1e-6,rtol=0)
                    candidates.append(dict(c,point=xy,local_radius_km=radius))
            for arm in ('zero-c','fitted-c'):
                pool=[c for c in candidates if c['arm']==arm and c['feasible'] and c['converged']]
                expected=min(pool,key=lambda c:(c['selection_score'],c['point'],c['origin']),default=None)
                assert expected==result['selections'][arm]['result']
                if expected is None:
                    audits.append(dict(label=label,phase=phase,arm=arm,accepted=False));continue
                c=expected;region=regions[tuple(c['point'])]
                subbank=bank.select(region['association']['selected_indices'])
                baseline=np.asarray(region['calibration']['receiver_baseline_hz'])
                vector=np.asarray(c['vector'])
                oracle=PositionObjective(obs,subbank,prior,score,receiver_baseline_hz=baseline)
                if phase=='rf_offsets':
                    wrapped=RFObjective(oracle)
                    np.testing.assert_allclose(wrapped.group_basis,region['rf_group_basis'],atol=1e-12)
                    p=oracle.size;z=vector[p:];q=np.asarray(region['rf_group_basis'])
                    offsets=q@z
                    np.testing.assert_allclose(offsets,c['rf_offsets_hz'],atol=1e-8)
                    assert max(abs(offsets),default=0)<=150.+1e-6
                    np.testing.assert_allclose(oracle.design[:,[0,2,4]].T@wrapped.extra_design,0,atol=1e-8)
                    oracle.baseline=baseline+wrapped.incidence@offsets
                    value,gradient,terms=oracle.evaluate(vector[:p])
                    independent_penalty=.5*sum(float(x)**2 for x in offsets)/50.**2
                    extra=wrapped.extra_design.T@terms.prediction_gradient.sum(axis=1)+z/50.**2
                    gradient=np.r_[gradient,extra]
                    checked=Domain(wrapped,vector,arm,c['point'],c['local_radius_km']).audit(vector,gradient)
                    value+=independent_penalty
                    np.testing.assert_allclose(independent_penalty,c['rf_penalty'],atol=1e-8,rtol=0)
                else:
                    value,gradient,terms=oracle.evaluate(vector)
                    checked=run.engine.audit(oracle,vector,gradient,arm,c['point'],c['local_radius_km'],60.)
                np.testing.assert_allclose(value,c['objective'],atol=1e-6,rtol=0)
                np.testing.assert_allclose(terms.nll,c['data_nll'],atol=1e-6,rtol=0)
                assert checked['converged'] and checked['feasible']
                audits.append(dict(label=label,phase=phase,arm=arm,accepted=True,**checked))
            grids.append(dict(label=label,phase=phase,points=400))
        print('VERIFIED',label,flush=True)
    for path in run.HERE.glob('protocol_*.json'):
        for source,expected in run.read(path).get('sources',{}).items():assert run.data.digest(source)==expected,source
    for root in (run.CONTROL,run.SOFT):
        for name,expected in run.read(root/'artifact_manifest.json')['files'].items():assert run.data.digest(root/name)==expected,name
    out=dict(all_checks_passed=True,grids=grids,selected_original_oracle_audits=audits,verified_reuse_count=len(reuses))
    run.engine.write(run.HERE/f'validation_{tag}.json',out)
    print('PASS',len(grids),'grid replays;',len(audits),'selection and original-oracle checks',flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--labels',nargs='+',default=run.LABELS)
    parser.add_argument('--tag',default='full');args=parser.parse_args()
    validate(args.labels,args.tag)
