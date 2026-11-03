"""Denser southern probes and multistart profiled optimization; research only."""
import copy
import json
import time
from pathlib import Path
import numpy as np
from curvature_position_profile import ROOT


def southern_grid():
    return [(float(e),float(n)) for n in (-2700,-1900,-1100,-300) for e in (-1200,-400,400,1200)]


def best_unique_fits(bank):
    unique={}
    for fit in bank:
        key=tuple(np.round(fit['parameters'][:2],8))
        if key not in unique or fit['objective']<unique[key]['objective']:
            unique[key]=fit
    return list(unique.values())


def local_offset(lat,lon,target_lat,target_lon):
    a,b,c,d=np.deg2rad([lat,lon,target_lat,target_lon]);dl=d-b
    east=np.cos(c)*np.sin(dl)
    north=np.cos(a)*np.sin(c)-np.sin(a)*np.cos(c)*np.cos(dl)
    angle=np.arctan2(np.hypot(east,north),np.sin(a)*np.sin(c)+np.cos(a)*np.cos(c)*np.cos(dl))
    bearing=np.arctan2(east,north)
    return 6371008.8*angle*np.array([np.sin(bearing),np.cos(bearing)])


def run():
    from all_visible_bank import load_expanded_scan
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from position_profile_grid import geodesic_position,run_profile
    from joint_inputs import _coordinates
    from finite_set_fit import snapshot_files,assert_snapshot_unchanged
    from plot_all_glrt_doppler_overlay import serializable
    from scipy.optimize import minimize
    source=ROOT/'curvature-filter-roof-profile-3km-checked'
    parent=json.loads((source/'receipt.json').read_text());assert_snapshot_unchanged(parent['source_hashes'])
    latest_path=ROOT/'later-tle-timing-aligned-v2/receipt.json';latest=json.loads(latest_path.read_text())
    catalogue=parse_element_sets(Path(latest['latest_snapshot']['path']).read_text())
    lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    output=ROOT/'dense-profile-minimum-v2';output.mkdir(exist_ok=False)
    hashes=snapshot_files([__file__,source/'receipt.json',latest_path]);started=time.monotonic()
    def save(name,value):
        (output/name).write_text(json.dumps(serializable(value),indent=2,allow_nan=False)+'\n')
    lat,lon=parent['results'][0]['roof_lat_lon'];center=geodesic_position(lat,lon,0.,0.)
    loaded={};cache={};evaluations=[]
    directories=[ROOT/'curvature-filter-roof-profile',ROOT/'curvature-filter-roof-profile-3km',source]
    for scan in parent['results']:
        label=scan['scan'];data=load_expanded_scan(scan['session'])
        original=next(s for s in latest['scans'] if s['scan']==label)
        sats=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in scan['variants']['unfiltered']['candidates']])
        indices=[lookup[int(data.numbers[s])] for s in sats]
        p,v,valid=propagate_candidate_states(catalogue,indices,original['origin_utc_ns'],data.nodes,np.array([0.]))
        assert list(valid)==indices
        data=copy.copy(data);data.position=data.position.copy();data.velocity=data.velocity.copy()
        data.position[sats]=p[:,0];data.velocity[sats]=v[:,0]
        loaded[label]=data
        for variant in ('unfiltered','filtered'):
            actual='unfiltered' if scan['variants'][variant].get('identical_to_unfiltered') else variant
            key=(label,actual)
            if key in cache:continue
            candidates=scan['variants'][variant]['candidates']
            chosen=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in candidates])
            roofpath=directories[0]/f'{label}-{actual}-roof.json'
            roof=json.loads(roofpath.read_text());hashes.update(snapshot_files([roofpath]))
            bank=[]
            for directory in directories:
                for path in directory.glob(f'{label}-{actual}-*.json'):
                    fit=json.loads(path.read_text())
                    if not isinstance(fit,dict) or not fit.get('success') or 'parameters' not in fit:continue
                    hashes.update(snapshot_files([path]));bank.append(fit)
            cache[key]=dict(chosen=chosen,roof=roof,bank=best_unique_fits(bank))
    def profile(label,variant,position):
        key=(label,'unfiltered' if label=='B' else variant);item=cache[key]
        nearest=min(item['bank'],key=lambda f:np.linalg.norm(np.array(f['parameters'][:2])-position))
        if np.linalg.norm(np.array(nearest['parameters'][:2])-position)<1e-9:return nearest
        vector=None;fit=None
        for attempt in range(5):
            fit=run_profile(loaded[label],nearest['parameters'],item['chosen'],nearest['rf_coefficient_hz_per_ghz'],position,
                probability_override=item['roof']['detection_probability'],start_vector=vector,budget_s=8.)
            vector=fit['vector']
            if fit['success']:break
        if not fit['success']:raise RuntimeError(f'Unconverged {label} {variant}')
        item['bank'].append(fit)
        en=local_offset(lat,lon,*_coordinates(position));index=len(evaluations)
        row=dict(index=index,scan=label,variant=key[1],east_m=en[0],north_m=en[1],position_km=position,
            objective=fit['objective'],delta_score=fit['objective']-item['roof']['objective'],
            nuisance_gradient=fit['projected_nuisance_gradient_inf_norm'])
        evaluations.append(row);save(f'fit-{index:04d}.json',fit);save('evaluations.json',evaluations)
        print(label,key[1],f'E{en[0]:.0f} N{en[1]:.0f}',f"delta {row['delta_score']:+.4f}",flush=True)
        return fit
    def combined(variant,position):
        fits=[profile(label,variant,position) for label in ('A','B')]
        return sum(f['objective'] for f in fits),np.sum([f['free_position_gradient'] for f in fits],axis=0)
    grid=[]
    for e,n in southern_grid():
        position=geodesic_position(lat,lon,np.degrees(np.arctan2(e,n)),np.hypot(e,n))
        for variant in ('unfiltered','filtered'):
            value,gradient=combined(variant,position)
            grid.append(dict(variant=variant,east_m=e,north_m=n,position_km=position,objective=value,gradient=gradient))
    save('grid.json',grid)
    minima={}
    for variant in ('unfiltered','filtered'):
        best=min([r for r in grid if r['variant']==variant],key=lambda r:r['objective'])
        starts=[center,np.array(best['position_km'])]
        attempts=[]
        for start_index,start in enumerate(starts):
            # Coordinates in regional-map kilometers, with a broad safety bound.
            res=minimize(lambda x:combined(variant,x),start,jac=True,method='L-BFGS-B',
                bounds=[(c-5,c+5) for c in center],options=dict(ftol=1e-13,gtol=1e-3,maxiter=35,maxls=12))
            en=local_offset(lat,lon,*_coordinates(res.x))
            record=dict(start=start_index,position_km=res.x,east_m=en[0],north_m=en[1],objective=res.fun,
                gradient_score_per_km=res.jac,success=bool(res.success),message=str(res.message),iterations=res.nit)
            attempts.append(record);save(f'{variant}-optimization.json',attempts)
            print('MINIMUM',variant,serializable(record),flush=True)
        best=min(attempts,key=lambda a:a['objective']);position=np.array(best['position_km'])
        # Eight neighbors allow a full central-difference 2D Hessian check.
        neighbors=[];h=.05
        for dx,dy in ((h,0),(-h,0),(0,h),(0,-h),(h,h),(h,-h),(-h,h),(-h,-h)):
            value,gradient=combined(variant,position+np.array([dx,dy]))
            neighbors.append(dict(dx_km=dx,dy_km=dy,objective=value,delta=value-best['objective']))
        vals={(r['dx_km'],r['dy_km']):r['objective'] for r in neighbors};f=best['objective']
        mixed=(vals[h,h]-vals[h,-h]-vals[-h,h]+vals[-h,-h])/(4*h*h)
        hessian=np.array([[(vals[h,0]+vals[-h,0]-2*f)/h**2,mixed],
                          [mixed,(vals[0,h]+vals[0,-h]-2*f)/h**2]])
        roof_score=sum(cache[(label,'unfiltered' if label=='B' else variant)]['roof']['objective'] for label in ('A','B'))
        minima[variant]=dict(best=best,attempts=attempts,neighbors=neighbors,hessian_score_per_km2=hessian,
            hessian_eigenvalues=np.linalg.eigvalsh(hessian),delta_score=f-roof_score,
            start_agreement_m=float(np.linalg.norm(np.array(attempts[0]['position_km'])-attempts[1]['position_km'])*1000))
        save('minima-partial.json',minima)
    assert_snapshot_unchanged(hashes)
    receipt=dict(parent=str(source/'receipt.json'),source_hashes=hashes,minima=minima,grid=grid,evaluations=evaluations,
        elapsed_s=time.monotonic()-started,roof_lat_lon=[lat,lon],
        scope='Same frozen satellite exclusions and full finite-set likelihood as prior 3km map. '
        '16 additional southern grid points; combined A+B position optimized from roof and best new grid point; '
        'each evaluation profiles independent per-scan timing/RX/RF parameters. Warm starts from nearest saved converged fit. '
        'Safety bounds +/-5 regional-map km around roof. Eight 50m neighbors verify local curvature; '
        'multistart agreement and positive Hessian support a local minimum, not a guaranteed global minimum. '
        'No candidate removals beyond the original curvature filter; B 62739 remains unassessed and present.')
    save('receipt.json',receipt);plot(output,receipt,parent)


def plot(output,receipt,parent):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.colors import TwoSlopeNorm
    fig,axes=plt.subplots(1,2,figsize=(14,7))
    for ax,variant in zip(axes,('unfiltered','filtered')):
        rows=list(parent['combined'][variant]['cells'])
        roof=next(c['objective'] for c in rows if c['label']=='roof')
        rows += [dict(east_m=r['east_m'],north_m=r['north_m'],delta_score=r['objective']-roof) for r in receipt['grid'] if r['variant']==variant]
        values=[r['delta_score'] for r in rows]
        norm=TwoSlopeNorm(vmin=-100,vcenter=0,vmax=300)
        im=ax.scatter([r['east_m']/1000 for r in rows],[r['north_m']/1000 for r in rows],c=values,cmap='RdBu_r',norm=norm,s=70,edgecolors='.4')
        best=receipt['minima'][variant]['best']
        ax.plot(0,0,'k+',ms=15,mew=2,label='Correct roof')
        ax.plot(best['east_m']/1000,best['north_m']/1000,'*',ms=20,color='gold',markeredgecolor='black',label='Optimized local minimum')
        ax.annotate(f"Δscore {receipt['minima'][variant]['delta_score']:+.2f}\nE {best['east_m']/1000:+.2f}, N {best['north_m']/1000:+.2f} km",
            (best['east_m']/1000,best['north_m']/1000),xytext=(8,-35),textcoords='offset points',fontsize=10)
        ax.set_title('Combined A + B · '+variant);ax.set_xlabel('East of roof (km)');ax.set_ylabel('North of roof (km)')
        ax.set_aspect('equal');ax.set_xlim(-3.2,3.2);ax.set_ylim(-3.7,3.2);ax.grid(alpha=.2);ax.legend(loc='upper left')
    fig.subplots_adjust(left=.07,right=.90,top=.85,bottom=.15,wspace=.25)
    cax=fig.add_axes([.93,.20,.017,.59]);fig.colorbar(im,cax=cax,label='Score − roof score (lower is better)')
    fig.suptitle('DS13 · denser position probes and optimized combined-score minima',fontsize=16,y=.96)
    fig.text(.5,.90,'27 original probes + 16 new southern grid points; timing/RX/RF nuisance refitted throughout',ha='center',fontsize=11)
    fig.text(.5,.04,'Stars are multistart local optimization results, not a guarantee of the global minimum.\n'
        'Original curvature exclusions remain fixed; full-group likelihood still includes soft associations outside final tracks.',ha='center',fontsize=10)
    fig.savefig(output/'minimum-map.png',dpi=170);plt.close(fig)


if __name__=='__main__':run()
