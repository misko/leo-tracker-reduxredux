"""Attribute the profiled position gradient; test top-driver removal diagnostically."""
import copy
import csv
import json
import numpy as np
from curvature_position_profile import ROOT


def contributions(weight, derivative):
    weight=np.asarray(weight); derivative=np.asarray(derivative)
    if derivative.shape != weight.shape+(2,):
        raise ValueError('derivative must have one EN pair per row/candidate')
    return weight[:,:,None]*derivative*100.  # score per 100 local meters


def run():
    from all_visible_bank import load_expanded_scan
    from leo.sky.propagation import parse_element_sets
    from leo.analysis.adaptive_tle_prediction import propagate_candidate_states
    from later_tle_comparison import predict
    from rf_calibration_diagnostic import CalibrationObjective
    from finite_set_fit import snapshot_files,assert_snapshot_unchanged
    from position_profile_grid import geodesic_position,run_profile
    from plot_all_glrt_doppler_overlay import serializable
    source=ROOT/'curvature-filter-roof-profile'
    parent=json.loads((source/'receipt.json').read_text())
    assert_snapshot_unchanged(parent['source_hashes'])
    latest=json.loads((ROOT/'later-tle-timing-aligned-v2/receipt.json').read_text())
    catalogue=parse_element_sets(__import__('pathlib').Path(latest['latest_snapshot']['path']).read_text())
    lookup={int(n):i for i,n in enumerate(catalogue.satellite_numbers)}
    output=ROOT/'position-bias-contributors';output.mkdir(exist_ok=False)
    hashes=snapshot_files([__file__,source/'receipt.json',ROOT/'later-tle-timing-aligned-v2/receipt.json'])
    def read(name):
        path=source/name;hashes.update(snapshot_files([path]));return json.loads(path.read_text())
    def save(name,value):
        (output/name).write_text(json.dumps(serializable(value),indent=2,allow_nan=False)+'\n')
    results=[]
    combined_gradient=np.asarray(parent['combined']['filtered']['derivatives'][0]['gradient_score_per_m'])
    uphill=combined_gradient/np.linalg.norm(combined_gradient)
    for scan in parent['results']:
        label=scan['scan']; session=scan['session'];lat,lon=scan['roof_lat_lon']
        print(label,'loading',flush=True)
        data=load_expanded_scan(session)
        original=next(s for s in latest['scans'] if s['scan']==label)
        numbers=scan['variants']['unfiltered']['candidates']
        sats=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in numbers])
        indices=[lookup[int(n)] for n in numbers]
        p,v,valid=propagate_candidate_states(catalogue,indices,original['origin_utc_ns'],data.nodes,np.array([0.]))
        assert list(valid)==indices
        data=copy.copy(data);data.position=data.position.copy();data.velocity=data.velocity.copy()
        data.position[sats]=p[:,0];data.velocity[sats]=v[:,0]
        variants={}
        for variant in ('unfiltered','filtered'):
            actual='unfiltered' if scan['variants'][variant].get('identical_to_unfiltered') else variant
            fit=read(f'{label}-{actual}-roof.json')
            selected=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in scan['variants'][variant]['candidates']])
            objective=CalibrationObjective(data,np.array(fit['parameters']),selected,False,8.)
            objective.base.deadline=float('inf');objective.likelihood.detection_probability=fit['detection_probability']
            value,gradient=objective.evaluate(np.array(fit['vector']))
            assert abs(value-fit['objective'])<1e-7
            weight=-objective.likelihood.last_result['prediction_gradient'].copy()
            posterior=objective.likelihood.last_result['row_association_probability'].copy()
            derivatives=[];direct=[];priors=[]
            for plus,minus,bearing in (('E+50N+0','E-50N+0',90.),('E+0N+50','E+0N-50',0.)):
                hi=read(f'{label}-{actual}-{plus}.json');lo=read(f'{label}-{actual}-{minus}.json')
                derivatives.append((predict(data,hi['parameters'],selected,hi['rf_coefficient_hz_per_ghz'])-
                                    predict(data,lo['parameters'],selected,lo['rf_coefficient_hz_per_ghz']))/100.)
                priors.append(hi['nuisance_prior_nll']-lo['nuisance_prior_nll'])
                ph=np.array(fit['parameters']);pl=ph.copy()
                ph[:2]=geodesic_position(lat,lon,bearing,1.)
                pl[:2]=geodesic_position(lat,lon,bearing+180,1.)
                direct.append((predict(data,ph,selected,fit['rf_coefficient_hz_per_ghz'])-
                               predict(data,pl,selected,fit['rf_coefficient_hz_per_ghz']))/2.)
            terms=contributions(weight,np.stack(derivatives,axis=-1))
            direct_terms=contributions(weight,np.stack(direct,axis=-1))
            summed=terms.sum(axis=(0,1))+np.asarray(priors)
            expected=np.array(scan['variants'][variant]['derivatives'][0]['gradient_score_per_m'])*100
            np.testing.assert_allclose(summed,expected,rtol=.01,atol=.005)
            np.testing.assert_allclose(direct_terms.sum(axis=(0,1)),expected,rtol=.01,atol=.005)
            rows=[];channels=[];timebins=[];satellite_rows=[]
            for j,s in enumerate(selected):
                number=int(data.numbers[s])
                total=terms[:,j].sum(axis=0)
                satellite_rows.append(dict(satellite=number,gradient_per_100m=total,
                    downhill_pressure=float(total@uphill),support=float(posterior[:,j].sum())))
                for rx in (0,1):
                    mask=data.receiver==rx
                    g=terms[mask,j].sum(axis=0);d=direct_terms[mask,j].sum(axis=0)
                    rows.append(dict(scan=label,variant=variant,satellite=number,receiver=rx,
                        east=g[0],north=g[1],downhill_pressure=float(g@uphill),
                        direct_east=d[0],direct_north=d[1],support=float(posterior[mask,j].sum())))
                    for ch in np.unique(data.channel):
                        m=mask&(data.channel==ch);t=terms[m,j].sum(axis=0)
                        channels.append(dict(satellite=number,receiver=rx,channel=int(ch),east=t[0],north=t[1],
                                             downhill_pressure=float(t@uphill),support=float(posterior[m,j].sum())))
                    for start in range(0,300,30):
                        m=mask&(data.times>=start)&(data.times<start+30);t=terms[m,j].sum(axis=0)
                        timebins.append(dict(satellite=number,receiver=rx,start_s=start,east=t[0],north=t[1],
                                             downhill_pressure=float(t@uphill),support=float(posterior[m,j].sum())))
            variants[variant]=dict(rows=rows,channels=channels,timebins=timebins,satellites=satellite_rows,
                prior_gradient_per_100m=priors,total_gradient_per_100m=summed,
                finite_difference_per_100m=expected,direct_gradient_per_100m=direct_terms.sum(axis=(0,1)))
            print(label,variant,'top',serializable(sorted(satellite_rows,key=lambda r:-r['downhill_pressure'])[:5]),flush=True)
        result=dict(scan=label,session=session,variants=variants)
        results.append(result);save('partial.json',results)
        # One controlled deletion per scan; refit shared nuisance rather than merely subtracting its gradient.
        driver=max(variants['filtered']['satellites'],key=lambda r:r['downhill_pressure'])['satellite']
        base_variant='unfiltered' if scan['variants']['filtered'].get('identical_to_unfiltered') else 'filtered'
        roof=read(f'{label}-{base_variant}-roof.json')
        chosen=[n for n in scan['variants']['filtered']['candidates'] if n!=driver]
        selected=np.array([int(np.flatnonzero(data.numbers==n)[0]) for n in chosen])
        cells=[];center=None
        for e,n in ((0.,0.),(50.,0.),(-50.,0.),(0.,50.),(0.,-50.)):
            position=geodesic_position(lat,lon,np.degrees(np.arctan2(e,n)),np.hypot(e,n))
            start=roof if center is None else center;vector=None
            for attempt in range(5):
                fitted=run_profile(data,start['parameters'],selected,start['rf_coefficient_hz_per_ghz'],position,
                    probability_override=roof['detection_probability'],start_vector=vector,budget_s=8.)
                vector=fitted['vector']
                if fitted['success']:break
            assert fitted['success'],f'{label} ablation did not converge'
            if center is None:center=fitted
            save(f'{label}-without-{driver}-E{e:+g}N{n:+g}.json',fitted)
            cells.append(dict(east_m=e,north_m=n,objective=fitted['objective']))
            print(label,'without',driver,e,n,fitted['objective']-center['objective'],flush=True)
        from curvature_position_profile import finite_difference
        result['ablation']=dict(removed=driver,cells=cells,derivative=finite_difference(cells,50.))
        save('partial.json',results)
    assert_snapshot_unchanged(hashes)
    save('receipt.json',dict(results=results,uphill_unit_en=uphill,source_hashes=hashes,
        scope='Local full finite-set likelihood attribution at roof. Prediction log-likelihood derivative multiplied '
        'by prediction change along the nuisance-refitted +/-50m path; includes every GLRT group, not only final tracks. '
        'Data terms grouped by candidate/RX/channel/time; timing-prior derivative reported separately. '
        'Positive downhill pressure means contribution favoring the combined filtered downhill direction. '
        'Direct fixed-nuisance attribution retained for comparison; allocation is path/parameterization dependent, not unique causality. '
        'Top candidate deletion per scan separately refits all nuisance to test leverage. No production changes.'))
    rows=[r for s in results for v in s['variants'].values() for r in v['rows']]
    with (output/'contributors.csv').open('x',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(serializable(rows))
    plot(output,results)


def plot(output,results):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(14,8))
    for ax,scan in zip(axes,results):
        rows=sorted(scan['variants']['filtered']['rows'],key=lambda r:-r['downhill_pressure'])
        values=[r['downhill_pressure'] for r in rows]
        ax.barh(range(len(rows)),values,color=['#D55E00' if x>0 else '#0072B2' for x in values])
        ax.set_yticks(range(len(rows)),[f"{r['satellite']} / RX{r['receiver']}" for r in rows]);ax.invert_yaxis()
        ax.axvline(0,color='.3');ax.grid(axis='x',alpha=.2);ax.set_axisbelow(True)
        ax.set_title('Scan '+scan['scan']);ax.set_xlabel('Contribution to downhill pressure / 100 m')
    fig.suptitle('Which tracks push the fitted location away from the roof?\nCurvature-filtered model · nuisance-refitted position derivative',fontsize=14)
    fig.text(.5,.025,'Orange favors the observed south-southeast drift; blue opposes it. All GLRT groups included.\n'
             'Receiver/satellite contributions are a local attribution, not identity confidence. Timing-prior term is separate.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.085,1,.92));fig.savefig(output/'contributors.png',dpi=170);plt.close(fig)


if __name__=='__main__':run()
