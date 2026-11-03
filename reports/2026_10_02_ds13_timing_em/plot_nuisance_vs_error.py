"""Empirical nuisance distributions versus position error; no new model fits."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
from curvature_position_profile import ROOT
from find_profile_minimum import local_offset
from joint_inputs import _coordinates

SOURCE=ROOT.parent/'2026_10_03_ds13_four_scan_curvature/comparison-v2'
COLORS=['#0072B2','#E69F00','#009E73','#CC79A7']
METRICS=[('rx0_offset_hz','RX0 offset at t = 150 s (kHz)',1000.),
         ('rx1_offset_hz','RX1 offset at t = 150 s (kHz)',1000.),
         ('rx0_drift_hz_s','RX0 linear drift (Hz/s)',1.),
         ('rx1_drift_hz_s','RX1 linear drift (Hz/s)',1.),
         ('rf_hz_ghz','Common RF coefficient (Hz/GHz)',1.),
         ('common_tau_s','Common orbit timing shift (s)',1.),
         ('individual_tau_rms_s','RMS satellite-relative timing (s)',1.),
         ('timing_prior_nll','Timing-prior penalty (NLL)',1.)]


def extract(fit,numbers,number_to_index):
    p=np.asarray(fit['parameters'],float)
    tau=p[6+np.asarray([number_to_index[int(n)] for n in numbers])]
    common=float(tau.mean());relative=tau-common
    np.testing.assert_allclose(common,fit['vector'][6],atol=1e-10,rtol=0)
    prior=.5*float(relative@relative)+.5*(common/10.)**2
    np.testing.assert_allclose(prior,fit['nuisance_prior_nll'],atol=1e-8,rtol=0)
    return dict(rx0_offset_hz=p[2],rx1_offset_hz=p[4],rx0_drift_hz_s=p[3],rx1_drift_hz_s=p[5],
        rf_hz_ghz=float(np.asarray(fit['rf_coefficient_hz_per_ghz']).item()),common_tau_s=common,
        individual_tau_rms_s=float(np.sqrt(np.mean(relative**2))),timing_prior_nll=prior,
        satellite_tau_s=tau.tolist(),satellite_relative_tau_s=relative.tolist())


def deduplicate(records):
    """One best fit per scan, candidate set and location rounded to 1 mm."""
    unique={}
    for row in records:
        key=(row['scan'],tuple(row['candidates']),tuple(np.round(row['position_km'],6)))
        if key not in unique or row['objective']<unique[key]['objective']:unique[key]=row
    return list(unique.values())


def reference_changes(row,roof):
    if row['candidates']!=roof['candidates']:raise ValueError('roof reference must use the same candidate set')
    result={'delta_'+k:row[k]-roof[k] for k,_,_ in METRICS}
    result['relative_timing_change_rms_s']=float(np.sqrt(np.mean((
        np.asarray(row['satellite_relative_tau_s'])-roof['satellite_relative_tau_s'])**2)))
    return result


def run():
    out=SOURCE/'nuisance-vs-position-error';out.mkdir(exist_ok=False)
    hashes={}
    def read(path):
        payload=path.read_bytes();hashes[str(path.resolve())]=hashlib.sha256(payload).hexdigest()
        return json.loads(payload)
    receipt=read(SOURCE/'receipt.json');selection=read(SOURCE.parent/'selection.json')
    hashes[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    poses={p['session']:p for p in selection['poses']}
    all_records=[];endpoints=[];roofs=[]
    for scan in receipt['scans']:
        sid=scan['session'];seed=read(SOURCE.parent/'scans'/sid/'seed.json')
        mapping=dict(zip(seed['catalog_numbers'],seed['satellites']))
        pose=poses[sid];roof_fit=read(SOURCE/sid/'unfiltered-roof.json');center=np.asarray(roof_fit['parameters'][:2])
        records=[]
        for i,e in enumerate(scan['evaluations']):
            path=SOURCE/sid/f'fit-{i:04d}.json';fit=read(path)
            assert fit['success'] and e['success']
            np.testing.assert_allclose(fit['parameters'][:2],e['position'],rtol=0,atol=1e-8)
            np.testing.assert_allclose(fit['objective'],e['objective'],rtol=0,atol=1e-7)
            en=local_offset(pose['latitude'],pose['longitude'],*_coordinates(fit['parameters'][:2]))
            records.append(dict(scan=scan['scan_index'],session=sid,candidates=e['candidates'],
                position_km=fit['parameters'][:2],east_m=float(en[0]),north_m=float(en[1]),
                position_error_km=float(np.linalg.norm(en)/1000),objective=fit['objective'],fit_path=str(path),
                **extract(fit,e['candidates'],mapping)))
        for numbers in {tuple(r['candidates']) for r in records}:
            candidates=[r for r in records if tuple(r['candidates'])==numbers]
            at_roof=[r for r in candidates if np.linalg.norm(np.asarray(r['position_km'])-center)<1e-8]
            if not at_roof:raise ValueError('missing same-policy roof reference')
            base=min(at_roof,key=lambda r:r['objective']);roofs.append(base.copy())
            for r in candidates:r.update(reference_changes(r,base))
        for v in scan['variants']:
            if v['status']!='evaluated':continue
            matches=[r for r in records if r['candidates']==v['policy']['kept'] and
                     np.linalg.norm(np.asarray(r['position_km'])-v['best']['position_km'])<1e-8]
            best=min(matches,key=lambda r:abs(r['objective']-v['best']['objective']))
            assert abs(best['objective']-v['best']['objective'])<1e-6
            np.testing.assert_allclose(best['position_error_km']*1000,v['best']['distance_m'],atol=1e-5,rtol=0)
            endpoints.append(dict(best,threshold=v['threshold'],boundary=v['boundary'],
                multiple_minima=v['start_agreement_m']>1,retained=len(v['policy']['kept'])))
        all_records.extend(records)
    records=deduplicate(all_records)
    endpoint_unique={}
    for e in endpoints:
        key=(e['scan'],tuple(e['candidates']))
        if key not in endpoint_unique:endpoint_unique[key]=dict(e,cutoffs=[])
        endpoint_unique[key]['cutoffs'].append(e['threshold'])
    unique_endpoints=list(endpoint_unique.values())
    scatter(out,records,unique_endpoints,False);scatter(out,records,unique_endpoints,True)
    timing_boxes(out,endpoints)
    columns=['scan','session','position_error_km','east_m','north_m','objective','candidates','fit_path']
    columns += [k for k,_,_ in METRICS]+['delta_'+k for k,_,_ in METRICS]+['relative_timing_change_rms_s']
    for name,rows in [('profile-values.csv',records),('best-found-values.csv',endpoints)]:
        cols=columns+(['threshold','boundary','multiple_minima','retained'] if name.startswith('best') else [])
        with (out/name).open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=cols);writer.writeheader()
            writer.writerows({k:r[k] for k in cols} for r in rows)
    result=dict(raw_profile_count=len(all_records),unique_location_policy_count=len(records),
        unique_endpoint_policies=len(unique_endpoints),endpoints=endpoints,source_hashes=hashes,
        scope='Four additional DS13 scans only. Error is geodesic horizontal distance from capture-bound roof, not Doppler RMS. '
        'Saved converged fits only; no refitting. Deduplicate locations at 1 mm within each scan/candidate set, retaining lowest score. '
        'Changes reference the same candidate-set nuisance refit at the roof. Satellite-relative timing is total shift minus '
        'the unweighted mean over retained satellites; timing is shared across RX for each satellite. '
        'RF coefficient multiplies (RF - mean unique RF)/GHz; receiver lines use t-150 s. '
        'Empirical adaptive-search samples are nonuniform and correlated, not posterior draws or independent replicates. '
        'Timing boxes summarize retained satellites, not uncertainty; repeated policies reuse the same fit. '
        'Boundary endpoints are not located minima; starred endpoints have start-dependent local minima.')
    for path,digest in hashes.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==digest
    (out/'receipt.json').write_text(json.dumps(result,indent=2,allow_nan=False)+'\n')
    print(json.dumps({k:result[k] for k in ('raw_profile_count','unique_location_policy_count','unique_endpoint_policies')},indent=2))
    for r in unique_endpoints:
        print(r['scan'],r['cutoffs'],round(r['position_error_km'],3),
              {k:round(r[k],4) for k in ('delta_rx0_drift_hz_s','delta_rx1_drift_hz_s','delta_common_tau_s','relative_timing_change_rms_s')})


def scatter(out,records,endpoints,changes):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    fig,axes=plt.subplots(2,4,figsize=(17,8.5),sharex=True)
    for ax,(key,label,scale) in zip(axes.flat,METRICS):
        selected='delta_'+key if changes else key
        if changes:
            label='Change in '+label[0].lower()+label[1:]
            if key=='individual_tau_rms_s':
                selected='relative_timing_change_rms_s';label='RMS change in satellite-relative timing (s)'
            ax.axhline(0,color='.6',lw=.7)
        for scan,color in enumerate(COLORS,1):
            rows=[r for r in records if r['scan']==scan]
            ax.scatter([r['position_error_km'] for r in rows],[r[selected]/scale for r in rows],s=12,alpha=.22,color=color,linewidths=0)
            for r in (e for e in endpoints if e['scan']==scan):
                marker='^' if r['boundary'] else '*' if r['multiple_minima'] else 'o'
                ax.scatter(r['position_error_km'],r[selected]/scale,s=85 if marker=='*' else 55,
                           color=color,marker=marker,edgecolors='k',linewidths=.6,zorder=5)
        ax.set_ylabel(label);ax.set_xlabel('Position error from roof (km)');ax.grid(alpha=.2)
    legend=[Line2D([],[],marker='o',ls='',color=c,label=f'Scan {i}') for i,c in enumerate(COLORS,1)]
    legend += [Line2D([],[],marker=m,ls='',color='k',label=l) for m,l in [('o','Best local result'),('^','Search boundary'),('*','Multiple minima')]]
    fig.legend(handles=legend,loc='upper center',bbox_to_anchor=(.5,.935),ncol=7,frameon=False,fontsize=10)
    title='Nuisance changes from the same-model roof fit' if changes else 'Absolute nuisance values across fitted locations'
    fig.suptitle('Four DS13 scans · '+title,fontsize=16,y=.985)
    fig.text(.5,.02,'Faint dots: deduplicated saved profile fits. Large markers: best-found result per unique candidate set.\nAdaptive search samples—not posterior draws; no causal inference from these associations.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.075,1,.89));fig.savefig(out/('nuisance-changes-vs-error.png' if changes else 'nuisance-values-vs-error.png'),dpi=170);plt.close(fig)


def timing_boxes(out,endpoints):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(2,2,figsize=(13,9),sharey=True)
    rng=np.random.default_rng(20261003)
    for scan,(ax,color) in enumerate(zip(axes.flat,COLORS),1):
        rows=[r for r in endpoints if r['scan']==scan]
        bp=ax.boxplot([r['satellite_tau_s'] for r in rows],positions=np.arange(len(rows)),widths=.5,
                      patch_artist=True,showfliers=False)
        for box in bp['boxes']:box.set(facecolor=color,alpha=.25)
        labels=[]
        for x,r in enumerate(rows):
            tau=r['satellite_tau_s'];ax.scatter(x+rng.uniform(-.15,.15,len(tau)),tau,color=color,s=22,zorder=3)
            ax.scatter(x,r['common_tau_s'],color='k',marker='D',s=30,zorder=4)
            suffix='†' if r['boundary'] else '*' if r['multiple_minima'] else ''
            labels.append(f"{'Off' if r['threshold'] is None else r['threshold']}\n{r['position_error_km']:.3f} km{suffix}\nn={len(tau)}")
        ax.axhline(0,color='.5',lw=.7);ax.set_xticks(range(len(rows)),labels);ax.grid(axis='y',alpha=.2)
        ax.set_title(f"Scan {scan} · {rows[0]['session']}",fontsize=11)
        ax.set_ylabel('Total satellite orbit timing shift (s)');ax.set_xlabel('Curvature cutoff / best-found position error / satellite count')
    fig.suptitle('Satellite timing-shift distributions at the best-found positions',fontsize=16)
    fig.text(.5,.02,'Dots = retained satellites; box = median / IQR, whiskers = 1.5 IQR; black diamond = common timing (mean).\nNot posterior uncertainty. Repeated candidate sets reuse fits. † Boundary, minimum not located. * Start-dependent minima.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.075,1,.94));fig.savefig(out/'satellite-timing-distributions.png',dpi=170);plt.close(fig)


if __name__=='__main__':run()
