"""Extend the frozen roof screen with stratified random probes to 3 km."""
import copy
import csv
import json
from pathlib import Path
import numpy as np
from curvature_position_profile import ROOT


def wide_probes(seed=2026100303):
    rng=np.random.default_rng(seed);points=[]
    for band,(lo,hi) in enumerate(((500.,1000.),(1000.,2000.),(2000.,3000.))):
        for sector in range(4):
            angle=rng.uniform(sector*np.pi/2,(sector+1)*np.pi/2)
            radius=np.sqrt(rng.uniform(lo*lo,hi*hi))
            points.append(dict(label=f'wide-{band+1}-{sector+1}',east_m=float(radius*np.sin(angle)),
                north_m=float(radius*np.cos(angle)),radius_m=float(radius)))
    return points


def run():
    from all_visible_bank import load_expanded_scan
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from finite_set_fit import snapshot_files,assert_snapshot_unchanged
    from position_profile_grid import run_profile,geodesic_position
    from plot_all_glrt_doppler_overlay import serializable
    source=ROOT/'curvature-filter-roof-profile';output=ROOT/'curvature-filter-roof-profile-3km'
    parent=json.loads((source/'receipt.json').read_text())
    assert_snapshot_unchanged(parent['source_hashes'])
    latest_path=ROOT/'later-tle-timing-aligned-v2/receipt.json'
    latest=json.loads(latest_path.read_text());tle=Path(latest['latest_snapshot']['path'])
    catalogue=parse_element_sets(tle.read_text());lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    hashes=snapshot_files([__file__,source/'receipt.json',latest_path,tle])
    output.mkdir(exist_ok=False)
    def save(name,value):
        (output/name).write_text(json.dumps(serializable(value),indent=2,allow_nan=False)+'\n')
    results=copy.deepcopy(parent['results'])
    for result in results:
        label=result['scan'];session=result['session'];lat,lon=result['roof_lat_lon']
        print(label,'loading',flush=True)
        data=load_expanded_scan(session)
        original=next(s for s in latest['scans'] if s['scan']==label)
        numbers=result['variants']['unfiltered']['candidates']
        satellites=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in numbers])
        indices=[lookup[int(n)] for n in numbers]
        p,v,valid=propagate_candidate_states(catalogue,indices,original['origin_utc_ns'],data.nodes,np.array([0.]))
        assert list(valid)==indices
        data=copy.copy(data);data.position=data.position.copy();data.velocity=data.velocity.copy()
        data.position[satellites]=p[:,0];data.velocity[satellites]=v[:,0]
        for variant in ('unfiltered','filtered'):
            if variant=='filtered' and result['variants'][variant].get('identical_to_unfiltered'):
                result['variants'][variant]=copy.deepcopy(result['variants']['unfiltered'])
                result['variants'][variant]['identical_to_unfiltered']=True
                continue
            item=result['variants'][variant]
            path=source/f'{label}-{variant}-roof.json';hashes.update(snapshot_files([path]));roof=json.loads(path.read_text())
            chosen=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in item['candidates']])
            for point in wide_probes():
                e,n=point['east_m'],point['north_m']
                pos=geodesic_position(lat,lon,np.degrees(np.arctan2(e,n)),np.hypot(e,n))
                vector=None;attempts=[]
                for _ in range(5):
                    fit=run_profile(data,roof['parameters'],chosen,roof['rf_coefficient_hz_per_ghz'],pos,
                        probability_override=roof['detection_probability'],start_vector=vector,budget_s=8.)
                    vector=fit['vector'];attempts.append({k:fit[k] for k in ('objective','success','status','projected_nuisance_gradient_inf_norm')})
                    if fit['success']:break
                fit['attempts']=attempts
                save(f"{label}-{variant}-{point['label']}.json",fit)
                if not fit['success']:
                    raise RuntimeError(f"Unconverged profile: {label} {variant} {point['label']}; saved checkpoint")
                cell=dict(**point,objective=fit['objective'],delta_score=fit['objective']-roof['objective'],
                    data_nll=fit['data_nll'],prior_nll=fit['nuisance_prior_nll'],success=fit['success'],
                    nuisance_gradient=fit['projected_nuisance_gradient_inf_norm'],position_km=pos,support=fit['satellite_support'])
                item['cells'].append(cell)
                print(f"{label} {variant} {point['label']} r={point['radius_m']:.0f}m Δ={cell['delta_score']:+.3f}",flush=True)
                save('partial.json',results)
            item['best']=min(item['cells'],key=lambda c:c['objective'])
    combined={}
    for variant in ('unfiltered','filtered'):
        cells=[]
        a,b=[s['variants'][variant]['cells'] for s in results]
        for left,right in zip(a,b,strict=True):
            assert all(left[k]==right[k] for k in ('label','east_m','north_m'))
            cells.append(dict(**{k:left[k] for k in ('label','east_m','north_m')},
                objective=left['objective']+right['objective'],delta_score=left['delta_score']+right['delta_score']))
        combined[variant]=dict(cells=cells,best=min(cells,key=lambda c:c['objective']),
                              derivatives=parent['combined'][variant]['derivatives'])
    assert_snapshot_unchanged(hashes)
    receipt=dict(results=results,combined=combined,source_hashes=hashes,random_seed=2026100303,
        scope=parent['scope']+' Extended with 12 stratified random samples: one per quadrant in each radial band '
        '0.5–1, 1–2 and 2–3 km; uniform area within each sector. All 15 original points retained unchanged. '
        'Same frozen exclusions, likelihood, candidate probabilities and priors; nuisance refit from roof at every new site. '
        'Displayed arrows/derivatives remain LOCAL roof gradients, not gradients at distant samples. '
        'Best sampled point is not an optimized location or a global minimum.')
    save('receipt.json',receipt)
    rows=[dict(scan=s['scan'],variant=variant,**{k:c[k] for k in ('label','east_m','north_m','objective','delta_score')})
          for s in results for variant,item in s['variants'].items() for c in item['cells']]
    rows += [dict(scan='combined',variant=variant,**c) for variant,item in combined.items() for c in item['cells']]
    with (output/'scores.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    plot(output,receipt)
    print('BEST',json.dumps(serializable({v:c['best'] for v,c in combined.items()})),flush=True)


def plot(output,receipt):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,3,figsize=(15,11),sharex=True,sharey=True)
    limit=max(abs(c['delta_score']) for s in receipt['results'] for item in s['variants'].values() for c in item['cells'])
    limit=max(limit,max(abs(c['delta_score']) for item in receipt['combined'].values() for c in item['cells']))
    for row,variant in enumerate(('unfiltered','filtered')):
        for col,label in enumerate(('A','B','combined')):
            item=receipt['combined'][variant] if label=='combined' else next(s for s in receipt['results'] if s['scan']==label)['variants'][variant]
            cells=item['cells'];ax=axes[row,col]
            im=ax.scatter([c['east_m']/1000 for c in cells],[c['north_m']/1000 for c in cells],
                c=[c['delta_score'] for c in cells],cmap='RdBu_r',vmin=-limit,vmax=limit,
                s=[80 if c['label'].startswith('wide') else 28 for c in cells],edgecolors='.4')
            for c in cells:
                if c['label'].startswith('wide'):
                    ax.annotate(f"{c['delta_score']:+.1f}",(c['east_m']/1000,c['north_m']/1000),
                                xytext=(4,5),textcoords='offset points',fontsize=8)
            g=np.array(item['derivatives'][0]['gradient_score_per_m'])
            ax.plot(0,0,'k+',ms=14,mew=2)
            ax.arrow(0,0,*(-g/np.linalg.norm(g)*.7),width=.013,head_width=.12,color='black',length_includes_head=True)
            best=item['best'];ax.plot(best['east_m']/1000,best['north_m']/1000,marker='*',ms=17,
                markerfacecolor='none',markeredgecolor='black',markeredgewidth=1.5)
            ax.add_patch(plt.Circle((0,0),3,fill=False,color='.6',linestyle=':',linewidth=.8))
            ax.set_title(f"{'Combined' if label=='combined' else 'Scan '+label} · {variant}\n"
                         f"Best sampled Δscore: {best['delta_score']:+.1f}",fontsize=11,pad=12)
            ax.set_aspect('equal');ax.set_xlim(-3.3,3.3);ax.set_ylim(-3.3,3.3);ax.grid(alpha=.18)
            ax.set_xlabel('East of roof (km)')
            if col==0:ax.set_ylabel('North of roof (km)')
    fig.subplots_adjust(left=.07,right=.90,bottom=.13,top=.86,hspace=.36,wspace=.22)
    cax=fig.add_axes([.925,.20,.016,.59]);fig.colorbar(im,cax=cax,label='Score − roof score (lower is better)')
    fig.suptitle('DS13 · position score at random points out to 3 km',fontsize=17,y=.965)
    fig.text(.5,.917,'Same frozen curvature exclusions; RX offsets/drifts, RF and satellite timing refitted at each new point',ha='center',fontsize=11)
    fig.text(.5,.045,'+ = correct roof. Arrow = LOCAL downhill direction at roof; fixed display length. ☆ = best sampled point, not an optimized minimum.\n'
        '15 original near-roof points + 12 stratified random points spanning 0.5–3 km. Shared color scale.\n'
        'Same full-group likelihood as before, including soft associations outside final tracks and unassessed B · 62739.',ha='center',fontsize=10)
    fig.savefig(output/'score-gradient-3km.png',dpi=170);plt.close(fig)


if __name__=='__main__':run()
