"""Saved DS24 paired cohort audit. No engine imports, inference, IQ or RF reads.

Run: /home/mouse9911/gits/leo-tracker-reduxredux/.venv/bin/python audit.py
All regression below describes already saved conditional CFO residuals; it is
not a new position or calibration fit. Fixed saved observations are never edited.
"""
from collections import defaultdict
import csv
import hashlib
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

OUT = Path(__file__).resolve().parent
HALF = Path('/srv/bulk/leo/research/ds24-channel-halves-20261024')
FULL = Path('/srv/bulk/leo/research/ds25-20261024')
EVID = Path('/srv/bulk/leo/research/ds24-bottlenecks-20261024/evidence')
INFO = Path('/srv/bulk/leo/research/ds24-bottlenecks-20261024/information')
REVIEW = Path('/srv/bulk/leo/research/ds24-channel-review-20261026')
ROOTS = {'all_channels':FULL, 'ch1_4':HALF/'ch1_4', 'ch5_8':HALF/'ch5_8'}
ARMS = ['c0','fitted_c']
FOCUS = ['DS24-0015','DS24-0019','DS24-0097']
SOURCES = {}

def source(p):
    SOURCES[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    return p

def read(p):
    return json.loads(source(p).read_bytes())

def encode(x):
    if isinstance(x,np.ndarray): return x.tolist()
    if isinstance(x,np.generic): return x.item()
    raise TypeError(type(x).__name__)

def write(name,x):
    (OUT/name).write_text(json.dumps(x,indent=2,default=encode,allow_nan=False)+'\n')

def stats(x):
    x=np.asarray(x,float);x=x[np.isfinite(x)]
    if not len(x): return {'n':0}
    return dict(n=len(x),mean=x.mean(),median=np.median(x),p05=np.quantile(x,.05),p95=np.quantile(x,.95),min=x.min(),max=x.max())

def correlation(x,y):
    x,y=np.asarray(x,float),np.asarray(y,float)
    ok=np.isfinite(x)&np.isfinite(y); x,y=x[ok],y[ok]
    return None if len(x)<3 or min(x.std(),y.std())==0 else float(np.corrcoef(x,y)[0,1])

def raw_curvature(track):
    # Exact descriptive rule in tools/localize_merged_track_catalogue.py.
    t,y=np.asarray(track['times']),np.asarray(track['values'])
    x=t-t.mean();centered=y-y.mean()
    residual=centered-x*(centered@x)/max(x@x,1e-12)
    return bool(np.ptp(t)>=20 and np.sqrt(np.mean(residual**2))>=250)

def csvout(name,rows):
    with (OUT/name).open('w') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)

def residual_summary(points):
    """Columns family, RX, channel, time, residual, sigma, RF."""
    x=np.asarray(points,float);t,r,s,f=x[:,3],x[:,4],x[:,5],x[:,6]
    lane_keys=x[:,:3].astype(int)
    lanes=np.unique(lane_keys,axis=0)
    slopes=[];numerator=denominator=0.; lane_square=0.;centered_square=0.
    means=[]
    for key in lanes:
        q=np.all(lane_keys==key,axis=1);tt=t[q]-t[q].mean();rr=r[q]-r[q].mean()
        den=float(tt@tt);num=float(tt@rr)
        if den>0:
            sl=num/den;slopes.append(sl);numerator+=num;denominator+=den;lane_square+=num*num/den
        centered_square+=float(rr@rr);means.append(float(r[q].mean()))
    common=numerator/denominator if denominator else 0.
    rx={}
    for receiver in [1,2]:
        q=x[:,1]==receiver
        if q.any():
            rx[str(receiver)] = dict(points=int(q.sum()),RMS_hz=np.sqrt(np.mean(r[q]**2)),normalized_RMS_hz=np.sqrt(np.mean((r[q]*11.5e9/f[q])**2)),mean_hz=r[q].mean(),standardized_RMS=np.sqrt(np.mean((r[q]/s[q])**2)))
    return dict(points=len(x),RMS_hz=np.sqrt(np.mean(r*r)),normalized_RMS_hz=np.sqrt(np.mean((r*11.5e9/f)**2)),mean_hz=r.mean(),time_span_s=np.ptp(t),time_q05_s=np.quantile(t,.05),time_q95_s=np.quantile(t,.95),RX=rx,lane_slope_hz_s=stats(slopes),lane_mean_hz=stats(means),common_within_lane_slope_hz_s=common,common_slope_fraction_of_centered_SS=(numerator*numerator/denominator/centered_square if denominator and centered_square else 0.),individual_lane_slopes_fraction_of_centered_SS=lane_square/centered_square if centered_square else 0.)

def main():
    cases=read(HALF/'summary.json')['baseline']['c0']['common_cases']
    source(Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools/localize_merged_track_catalogue.py'))
    source(Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools/compare_dsx01_retention_localization.py'))
    source(Path('/home/mouse9911/gits/leo-tracker-reduxredux/tools/dsx01_joint_marginal.py'))
    assert len(cases)==24
    q=read(EVID/'evidence_quick.json');quick={(r['case'],r['group'],r['arm']):r for r in q['records']}
    compare={(r['case'],r['group'],r['arm']):r for r in q['comparisons']}
    source(HALF/'tables/positions.csv')
    positions={(r['case'],r['group'],r['arm']):r for r in csv.DictReader((HALF/'tables/positions.csv').open()) if r['method']=='baseline' and r['case'] in cases and r['error_km']}
    normal=read(REVIEW/'normalized_rms.json');norm={(r['case'],r['group'],r['arm']):r for r in normal['rows']}
    information={r['case']:r for r in read(INFO/'all_cases.json')['rows']}
    source(EVID/'track_residual_metrics.csv')
    trackmetrics=list(csv.DictReader((EVID/'track_residual_metrics.csv').open()))
    bytrack=defaultdict(list)
    for r in trackmetrics: bytrack[r['case'],r['group'],r['arm']].append(r)
    fits={};tracks={};rf={};records=[];family_rows=[];scan_rows=[];labels={}
    for case in cases:
        for group,root in ROOTS.items():
            ts=read(root/case/'tracks.json');tracks[case,group]={t['key']:t for t in ts}
            prepared=read(root/case/'prepared.json')
            baseline_result=read(root/case/'result.json')
            graph_ids=set(oid for t in ts for oid in t['observation_ids'])
            curved_graph=[t for t in ts if raw_curvature(t)]
            assert len(curved_graph)==prepared['curved_tracks']
            curved_ids=set(oid for t in curved_graph for oid in t['observation_ids'])
            assert len(graph_ids)==prepared['graph_points']
            obs=read(root/case/'observations.json')
            for o in obs:
                key=(case,o['observation_id'])
                assert key not in rf or rf[key]==o['actual_rf_hz']
                rf[key]=o['actual_rf_hz']
            saved=read(root/'family_cavity/position'/(case+'.json'))
            node=saved['selected']['node'] if saved['accepted'] else saved['baseline_node']
            seed={r['component']:r for r in node['seed']['rows']}
            for arm in ARMS:
                a=saved['policy_arms'][arm];key=(case,group,arm);fits[key]=a
                gg=[g for g in a['gates']['tracks'] if g['compatible']]
                labs=defaultdict(list)
                for g in gg: labs[int(g['norad'])].append(g)
                labels[key]=labs
                pp=a.get('predictive_points',a.get('additional_predictive_points',0))
                assert a['active_points']+pp==quick[key]['associated']
                beta=np.asarray(a['state']['beta']);times=[];lengths=[];ambiguities=[]
                for g in gg:
                    t=tracks[case,group][g['component']]
                    ids=set(g['observation_ids']);tt=np.asarray([v for oid,v in zip(t['observation_ids'],t['times'],strict=True) if oid in ids]);assert len(tt)==g['points']
                    times.extend(tt);lengths.append(float(np.ptp(tt)))
                    if g['component'] in seed:ambiguities.append(int(seed[g['component']]['feasible_candidates']))
                tm=bytrack[key]
                r=dict(case=case,group=group,arm=arm,error_km=float(positions[key]['error_km']),RMS_hz=a['RMS_hz'],normalized_RMS_hz=norm[key].get('normalized_RMS_hz',norm[key].get('normalized_RMS_at_11p5GHz_hz')),GLRT=len(obs),curved_points=a['active_points'],predictive_points=pp,families=len(labs),tracks=len(gg),RX1_points=sum(g['points'] for g in gg if tracks[case,group][g['component']]['receiver']==1),RX2_points=sum(g['points'] for g in gg if tracks[case,group][g['component']]['receiver']==2),median_track_span_s=np.median(lengths),total_time_span_s=np.ptp(times),points_before_60s=sum(t<60 for t in times),points_after_240s=sum(t>240 for t in times),median_track_ACF=np.median([float(t['lag1_acf']) for t in tm]),median_track_abs_half_step_hz=np.median([abs(float(t['half_mean_step_hz'])) for t in tm]),multicandidate_tracks=sum(k>1 for k in ambiguities),seed_max_feasible_candidates=max(ambiguities,default=0),phase_max_abs_s=max(abs(a['state']['phases'][g['candidate_index']]) for g in gg),phase_reference_max_abs_s=max(abs(np.asarray(a['phase_reference']))),position_distance_to_12p5km_box_km=12.5-max(abs(np.asarray(a['endpoint_east_north_km']))),c_hz_per_GHz=beta[8] if len(beta)>8 else 0.)
                r['final_phase_change_s']=a.get('final_phase_change_s',a.get('history',[{}])[-1].get('phase_change_s'))
                r.update(graph_points=len(graph_ids),graph_tracks=len(ts),raw_curvature_graph_tracks=len(curved_graph),raw_curvature_graph_points=len(curved_ids),curved_points_as_fraction_GLRT=a['active_points']/len(obs),graph_points_as_fraction_GLRT=len(graph_ids)/len(obs),likelihood_fraction_GLRT=(a['active_points']+pp)/len(obs))
                failed=baseline_result['initial_failed_components']
                r.update(initial_failed_components=len(failed),initial_failed_RX1=sum('-RX1-' in t for t in failed),initial_failed_RX2=sum('-RX2-' in t for t in failed))
                for rx in [1,2]:
                    for band in [0,1]:
                        i=2*(rx-1)+band;prefix=f'RX{rx}_{"low" if band==0 else "high"}'
                        r[prefix+'_offset_hz']=beta[i];r[prefix+'_drift_hz_s']=beta[4+i]/150
                r['smooth_RX1_coefficient_norm_hz']=float(np.linalg.norm(a['state']['smooth'][0]));r['smooth_RX2_coefficient_norm_hz']=float(np.linalg.norm(a['state']['smooth'][1]))
                records.append(r)
                for norad,gates in labs.items():
                    idx=gates[0]['candidate_index'];ph=a['state']['phases'][idx]
                    local=sorted({g['candidate_index'] for g in a['gates']['tracks']}|{e['candidate_index'] for e in (saved['selected']['node'] if saved['accepted'] else saved['baseline_node'])['seed']['rows']})
                    # Means and reference use all node families, including inactive rows.
                    local=sorted({g['candidate_index'] for g in node['seed']['rows']})
                    mean=(saved['selected']['means'] if saved['accepted'] else saved['baseline_means'])[local.index(idx)]
                    ts0=[tracks[case,group][g['component']] for g in gates]
                    tt=[v for g,t in zip(gates,ts0,strict=True) for oid,v in zip(t['observation_ids'],t['times'],strict=True) if oid in set(g['observation_ids'])]
                    family_rows.append(dict(case=case,group=group,arm=arm,norad=norad,points=sum(g['points'] for g in gates),tracks=len(gates),receivers=','.join(map(str,sorted({t['receiver'] for t in ts0}))),channels=','.join(map(str,sorted({t['channel'] for t in ts0}))),time_start_s=min(tt),time_end_s=max(tt),phase_s=ph,prior_mean_s=mean,phase_minus_prior_mean_s=ph-mean))
    # Original saved actual conditional CFO residuals, with native RF attached by ID.
    source(EVID/'curved_point_residuals.csv');points=defaultdict(list);lanes=defaultdict(list)
    with (EVID/'curved_point_residuals.csv').open() as f:
        for row in csv.DictReader(f):
            key=row['case'],row['group'],row['arm'];n,rx,ch=int(row['norad']),int(row['receiver']),int(row['channel'])
            v=[n,rx,ch,float(row['time_s']),float(row['residual_hz']),float(row['sigma_hz']),rf[row['case'],row['observation_id']]]
            points[key].append(v);lanes[key+(n,rx,ch)].append(v)
    residual={};lanerows=[]
    for key,v in points.items():
        z=residual_summary(v);assert abs(z['RMS_hz']-fits[key]['RMS_hz'])<1e-6
        assert abs(z['normalized_RMS_hz']-rec_norm(norm[key]))<1e-6
        residual['/'.join(key)]=z
    for key,v in lanes.items():
        x=np.array(v);t=x[:,3];r=x[:,4];tc=t-t.mean();rc=r-r.mean();slope=float(tc@rc/max(tc@tc,1e-15))
        lanerows.append(dict(case=key[0],group=key[1],arm=key[2],norad=key[3],receiver=key[4],channel=key[5],points=len(x),span_s=np.ptp(t),time_start_s=t.min(),time_end_s=t.max(),RMS_hz=np.sqrt(np.mean(r*r)),normalized_RMS_hz=np.sqrt(np.mean((r*11.5e9/x[:,6])**2)),mean_hz=r.mean(),linear_slope_hz_s=slope,linear_end_to_end_hz=slope*np.ptp(t)))
    rec={(r['case'],r['group'],r['arm']):r for r in records}
    paired={}
    for arm in ARMS:
        delta=np.array([rec[c,'ch5_8',arm]['error_km']-rec[c,'ch1_4',arm]['error_km'] for c in cases]);order=np.argsort(delta)[::-1]
        paired[arm]=dict(high_minus_low_km=stats(delta),high_worse_scans=int((delta>0).sum()),high_better_scans=int((delta<0).sum()),top_2_paired_deficit_cases=[cases[i] for i in order[:2]],top_2_fraction_of_net_gap=delta[order[:2]].sum()/delta.sum(),mean_gap_without_top_2_km=delta[order[2:]].mean(),mean_gap_without_0015_0097_km=np.mean([d for c,d in zip(cases,delta) if c not in ['DS24-0015','DS24-0097']]))
        for case,d in zip(cases,delta):
            low,high,full=[rec[case,g,arm] for g in ['ch1_4','ch5_8','all_channels']]
            rr=dict(case=case,arm=arm,low_error_km=low['error_km'],high_error_km=high['error_km'],full_error_km=full['error_km'],high_minus_low_error_km=d)
            for metric in ['curved_points','predictive_points','families','median_track_span_s','RX1_points','RX2_points','median_track_ACF','median_track_abs_half_step_hz']:
                rr['low_'+metric]=low[metric];rr['high_'+metric]=high[metric];rr['high_minus_low_'+metric]=high[metric]-low[metric]
            sub=information[case]['arms'][arm]['curved']['subsets']
            rr['full_fit_geometry_low_radius_km']=sub['low']['rms_radius_km'];rr['full_fit_geometry_high_radius_km']=sub['high']['rms_radius_km'];rr['full_fit_geometry_high_to_low_radius']=sub['high']['rms_radius_km']/sub['low']['rms_radius_km']
            for group,prefix in [('ch1_4','low'),('ch5_8','high')]:
                co=compare[case,group,arm];rr[prefix+'_full_only']=co['full_only'];rr[prefix+'_half_only']=co['half_only'];rr[prefix+'_identity_disagreements']=co['identity_disagreements'];rr[prefix+'_full_endpoint_separation_km']=co['endpoint_separation_km']
                rr[prefix+'_common_phase_change_median_s']=float(np.median([abs(fits[case,group,arm]['state']['phases'][g[0]['candidate_index']]-fits[case,'all_channels',arm]['state']['phases'][labels[case,'all_channels',arm][n][0]['candidate_index']]) for n,g in labels[case,group,arm].items() if n in labels[case,'all_channels',arm]]))
                shifts=np.array([fits[case,group,arm]['state']['phases'][g[0]['candidate_index']]-fits[case,'all_channels',arm]['state']['phases'][labels[case,'all_channels',arm][n][0]['candidate_index']] for n,g in labels[case,group,arm].items() if n in labels[case,'all_channels',arm]])
                rr[prefix+'_common_phase_signed_change_median_s']=float(np.median(shifts));rr[prefix+'_common_phase_positive_shifts']=int((shifts>0).sum());rr[prefix+'_common_phase_families']=len(shifts)
            scan_rows.append(rr)
    correlations={}
    for arm in ARMS:
        ss=[s for s in scan_rows if s['arm']==arm];keys=[k for k in ss[0] if k.startswith('high_minus_low_') and k!='high_minus_low_error_km']+['full_fit_geometry_high_to_low_radius','high_full_only','high_half_only']
        correlations[arm]={k:correlation([s['high_minus_low_error_km'] for s in ss],[s[k] for s in ss]) for k in keys}
    systematics={}
    for arm in ARMS:
        for group in ROOTS:
            ss=[r for r in records if r['arm']==arm and r['group']==group]
            p=np.array([fits[c,group,arm]['endpoint_east_north_km'] for c in cases]);f=np.array([fits[c,'all_channels',arm]['endpoint_east_north_km'] for c in cases]);delta=p-f
            rz=[residual['/'.join([c,group,arm])] for c in cases]
            systematics[group+'/'+arm]=dict(mean_endpoint_minus_full_east_north_km=delta.mean(axis=0),median_endpoint_minus_full_east_north_km=np.median(delta,axis=0),std_endpoint_minus_full_east_north_km=delta.std(axis=0),east_shift_positive=int((delta[:,0]>0).sum()),north_shift_positive=int((delta[:,1]>0).sum()),scan_count=len(ss),curved_families=stats([r['families'] for r in ss]),curved_points=stats([r['curved_points'] for r in ss]),track_span_s=stats([r['median_track_span_s'] for r in ss]),phase_max_abs_s=stats([r['phase_max_abs_s'] for r in ss]),references_at_15s=sum(r['phase_reference_max_abs_s']>=14.999 for r in ss),position_box_nearest_distance_km=min(r['position_distance_to_12p5km_box_km'] for r in ss),maximum_final_phase_change_s=max(r['final_phase_change_s'] for r in ss if r['final_phase_change_s'] is not None),common_within_lane_slope_hz_s=stats([r['common_within_lane_slope_hz_s'] for r in rz]),individual_lane_slopes_explained_SS=stats([r['individual_lane_slopes_fraction_of_centered_SS'] for r in rz]),RX={str(rx):{k:stats([r['RX'][str(rx)][k] for r in rz]) for k in ['RMS_hz','normalized_RMS_hz','standardized_RMS','points','mean_hz']} for rx in [1,2]})
    # Existing same-time distinct-pair residual correlations use full-fit lanes.
    cr=read(EVID/'residual_correlations.json');cs={}
    for arm in ARMS:
        for rx in [1,2]:
            for band in ['low','high']:
                rr=[r for r in cr['rows'] if r['arm']==arm and r['kind']=='cross_family_same_RX_same_band' and r['left'][1]==rx and ('low' if r['left'][2]<=4 else 'high')==band]
                cs[f'{arm}/RX{rx}/{band}']=dict(dependent_lane_pairs=len(rr),pair_correlations=stats([r['correlation'] for r in rr]),scan_medians=stats([np.median([r['correlation'] for r in rr if r['case']==c]) for c in cases if any(r['case']==c for r in rr)]))
    csvout('scan_metrics.csv',records);csvout('paired_scans.csv',scan_rows);csvout('family_metrics.csv',family_rows);csvout('residual_lanes.csv',lanerows)
    stages={}
    for g in ROOTS:
        rows=[r for r in records if r['group']==g and r['arm']=='fitted_c']
        stages[g]={k:sum(r[k] for r in rows) for k in ['GLRT','graph_points','raw_curvature_graph_points','curved_points','predictive_points','graph_tracks','raw_curvature_graph_tracks','tracks','initial_failed_components','initial_failed_RX1','initial_failed_RX2']}
        stages[g]['graph_fraction_GLRT']=stages[g]['graph_points']/stages[g]['GLRT']
        stages[g]['raw_curvature_fraction_GLRT']=stages[g]['raw_curvature_graph_points']/stages[g]['GLRT']
        stages[g]['active_curved_fraction_GLRT']=stages[g]['curved_points']/stages[g]['GLRT']
        stages[g]['active_curved_fraction_raw_curvature']=stages[g]['curved_points']/stages[g]['raw_curvature_graph_points']
    ablation={}
    for g in ROOTS:
        cc=[rec[c,g,'c0'] for c in cases];ff=[rec[c,g,'fitted_c'] for c in cases]
        ablation[g]=dict(mean_fitted_minus_c0_error_km=np.mean([b['error_km']-a['error_km'] for a,b in zip(cc,ff)]),mean_fitted_minus_c0_RMS_hz=np.mean([b['RMS_hz']-a['RMS_hz'] for a,b in zip(cc,ff)]),mean_fitted_minus_c0_normalized_RMS_hz=np.mean([b['normalized_RMS_hz']-a['normalized_RMS_hz'] for a,b in zip(cc,ff)]))
    vectors={}
    for arm in ARMS:
        d=np.array([np.asarray(fits[c,'ch5_8',arm]['endpoint_east_north_km'])-fits[c,'ch1_4',arm]['endpoint_east_north_km'] for c in cases]);center=d.mean(axis=0)
        vectors[arm]=dict(high_minus_low_mean_east_north_km=center,SD_east_north_km=d.std(axis=0),mean_vector_length_km=np.linalg.norm(center),centered_RMS_vector_length_km=np.sqrt(np.mean(np.sum((d-center)**2,axis=1))),positive_east_scans=int((d[:,0]>0).sum()),positive_north_scans=int((d[:,1]>0).sum()))
    summary=dict(scope='Original 24 matched saved DS24 baseline/policy fits; c0 and fitted_c. All numerical regressions are descriptive of saved postfit conditional CFO residuals. No new detector, IQ, association, geometry or position fits.',paired=paired,group_summary=systematics,descriptive_Pearson_correlation_with_paired_error_gap=correlations,same_RX_cross_family_full_fit_residual_correlations=cs,focus_scans=[r for r in scan_rows if r['case'] in FOCUS],focus_states=[r for r in records if r['case'] in FOCUS],focus_families=[r for r in family_rows if r['case'] in FOCUS],association=q['agreement'],limits=['Satellite assignments and family counts are model labels, not independently established identities.','Same-label agreement can coexist with changed membership and nuisance estimates.','The c controls are matched within each saved group; half/full memberships differ.','Residual correlations are conditional and dependent; they do not identify hardware or TLE causality.','Full-endpoint band information is a frozen full-fit local diagnostic, not separate half-fit uncertainty or calibrated confidence.','Offset/drift coefficients describe a prior-coupled calibration solution; single-band offset/drift modes cannot be interpreted as independently identified hardware quantities.','No fitted c localization advantage follows from a smaller frequency residual.','No change to production files or scientific fixtures.'])
    summary.update(graph_stages=stages,c_ablation=ablation,paired_position_vectors=vectors,validation=dict(actual_saved_conditional_residual_RMS_and_RF_normalized_RMS_reconstructed_contexts=len(residual),tolerance_hz=1e-6,point_records=sum(len(v) for v in points.values())))
    summary['limits'].append('Seed feasible-candidate counts are inherited nomination metadata, not current posterior ambiguity; some recovered final tracks still carry feasible_candidates=0 and compatible=False in the historical seed.')
    write('summary.json',summary);write('residual_summary.json',residual);write('provenance.json',dict(source_files_sha256=SOURCES,script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),new_fit_calls=0,raw_IQ_reads=0,new_RF_collection=False))
    plot(cases,rec,fits,scan_rows,points,lanerows)
    print(json.dumps({'paired':paired,'correlations':correlations,'states':{k:v for k,v in systematics.items() if k.endswith('fitted_c')}},default=encode,indent=2))

def rec_norm(row):
    return row['normalized_RMS_at_11p5GHz_hz']

def plot(cases,rec,fits,scanrows,points,lanerows):
    colors={'ch1_4':'#2677b8','ch5_8':'#d66a28','all_channels':'#498855'}
    fig,axs=plt.subplots(2,2,figsize=(13,9),layout='constrained')
    ax=axs[0,0]
    ss=sorted([r for r in scanrows if r['arm']=='fitted_c'],key=lambda r:r['high_minus_low_error_km'])
    ax.barh([r['case'][5:] for r in ss],[r['high_minus_low_error_km'] for r in ss],color=[colors['ch5_8'] if r['high_minus_low_error_km']>0 else colors['ch1_4'] for r in ss]);ax.axvline(0,color='black',lw=.6);ax.set(xlabel='CH5–8 minus CH1–4 position error (km)',ylabel='DS24 scan',title='Paired fitted-c localization deficits')
    ax=axs[0,1]
    for g in ['ch1_4','ch5_8']:
        delta=np.array([np.asarray(fits[c,g,'fitted_c']['endpoint_east_north_km'])-fits[c,'all_channels','fitted_c']['endpoint_east_north_km'] for c in cases]);ax.scatter(delta[:,0],delta[:,1],label=g,color=colors[g],alpha=.7)
        for c,p in zip(cases,delta):
            if c in FOCUS:ax.annotate(c[5:],p,fontsize=8)
    ax.axhline(0,color='black',lw=.5);ax.axvline(0,color='black',lw=.5);ax.set(xlabel='East shift from full fit (km)',ylabel='North shift from full fit (km)',title='Different directions across scans');ax.legend()
    ax=axs[1,0]
    for g in ROOTS:
        pp=[r for r in rec.values() if r['group']==g and r['arm']=='fitted_c'];ax.scatter([r['curved_points'] for r in pp],[r['error_km'] for r in pp],label=g,color=colors[g],alpha=.7)
    ax.set(xlabel='Saved active curved points',ylabel='Position error (km)',title='Support is weaker; point count alone is insufficient');ax.legend()
    ax=axs[1,1]
    for g in ROOTS:
        pp=[r for r in rec.values() if r['group']==g and r['arm']=='fitted_c'];ax.scatter([r['families'] for r in pp],[r['error_km'] for r in pp],label=g,color=colors[g],alpha=.7)
    ax.set(xlabel='Active model families',ylabel='Position error (km)',title='Family count does not measure geometric independence')
    fig.savefig(OUT/'paired_cohort.png',dpi=170);fig.savefig(OUT/'paired_cohort.pdf');plt.close(fig)
    fig,axs=plt.subplots(3,2,figsize=(14,10),layout='constrained')
    for row,c in enumerate(FOCUS):
        for col,rx in enumerate([1,2]):
            ax=axs[row,col]
            for g in ['ch1_4','ch5_8']:
                p=np.array(points[c,g,'fitted_c']);p=p[p[:,1]==rx];bins=np.arange(0,331,15);centers=(bins[:-1]+bins[1:])/2;means=[]
                for lo,hi in zip(bins[:-1],bins[1:]):
                    v=p[(p[:,3]>=lo)&(p[:,3]<hi),4];means.append(v.mean() if len(v) else np.nan)
                ax.plot(centers,means,'o-',ms=3,label=g,color=colors[g])
            ax.axhline(0,color='black',lw=.6);ax.set(title=f'{c} RX{rx}: saved conditional residual means',xlabel='Measured CFO time (s); 15s bins',ylabel='Residual (Hz)');ax.legend(fontsize=8)
    fig.suptitle('Postfit residuals; bins mix changing family support and are descriptive')
    fig.savefig(OUT/'focus_residual_time.png',dpi=170);plt.close(fig)
    fig,axs=plt.subplots(1,3,figsize=(15,5),layout='constrained')
    for c,ax in zip(FOCUS,axs):
        aa={}
        for g in ['all_channels','ch5_8']:
            a=fits[c,g,'fitted_c'];families=defaultdict(list)
            for r in a['gates']['tracks']:
                if r['compatible']:families[r['norad']].append(r)
            aa[g]={n:(a['state']['phases'][rows[0]['candidate_index']],sum(r['points'] for r in rows)) for n,rows in families.items()}
        common=set(aa['all_channels'])&set(aa['ch5_8']);order=sorted(common,key=lambda n:aa['ch5_8'][n][0]-aa['all_channels'][n][0]);delta=[aa['ch5_8'][n][0]-aa['all_channels'][n][0] for n in order]
        ax.barh([str(n) for n in order],delta,color=colors['ch5_8']);ax.axvline(0,color='black',lw=.6);ax.set(title=f'{c}: {sum(d>0 for d in delta)}/{len(delta)} positive shifts',xlabel='High-only minus full estimated phase (s)',ylabel='Common model family (NORAD)')
    fig.suptitle('Saved fitted-c states: coherent family timing shifts in 0015 and 0097')
    fig.savefig(OUT/'focus_phase_shifts.png',dpi=170);plt.close(fig)

if __name__=='__main__':main()
