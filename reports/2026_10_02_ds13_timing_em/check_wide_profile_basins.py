"""Check wide-probe support-collapse basins with <=500 m continuation steps."""
import copy
import json
from pathlib import Path
import numpy as np
from curvature_position_profile import ROOT
from extend_position_profile_3km import plot


def run():
    from all_visible_bank import load_expanded_scan
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from position_profile_grid import geodesic_position,run_profile
    from finite_set_fit import snapshot_files,assert_snapshot_unchanged
    from plot_all_glrt_doppler_overlay import serializable
    source=ROOT/'curvature-filter-roof-profile-3km';near=ROOT/'curvature-filter-roof-profile'
    output=ROOT/'curvature-filter-roof-profile-3km-checked';output.mkdir(exist_ok=False)
    receipt=json.loads((source/'receipt.json').read_text());assert_snapshot_unchanged(receipt['source_hashes'])
    latest=json.loads((ROOT/'later-tle-timing-aligned-v2/receipt.json').read_text())
    catalogue=parse_element_sets(Path(latest['latest_snapshot']['path']).read_text())
    lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    hashes=snapshot_files([__file__,source/'receipt.json']);checks=[]
    def save(name,value):
        (output/name).write_text(json.dumps(serializable(value),indent=2,allow_nan=False)+'\n')
    for result in receipt['results']:
        label=result['scan'];session=result['session'];lat,lon=result['roof_lat_lon'];data=None
        for variant in ('unfiltered','filtered'):
            if variant=='filtered' and result['variants'][variant].get('identical_to_unfiltered'):
                result['variants'][variant]=copy.deepcopy(result['variants']['unfiltered'])
                result['variants'][variant]['identical_to_unfiltered']=True;continue
            item=result['variants'][variant]
            roof_path=near/f'{label}-{variant}-roof.json';hashes.update(snapshot_files([roof_path]));roof=json.loads(roof_path.read_text())
            support=np.array(roof['satellite_support'])
            targets=[c for c in item['cells'] if c['label'].startswith('wide') and
                     (c['delta_score']>300 or np.any((support>50)&(np.array(c['support'])<.5*support)))]
            if not targets:continue
            if data is None:
                data=load_expanded_scan(session);numbers=result['variants']['unfiltered']['candidates']
                sats=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in numbers]);indices=[lookup[int(n)] for n in numbers]
                origin=next(s['origin_utc_ns'] for s in latest['scans'] if s['scan']==label)
                p,v,valid=propagate_candidate_states(catalogue,indices,origin,data.nodes,np.array([0.]))
                assert list(valid)==indices
                data=copy.copy(data);data.position=data.position.copy();data.velocity=data.velocity.copy()
                data.position[sats]=p[:,0];data.velocity[sats]=v[:,0]
            chosen=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in item['candidates']])
            for cell in targets:
                start=roof;steps=int(np.ceil(np.hypot(cell['east_m'],cell['north_m'])/500));record=[]
                for step in range(1,steps+1):
                    e,n=np.array([cell['east_m'],cell['north_m']])*step/steps
                    pos=geodesic_position(lat,lon,np.degrees(np.arctan2(e,n)),np.hypot(e,n));vector=None
                    for attempt in range(5):
                        fit=run_profile(data,start['parameters'],chosen,start['rf_coefficient_hz_per_ghz'],pos,
                            probability_override=roof['detection_probability'],start_vector=vector,budget_s=8.)
                        vector=fit['vector']
                        if fit['success']:break
                    assert fit['success'],'continuation did not converge'
                    save(f"{label}-{variant}-{cell['label']}-step-{step}.json",fit)
                    record.append(dict(step=step,east_m=e,north_m=n,objective=fit['objective']))
                    start=fit
                    print(label,variant,cell['label'],step,'/',steps,'delta',round(fit['objective']-roof['objective'],3),flush=True)
                old=cell['objective']
                if fit['objective']<old:
                    cell.update(objective=fit['objective'],delta_score=fit['objective']-roof['objective'],
                        data_nll=fit['data_nll'],prior_nll=fit['nuisance_prior_nll'],success=fit['success'],
                        nuisance_gradient=fit['projected_nuisance_gradient_inf_norm'],support=fit['satellite_support'])
                checks.append(dict(scan=label,variant=variant,label=cell['label'],original_score=old,
                    continuation_score=fit['objective'],improvement=old-cell['objective'],steps=record))
                save('checks-partial.json',checks)
            item['best']=min(item['cells'],key=lambda c:c['objective'])
    for variant,item in receipt['combined'].items():
        for i,c in enumerate(item['cells']):
            pair=[r['variants'][variant]['cells'][i] for r in receipt['results']]
            c['objective']=sum(v['objective'] for v in pair);c['delta_score']=sum(v['delta_score'] for v in pair)
        item['best']=min(item['cells'],key=lambda c:c['objective'])
    assert_snapshot_unchanged(hashes)
    receipt['basin_checks']=checks;receipt['source_hashes']=hashes
    receipt['scope']+=' Support-collapse/high-loss wide probes additionally checked using <=500m position continuation; lower converged result retained. Still not a global optimization guarantee.'
    save('receipt.json',receipt);plot(output,receipt)
    import csv
    rows=[dict(scan=r['scan'],variant=v,**{k:c[k] for k in ('label','east_m','north_m','objective','delta_score')})
          for r in receipt['results'] for v,item in r['variants'].items() for c in item['cells']]
    rows += [dict(scan='combined',variant=v,**c) for v,item in receipt['combined'].items() for c in item['cells']]
    with (output/'scores.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(serializable(rows))
    print('BEST',json.dumps(serializable({v:i['best'] for v,i in receipt['combined'].items()})),flush=True)


if __name__=='__main__':run()
