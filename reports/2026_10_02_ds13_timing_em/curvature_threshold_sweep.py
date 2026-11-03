"""Stricter frozen curvature screens: roof gradients and multistart minima."""
import copy
import csv
import json
import time
from pathlib import Path
import numpy as np
from curvature_position_profile import ROOT,excluded_satellites
from find_profile_minimum import best_unique_fits,local_offset

THRESHOLDS=(1.075,1.05,1.025)


def screen(numbers,tracks,threshold):
    excluded=excluded_satellites(tracks,threshold)
    assessed={t['catalog_number'] for t in tracks if t['ratio'] is not None}
    return dict(kept=[int(n) for n in numbers if n not in excluded],excluded=excluded,
                unassessed=sorted(set(numbers)-assessed))


def run():
    from all_visible_bank import load_expanded_scan
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from position_profile_grid import geodesic_position,run_profile
    from joint_inputs import _coordinates
    from finite_set_fit import snapshot_files,assert_snapshot_unchanged
    from plot_all_glrt_doppler_overlay import serializable
    from scipy.optimize import minimize
    started=time.monotonic();output=ROOT/'curvature-threshold-sweep';output.mkdir(exist_ok=False)
    near=ROOT/'curvature-filter-roof-profile';dense=ROOT/'dense-profile-minimum-v2'
    parent=json.loads((near/'receipt.json').read_text());minimum=json.loads((dense/'receipt.json').read_text())
    assert_snapshot_unchanged(parent['source_hashes']);assert_snapshot_unchanged(minimum['source_hashes'])
    latest_path=ROOT/'later-tle-timing-aligned-v2/receipt.json';latest=json.loads(latest_path.read_text())
    tle=Path(latest['latest_snapshot']['path']);catalogue=parse_element_sets(tle.read_text())
    lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    hashes=snapshot_files([__file__,near/'receipt.json',dense/'receipt.json',latest_path,tle])
    def save(name,value):
        (output/name).write_text(json.dumps(serializable(value),indent=2,allow_nan=False)+'\n')
    lat,lon=parent['results'][0]['roof_lat_lon'];center=geodesic_position(lat,lon,0.,0.)
    # Convert gradient in regional-map km to local east/north score per 100 m.
    jac=np.column_stack([(geodesic_position(lat,lon,b,1.)-geodesic_position(lat,lon,b+180,1.))/2 for b in (90.,0.)])*100
    loaded={};original_roof={};cache={};evaluations=[];results=[]
    for scan in parent['results']:
        label=scan['scan'];data=load_expanded_scan(scan['session'])
        sats=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in scan['variants']['unfiltered']['candidates']])
        indices=[lookup[int(data.numbers[s])] for s in sats]
        origin=next(s['origin_utc_ns'] for s in latest['scans'] if s['scan']==label)
        p,v,valid=propagate_candidate_states(catalogue,indices,origin,data.nodes,np.array([0.]))
        assert list(valid)==indices
        data=copy.copy(data);data.position=data.position.copy();data.velocity=data.velocity.copy()
        data.position[sats]=p[:,0];data.velocity[sats]=v[:,0];loaded[label]=data
        path=near/f'{label}-unfiltered-roof.json';hashes.update(snapshot_files([path]));original_roof[label]=json.loads(path.read_text())
        # B is unchanged at the first stricter threshold: reuse verified fits.
        if label=='B':
            bank=[]
            for row in minimum['evaluations']:
                if row['scan']!='B':continue
                path=dense/f"fit-{row['index']:04d}.json";hashes.update(snapshot_files([path]));bank.append(json.loads(path.read_text()))
            bank.append(original_roof[label])
            key=(label,tuple(scan['variants']['unfiltered']['candidates']))
            cache[key]=dict(chosen=sats,bank=best_unique_fits(bank),roof=original_roof[label])
    previous=np.array(minimum['minima']['filtered']['best']['position_km'])
    for threshold in THRESHOLDS:
        tag=str(threshold);policies={};keys={}
        for scan in parent['results']:
            label=scan['scan'];policy=screen(scan['variants']['unfiltered']['candidates'],scan['tracks'],threshold)
            policies[label]=policy;key=(label,tuple(policy['kept']));keys[label]=key
            if not policy['kept']:raise ValueError('no candidates remain')
            if key not in cache:
                chosen=np.array([int(np.flatnonzero(loaded[label].numbers==n)[0]) for n in policy['kept']])
                cache[key]=dict(chosen=chosen,bank=[],roof=None)
            print('SCREEN',threshold,label,policy,flush=True)
        def profile(label,position):
            item=cache[keys[label]]
            nearest=min(item['bank'],key=lambda f:np.linalg.norm(np.array(f['parameters'][:2])-position)) if item['bank'] else original_roof[label]
            if item['bank'] and np.linalg.norm(np.array(nearest['parameters'][:2])-position)<1e-9:return nearest
            vector=None
            for attempt in range(5):
                fit=run_profile(loaded[label],nearest['parameters'],item['chosen'],nearest['rf_coefficient_hz_per_ghz'],position,
                    probability_override=original_roof[label]['detection_probability'],start_vector=vector,budget_s=8.)
                vector=fit['vector']
                if fit['success']:break
            if not fit['success']:raise RuntimeError(f'Unconverged {tag} {label}')
            item['bank'].append(fit)
            en=local_offset(lat,lon,*_coordinates(position));idx=len(evaluations)
            evaluations.append(dict(index=idx,threshold=threshold,scan=label,east_m=en[0],north_m=en[1],
                                    position_km=position,objective=fit['objective']))
            save(f'fit-{idx:04d}.json',fit);save('evaluations.json',evaluations)
            return fit
        roofs={label:profile(label,center) for label in ('A','B')}
        for label,fit in roofs.items():cache[keys[label]]['roof']=fit;save(f'{tag}-{label}-roof.json',fit)
        roof_score=sum(f['objective'] for f in roofs.values())
        roof_gradients={label:np.asarray(fit['free_position_gradient'])@jac for label,fit in roofs.items()}
        roof_gradient=sum(roof_gradients.values())
        support={label:float(sum(f['satellite_support'])) for label,f in roofs.items()}
        print('ROOF',threshold,'gradient /100m',roof_gradient,'support',support,flush=True)
        def combined(position):
            fits=[profile(label,position) for label in ('A','B')]
            return sum(f['objective'] for f in fits),np.sum([f['free_position_gradient'] for f in fits],axis=0)
        # Roof finite-difference check on local EN, using frozen exclusions.
        cardinal=[]
        for bearing in (90.,270.,0.,180.):
            value,_=combined(geodesic_position(lat,lon,bearing,50.))
            cardinal.append(value-roof_score)
        finite_gradient=np.array([cardinal[0]-cardinal[1],cardinal[2]-cardinal[3]])
        np.testing.assert_allclose(finite_gradient,roof_gradient,rtol=.02,atol=.005)
        # Warm the old minimum with <=500m steps for this new candidate subset.
        for fraction in np.linspace(0,1,int(np.ceil(np.linalg.norm(previous-center)/.5))+1)[1:]:
            combined(center+fraction*(previous-center))
        attempts=[]
        for start_index,start in enumerate((center,previous)):
            def scaled(position):
                value,g=combined(position)
                return (value-roof_score)/50.,g/50.
            res=minimize(scaled,start,jac=True,method='L-BFGS-B',bounds=[(c-5,c+5) for c in center],
                options=dict(ftol=1e-12,gtol=2e-5,maxiter=35,maxls=12))
            value,g=combined(res.x);en=local_offset(lat,lon,*_coordinates(res.x))
            record=dict(start=start_index,position_km=res.x,east_m=en[0],north_m=en[1],objective=value,
                delta_score=value-roof_score,gradient_score_per_km=g,success=bool(res.success),message=str(res.message))
            attempts.append(record);save(f'{tag}-optimization.json',attempts)
            print('MINIMUM',threshold,serializable(record),flush=True)
        best=min(attempts,key=lambda a:a['objective']);position=np.array(best['position_km']);h=.05;neighbors=[]
        for dx,dy in ((h,0),(-h,0),(0,h),(0,-h),(h,h),(h,-h),(-h,h),(-h,-h)):
            value,_=combined(position+np.array([dx,dy]))
            neighbors.append(dict(dx_km=dx,dy_km=dy,delta=value-best['objective']))
        vals={(r['dx_km'],r['dy_km']):r['delta'] for r in neighbors}
        cross=(vals[h,h]-vals[h,-h]-vals[-h,h]+vals[-h,-h])/(4*h*h)
        hessian=np.array([[(vals[h,0]+vals[-h,0])/h**2,cross],[cross,(vals[0,h]+vals[0,-h])/h**2]])
        row=dict(threshold=threshold,policies=policies,roof_score=roof_score,roof_gradient_per_100m=roof_gradient,
            roof_gradients_by_scan=roof_gradients,roof_finite_difference_per_100m=finite_gradient,
            roof_effective_support=support,best=best,attempts=attempts,neighbors=neighbors,
            hessian_eigenvalues=np.linalg.eigvalsh(hessian),hessian_score_per_km2=hessian,
            distance_m=float(np.hypot(best['east_m'],best['north_m'])),
            start_agreement_m=float(np.linalg.norm(np.array(attempts[0]['position_km'])-attempts[1]['position_km'])*1000))
        results.append(row);save('partial.json',results);previous=position
    baselines=[]
    for variant,threshold in (('unfiltered',None),('filtered',1.1)):
        m=minimum['minima'][variant];policies={};support={}
        for scan in parent['results']:
            label=scan['scan'];policies[label]=screen(scan['variants']['unfiltered']['candidates'],scan['tracks'],threshold)
            actual='unfiltered' if scan['variants'][variant].get('identical_to_unfiltered') else variant
            path=near/f'{label}-{actual}-roof.json';hashes.update(snapshot_files([path]));fit=json.loads(path.read_text())
            support[label]=sum(fit['satellite_support'])
        baselines.append(dict(threshold=threshold,policies=policies,
            roof_gradient_per_100m=np.asarray(parent['combined'][variant]['derivatives'][0]['gradient_score_per_m'])*100,
            roof_effective_support=support,best=dict(**m['best'],delta_score=m['delta_score']),
            distance_m=float(np.hypot(m['best']['east_m'],m['best']['north_m'])),
            hessian_eigenvalues=m['hessian_eigenvalues'],start_agreement_m=m['start_agreement_m']))
    assert_snapshot_unchanged(hashes)
    receipt=dict(results=baselines+results,source_hashes=hashes,elapsed_s=time.monotonic()-started,
        scope='Strict > threshold applied once to max assessed RX ratio per satellite within scan, from the unchanged '
        'unfiltered correct-roof fit and frozen final points. Ratios not recomputed after culling. '
        'B62739 remains explicitly unassessed/retained. Full original GLRT group likelihood retained; per-candidate '
        'detection probability unchanged. Every site refits independent per-scan timing/RX/RF nuisance with original priors. '
        'Compare each model against its own roof score, not absolute scores across candidate subsets. '
        'Combined position locally optimized from roof and prior-cutoff minimum, safety bounds +/-5 regional km. '
        'Curvature and support loss reported; smaller gradient alone is not proof of improved localization. '
        'Threshold sensitivity at known site is in-sample diagnostics, not selection of a validated cutoff.')
    save('receipt.json',receipt)
    rows=[]
    for r in receipt['results']:
        rows.append(dict(threshold='off' if r['threshold'] is None else r['threshold'],
            A_retained=len(r['policies']['A']['kept']),B_retained=len(r['policies']['B']['kept']),
            east_m=r['best']['east_m'],north_m=r['best']['north_m'],distance_m=r['distance_m'],
            delta_score=r['best']['delta_score'],roof_gradient_norm_per_100m=float(np.linalg.norm(r['roof_gradient_per_100m'])),
            effective_support=sum(r['roof_effective_support'].values()),minimum_curvature=min(r['hessian_eigenvalues'])))
    with (output/'summary.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(serializable(rows))
    plot(output,receipt)


def plot(output,receipt):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    rows=receipt['results'];labels=['Off' if r['threshold'] is None else str(r['threshold']) for r in rows]
    colors=['.5','#0072B2','#E69F00','#009E73','#CC79A7'];fig,axes=plt.subplots(1,3,figsize=(15,5))
    for r,label,color in zip(rows,labels,colors):
        axes[0].scatter(r['best']['east_m']/1000,r['best']['north_m']/1000,s=90,color=color,label=label)
    axes[0].plot(0,0,'k+',ms=15,mew=2,label='Roof');axes[0].set_xlabel('East of roof (km)');axes[0].set_ylabel('North of roof (km)')
    axes[0].set_title('Optimized combined-score location');axes[0].legend(title='Ratio cutoff',fontsize=8);axes[0].grid(alpha=.2);axes[0].set_aspect('equal',adjustable='datalim')
    axes[1].bar(labels,[r['distance_m']/1000 for r in rows],color=colors)
    axes[1].set_title('Distance of minimum from roof');axes[1].set_ylabel('km');axes[1].set_xlabel('Stricter ratio cutoff →')
    for i,r in enumerate(rows):axes[1].text(i,r['distance_m']/1000+.03,f"{r['distance_m']/1000:.2f}",ha='center',fontsize=9)
    axes[2].bar(labels,[np.linalg.norm(r['roof_gradient_per_100m']) for r in rows],color=colors)
    axes[2].set_title('Score-gradient magnitude at roof');axes[2].set_ylabel('Score per 100 m');axes[2].set_xlabel('Stricter ratio cutoff →')
    for ax in axes[1:]:ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True)
    fig.suptitle('DS13 · does stricter linear/quadratic RMS filtering reduce position bias?',fontsize=15)
    counts=', '.join(f"{label}: {len(r['policies']['A']['kept'])}+{len(r['policies']['B']['kept'])}" for label,r in zip(labels,rows))
    fig.text(.5,.025,'Retained candidates A+B — '+counts+'\nRatios/exclusions frozen at roof. B · 62739 unassessed and retained. Local minima; no held-out validation.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.13,1,.90));fig.savefig(output/'threshold-comparison.png',dpi=170);plt.close(fig)


if __name__=='__main__':run()
