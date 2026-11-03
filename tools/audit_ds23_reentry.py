"""Independent RF replay before geography for the two reentry prototypes."""

import argparse
from concurrent.futures import ProcessPoolExecutor,as_completed
from pathlib import Path
import statistics

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from probe_ds23_sign_carrier_position import context_signed
from probe_ds23_consensus_growth import make
from probe_ds23_frequency_events import summary
from run_ds23_combined_recovery_full import valid,ARMS
from run_algo01_ds23_sample import ROOT,read,write,sha

LOCATIONS={
    'consensus':(ROOT/'reports/2026_10_21_ds23_consensus_growth',Path('/srv/bulk/leo/research/ds23-consensus-growth-20261021')),
    'catalogue':(ROOT/'reports/2026_10_21_ds23_catalogue_reentry',Path('/srv/bulk/leo/research/ds23-catalogue-reentry-20261021')),
    'owner':(ROOT/'reports/2026_10_21_ds23_owner_reentry',Path('/srv/bulk/leo/research/ds23-owner-reentry-20261021')),
}


def replay(job):
    method,cohort,case=job;out,bulk=LOCATIONS[method];path=bulk/(case+'.json');d=read(path)
    scan,node,mask,powers,means,hyper,entries,signed,source=context_signed(case)
    incumbent=signed['policy_arms']
    if d['incumbent_arms']!=incumbent:raise ValueError('source incumbent differs from audited signed policy')
    base=make(scan,node,mask,'c0',incumbent['c0']['phase_reference'],powers,means,hyper,entries)
    trials=[];checks=[]
    for t in d.get('trials',[]):
        changed=t['node'];offered=np.asarray(t['mask'],bool);newmeans=np.asarray(t.get('means',means))
        if offered.shape!=mask.shape or np.any(mask & ~offered):raise ValueError('original curved evidence removed')
        for k,sl in enumerate(base.slices):
            if mask[sl].any() and (node['seed']['rows'][k]['candidate_index']!=changed['seed']['rows'][k]['candidate_index'] or node['aliases'][k]!=changed['aliases'][k]):
                raise ValueError('incumbent curved identity or alias changed')
        for arm,r in t['arms'].items():
            trial_scan=scan
            if d.get('fine_basis'):
                from probe_ds23_owner_reentry import fine_view
                trial_scan=fine_view(scan)
            p=make(trial_scan,changed,offered,arm,r['phase_reference'],powers,newmeans,hyper,entries)
            fresh=summary(p,np.asarray(r['endpoint_east_north_km']),entries)
            delta=fresh['negative_twice_elbo']-r['negative_twice_elbo']
            if abs(delta)>1e-3:raise ValueError('reentry endpoint objective failed independent replay')
            for key in ['gates','linear_gates']:
                fg=fresh[key]['tracks'] if key=='gates' else fresh[key]
                rg=r[key]['tracks'] if key=='gates' else r[key]
                if [v['compatible'] for v in fg]!=[v['compatible'] for v in rg]:raise ValueError('original gate replay changed')
            checks.append(dict(arm=arm,RF_difference=delta,failed_curved=[g['component'] for g in fresh['gates']['tracks'] if not g['compatible']],
                final_phase_change_s=r['final_phase_change_s']))
        if valid(t['arms'])!=t.get('paired_valid',t.get('accepted')):raise ValueError('paired acceptance changed')
        trials.append(t)
    chosen=d.get('selected') if method in ['catalogue','owner'] else next((t for t in trials if t.get('accepted')),None)
    if method in ['catalogue','owner'] and chosen:
        group=chosen['group']['rows']
        passing=[t for t in trials if t['group']['rows']==group and t['paired_valid']]
        best=min(passing,key=lambda t:t['arms']['c0']['negative_twice_elbo'])
        if chosen!=best:raise ValueError('c0 RF same-mask model selection changed')
    expected=chosen['arms'] if chosen else incumbent
    if d['policy_arms']!=expected:raise ValueError('exact pair fallback failed')
    rows=[]
    added=int(np.asarray(chosen['mask'],bool).sum()-mask.sum()) if chosen else 0
    for arm in ARMS:
        from evaluate_ds23_phase_refreshed import extend_associations
        from dbg01_unassociated import ownership
        lookup={t['key']:t for t in scan.tracks}
        old=incumbent[arm];original=make(scan,node,mask,arm,old['phase_reference'],powers,means,hyper,entries)
        x=np.array(old['endpoint_east_north_km']);baseline=extend_associations(original,x,summary(original,x,entries)['gates'])
        def accepted_ids(extension):
            return ownership([dict(r,observation_ids=r.get('observation_ids',lookup[r['component']]['observation_ids'])) for r in extension['tracks']])
        before_ids=accepted_ids(baseline)
        if chosen:
            policy_scan=scan
            if d.get('fine_basis'):
                from probe_ds23_owner_reentry import fine_view
                policy_scan=fine_view(scan)
            current=d['policy_arms'][arm]
            p=make(policy_scan,chosen['node'],np.array(chosen['mask'],bool),arm,current['phase_reference'],powers,
                np.asarray(chosen.get('means',means)),hyper,entries)
            x=np.asarray(current['endpoint_east_north_km']);extension=extend_associations(p,x,summary(p,x,entries)['gates'])
            after_ids=accepted_ids(extension)
        else:after_ids=before_ids
        original_ids={o['observation_id'] for o in read(scan.bank_path/'observations.json')}
        if (before_ids|after_ids)-original_ids:raise ValueError('additional peaks entered original winner coverage')
        rows.append(dict(case=case,cohort=cohort,method=method,arm=arm,status=d['status'],adopted=bool(chosen),
            added_curved_points=added,baseline_latlon=incumbent[arm]['endpoint_latlon'],policy_latlon=d['policy_arms'][arm]['endpoint_latlon'],
            baseline_RMS_hz=incumbent[arm]['RMS_hz'],policy_RMS_hz=d['policy_arms'][arm]['RMS_hz'],
            attempted_models=len(trials),seconds=d['seconds'],all_original_GLRT=len(original_ids),
            baseline_associated_points=len(before_ids),policy_associated_points=len(after_ids),
            baseline_associated_percent=100*len(before_ids)/len(original_ids),
            policy_associated_percent=100*len(after_ids)/len(original_ids),
            lost_original_association_ids=sorted(before_ids-after_ids),newly_associated_original_ids=sorted(after_ids-before_ids)))
    return dict(case=case,method=method,cohort=cohort,source_sha256=sha(path),checks=checks,rows=rows,
        original_measurements_nominations_aliases_powers_priors_and_predictive_entries_preserved=True)


def stats(rows,key):
    values=[r[key] for r in rows]
    return dict(count=len(values),mean_km=statistics.mean(values),median_km=statistics.median(values),maximum_km=max(values))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--methods',nargs='+',choices=list(LOCATIONS),default=list(LOCATIONS))
    parser.add_argument('--cohorts',nargs='+',default=['engineering','development'])
    args=parser.parse_args();jobs=[]
    for method in args.methods:
        out,bulk=LOCATIONS[method];p=read(out/'protocol.json')
        for cohort in args.cohorts:
            for case in p[cohort]:
                if not (bulk/(case+'.json')).exists():raise ValueError(f'missing terminal result {method} {case}')
                jobs.append((method,cohort,case))
    receipts=[]
    with ProcessPoolExecutor(max_workers=8) as pool:
        for f in as_completed([pool.submit(replay,j) for j in jobs]):receipts.append(f.result())
    # Geographic evaluation occurs only after every supplied RF result replays.
    from report_algo02_ds23 import position_error
    for method in args.methods:
        out,bulk=LOCATIONS[method];rows=[r for q in receipts if q['method']==method for r in q['rows']]
        for r in rows:
            r['baseline_error_km']=position_error(r['baseline_latlon']);r['policy_error_km']=position_error(r['policy_latlon'])
        summary0={}
        for cohort in args.cohorts:
            summary0[cohort]={}
            for arm in ARMS:
                subset=[r for r in rows if r['cohort']==cohort and r['arm']==arm]
                before=stats(subset,'baseline_error_km');after=stats(subset,'policy_error_km')
                summary0[cohort][arm]=dict(incumbent=before,policy=after,accepted=sum(r['adopted'] for r in subset),
                    mean_and_median_improve=all(after[k]<before[k] for k in ['mean_km','median_km']))
        write(out/'independent_replay_evaluation.json',dict(rows=rows,statistics=summary0,
            receipts=[q for q in receipts if q['method']==method],all_original_gates_and_objectives_replayed=True,
            GPS_only_after_RF_replay_for_reporting=True,full_DS23_goal_achieved=False))
        fig,axes=plt.subplots(1,len(args.cohorts),figsize=(6*len(args.cohorts),5),layout='constrained',squeeze=False)
        for ax,cohort in zip(axes[0],args.cohorts):
            subset=[r for r in rows if r['cohort']==cohort and r['arm']=='fitted_c']
            for r in subset:
                ax.scatter(r['baseline_error_km'],r['policy_error_km'],color='tab:orange' if r['adopted'] else '.45')
                if cohort=='engineering' or r['adopted']:ax.annotate(r['case'].split('-')[-1],(r['baseline_error_km'],r['policy_error_km']),xytext=(3,3),textcoords='offset points',fontsize=8)
            limit=max([r[k] for r in subset for k in ['baseline_error_km','policy_error_km']])*1.08
            ax.plot([0,limit],[0,limit],'--',color='.7');ax.axhline(.5,color='seagreen',ls=':')
            ax.set(title=cohort,xlabel='Signed incumbent error (km)',ylabel='Reentry policy error (km)',xlim=(0,limit),ylim=(0,limit));ax.grid(alpha=.2)
        fig.suptitle(method+' reentry · fitted-c · orange = accepted complete-curve growth\nOriginal gates and exact incumbent fallback; no GPS in inference')
        fig.savefig(out/'position_comparison.png',dpi=165);plt.close(fig)
        print(method,summary0,flush=True)


if __name__=='__main__':main()
