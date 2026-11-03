"""Read saved research endpoints, verify row accounting, and render comparisons.

No model evaluation, fitting, RF collection or algorithm selection occurs here.
Run again after optional arc-1000 or expanded-bank results finish.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
OLD = HERE.parent/'2026_10_16_dsx01_models'
DATA = HERE.parent/'2026_10_16_dsx01_fast_association_losses'
SOURCE_IDS = ['S01', 'S02', 'S03', 'S04', 'S05']
PRIMARY = ['original', 'A180', 'continuation1000', 'profile1000', 'arc1000']
LABELS = dict(original='Original', A180='Frozen A (180)',
              continuation1000='Continuation (1000)', profile1000='Exact profile (1000)',
              arc1000='Arc A (1000)', expanded_profile='Expanded profile')
COLORS = dict(original='#6b6b6b', A180='#0072b2', continuation1000='#8b5fbf',
              profile1000='#d55e00', arc1000='#009e73', expanded_profile='#cc79a7')


def save_json(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False)+'\n')


def rms(values):
    values = np.asarray(values)
    return float(np.sqrt(np.mean(values**2))) if len(values) else None


def csv_out(path, rows):
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def point_metrics(data, original, mask):
    use = np.asarray(mask, bool)
    a, b = data['associated'] & use, original['associated'] & use
    intersection = a & b
    new, lost = int(np.sum(a & ~b)), int(np.sum(b & ~a))
    missing = int(np.sum(use & ~original['associated']))
    return dict(observations=int(use.sum()), associated=int(a.sum()),
        association_pct=100*int(a.sum())/max(1, int(use.sum())),
        original_associated=int(b.sum()), original_missing=missing,
        new_associations=new, lost_associations=lost, net_gain=new-lost,
        net_original_missing_restored_pct=100*(new-lost)/missing if missing else None,
        retained_associations=int(intersection.sum()),
        retained_identity_changes=int(np.sum(intersection &
            (data['satellite_number'] != original['satellite_number']))),
        associated_rms_hz=rms(data['residual_hz'][a]),
        intersection_original_rms_hz=rms(original['residual_hz'][intersection]),
        intersection_variant_rms_hz=rms(data['residual_hz'][intersection]))


def load_records():
    sources = json.loads((DATA/'sources.json').read_text())
    dataset = json.loads((DATA/'dataset.json').read_text())
    observations = [json.loads(line) for line in (DATA/'context-observations.jsonl').read_text().splitlines()]
    source_obs = {s: [o for o in observations if o['source_id'] == s] for s in SOURCE_IDS}
    lookups = {s: {o['observation_id']: i for i,o in enumerate(source_obs[s])} for s in SOURCE_IDS}
    with (DATA/'membership.csv').open() as stream:
        members = list(csv.DictReader(stream))
    region_rows = {r['region_id']: np.array([lookups[r['source_id']][m['observation_id']]
        for m in members if m['region_id'] == r['region_id']], int) for r in dataset['regions']}
    assert sum(len(ix) for ix in region_rows.values()) == 693
    records, failures, verification = [], [], []

    def add(path, method):
        record = json.loads(path.read_text())
        if record.get('status') == 'failed' or 'full_scan' not in record:
            failures.append(dict(path=str(path), status=record.get('status', 'no-endpoint')))
            return
        sid = record['source_id']
        payload = np.load(path.with_suffix('.npz'))
        data = {key: np.asarray(payload[key]).copy() for key in payload.files}
        expected_times = np.array([o['time_s'] for o in source_obs[sid]])
        np.testing.assert_allclose(data['times_s'], expected_times, atol=1e-9, rtol=0)
        assert data['associated'].dtype == bool
        assert data['associated'].shape == data['residual_hz'].shape == expected_times.shape
        if method=='original':
            np.testing.assert_array_equal(data['associated'],
                np.array([o['original_associated'] for o in source_obs[sid]]))
            np.testing.assert_array_equal(data['satellite_number'],
                np.array([o['original_best_satellite'] for o in source_obs[sid]]))
        assert int(data['associated'].sum()) == record['full_scan']['associated']
        assert len(expected_times) == record['full_scan']['observations']
        np.testing.assert_allclose(rms(data['residual_hz'][data['associated']]),
                                   record['full_scan']['associated_rms_hz'], atol=1e-8, rtol=0)
        verification.append(dict(path=str(path.relative_to(HERE.parent.parent)),
            sha256=hashlib.sha256(path.read_bytes()).hexdigest(), observations=len(expected_times),
            associated=int(data['associated'].sum()), row_order_verified=True))
        records.append(dict(source_id=sid, arm=record.get('arm', 'fitted-c'), method=method,
            record=record, data=data, path=path))

    for sid in SOURCE_IDS:
        add(OLD/'results'/f'{sid}-full-fitted-c-original.json', 'original')
        add(OLD/'results'/f'{sid}-full-fitted-c-A.json', 'A180')
    for path in sorted((HERE/'results').glob('*.json')):
        record = json.loads(path.read_text())
        if record.get('mode','full') == 'full' and record.get('method') in ('profile', 'continuation', 'arc'):
            add(path, record['method']+'1000')
    for path in sorted((HERE/'expanded-results').glob('*.json')):
        record = json.loads(path.read_text())
        if (record.get('mode','full') == 'full' and 'source_id' in record and
                ('full_scan' in record or record.get('status') == 'failed')):
            method = 'expanded_'+record.get('method', 'profile')
            LABELS.setdefault(method, 'Expanded '+record.get('method', 'profile'))
            COLORS.setdefault(method, '#cc79a7')
            add(path, method)
    return sources, dataset, source_obs, region_rows, records, failures, verification


def aggregate(group, scope, total):
    metrics = [x['metrics'][scope] for x in group]
    associated = sum(x['associated'] for x in metrics)
    intersection = sum(x['retained_associations'] for x in metrics)
    weighted = lambda field, count: (float(np.sqrt(sum(x[count]*x[field]**2
        for x in metrics if x[field] is not None)/sum(x[count] for x in metrics)))
        if sum(x[count] for x in metrics) else None)
    return dict(completed_recordings=len(group), observations=total,
        available_observations=sum(x['observations'] for x in metrics), associated=associated,
        association_pct=100*associated/total,
        new_associations=sum(x['new_associations'] for x in metrics),
        lost_associations=sum(x['lost_associations'] for x in metrics),
        net_gain=sum(x['net_gain'] for x in metrics),
        retained_associations=intersection,
        retained_identity_changes=sum(x['retained_identity_changes'] for x in metrics),
        associated_rms_hz=weighted('associated_rms_hz', 'associated'),
        intersection_original_rms_hz=weighted('intersection_original_rms_hz', 'retained_associations'),
        intersection_variant_rms_hz=weighted('intersection_variant_rms_hz', 'retained_associations'),
        strict_accepted=sum(bool(x['audit'].get('accepted')) for x in group),
        completed_major_windows=sum(x['major_windows'] for x in group))


def temporal_summary(source_obs, region_rows, dataset):
    records=[]
    totals={}
    for mode in ['early_to_late','late_to_early']:
        totals[mode]=dict(held=0,held_challenge=0)
        for sid in SOURCE_IDS:
            times=np.array([o['time_s'] for o in source_obs[sid]])
            train=times<=np.median(times) if mode=='early_to_late' else times>np.median(times)
            challenge=np.zeros(len(times),bool)
            for region in dataset['regions']:
                if region['source_id']==sid:challenge[region_rows[region['region_id']]]=True
            totals[mode]['held']+=int((~train).sum())
            totals[mode]['held_challenge']+=int((challenge & ~train).sum())
    for path in sorted((HERE/'results').glob('*.json')):
        r=json.loads(path.read_text());mode=r.get('mode','full')
        if mode=='full' or 'held' not in r:continue
        a=np.load(path.with_suffix('.npz'));sid=r['source_id']
        times=np.array([o['time_s'] for o in source_obs[sid]])
        np.testing.assert_allclose(a['times_s'],times,atol=1e-9,rtol=0)
        assert int(a['associated'].sum())==r['full_scan']['associated']
        assert len(times)==r['full_scan']['observations']
        expected=times<=np.median(times) if mode=='early_to_late' else times>np.median(times)
        np.testing.assert_array_equal(a['train_mask'],expected)
        challenge=np.zeros(len(times),bool)
        for region in dataset['regions']:
            if region['source_id']==sid:challenge[region_rows[region['region_id']]]=True
        result=dict(source_id=sid,arm=r['arm'],method=r['method'],mode=mode,
            strict_training_accepted=bool(r['audit']['accepted']),stationarity=r['audit'].get('stationarity'))
        for scope,mask in [('held',~expected),('held_challenge',~expected & challenge)]:
            assigned=a['associated'] & mask
            assert int(assigned.sum())==r[scope]['associated']
            assert int(mask.sum())==r[scope]['observations']
            if assigned.any():
                np.testing.assert_allclose(rms(a['residual_hz'][assigned]),
                    r[scope]['associated_rms_hz'],atol=1e-8,rtol=0)
            result[scope]=dict(observations=int(mask.sum()),associated=int(assigned.sum()),
                associated_rms_hz=rms(a['residual_hz'][assigned]),
                absolute_assigned_residuals_hz=abs(a['residual_hz'][assigned]).tolist())
        records.append(result)
    groups=[]
    for mode in totals:
        for arm in ['fitted-c','zero-c']:
            for method in ['continuation','profile']:
                group=[r for r in records if (r['mode'],r['arm'],r['method'])==(mode,arm,method)]
                if not group:continue
                out=dict(mode=mode,arm=arm,method=method,completed_recordings=len(group),
                         strict_training_accepted=sum(r['strict_training_accepted'] for r in group))
                for scope in ['held','held_challenge']:
                    n=totals[mode][scope];assigned=sum(r[scope]['associated'] for r in group)
                    residual=np.concatenate([r[scope]['absolute_assigned_residuals_hz'] for r in group])
                    out[scope]=dict(observations=n,available_observations=sum(r[scope]['observations'] for r in group),
                        associated=assigned,association_pct=100*assigned/n,associated_rms_hz=rms(residual))
                groups.append(out)
    if groups:
        fig,axes=plt.subplots(2,2,figsize=(13,9),constrained_layout=True)
        for j,mode in enumerate(totals):
            for i,scope in enumerate(['held','held_challenge']):
                for method in ['continuation','profile']:
                    for arm in ['fitted-c','zero-c']:
                        group=[r for r in records if (r['mode'],r['method'],r['arm'])==(mode,method,arm)]
                        if not group:continue
                        values=np.sort(np.concatenate([r[scope]['absolute_assigned_residuals_hz'] for r in group]))
                        axes[i,j].step(np.maximum(values,1e-3),np.arange(1,len(values)+1)/totals[mode][scope],
                            where='post',color=COLORS[method+'1000'],ls='-' if arm=='fitted-c' else '--',
                            label=method+' / '+arm)
                axes[i,j].set_xscale('log');axes[i,j].set_ylim(0,1);axes[i,j].grid(alpha=.2)
                axes[i,j].set_title(mode.replace('_',' ')+' / '+scope.replace('_',' '))
                axes[i,j].set_xlabel('Absolute assigned frequency residual (Hz)')
                axes[i,j].set_ylabel(f"Fraction of all {totals[mode][scope]:,} excluded observations")
        axes[0,0].legend(fontsize=8)
        fig.suptitle('Temporal stress test: neutral seeds, receiver band contrasts permanently fixed at zero\nRestricted calibration protocol; full-recording candidate banks; excluded rows stay in denominator')
        fig.savefig(HERE/'iteration-temporal.png',dpi=160);plt.close(fig)
    return dict(expected_denominators=totals,completed_records=len(records),aggregates=groups,
        per_source=[{k:v for k,v in r.items() if k not in ['held','held_challenge']} | {
            scope:{k:v for k,v in r[scope].items() if k!='absolute_assigned_residuals_hz'}
            for scope in ['held','held_challenge']} for r in records],
        qualification='Restricted zero-contrast stress protocol: band offsets are permanently zero, '
        'not relearned from training. Held CFO is excluded, but the production calibration stage '
        'is unmatched. Fixed bank is conditioned on earlier full-recording discovery; not untouched validation.')


def plots(records, windows, aggregates, original):
    methods = [m for m in PRIMARY if any(x['method'] == m and x['arm'] == 'fitted-c' for x in records)]
    headline = [x for x in records if x['arm']=='fitted-c']
    width = .8/max(1,len(methods))
    x = np.arange(5)
    fig, axes = plt.subplots(2,2,figsize=(14,9), constrained_layout=True)
    for j, method in enumerate(methods):
        table = {r['source_id']:r for r in headline if r['method']==method}
        offset = x+(j-(len(methods)-1)/2)*width
        for ax, field, label in [(axes[0,0], 'association_pct','Associated / all observations (%)'),
                (axes[0,1], 'associated_rms_hz','Assigned frequency RMS (Hz)')]:
            ax.bar(offset, [table.get(s,{}).get('metrics',{}).get('full',{}).get(field,np.nan)
                           for s in SOURCE_IDS], width*.93, label=LABELS[method], color=COLORS[method])
            ax.set_ylabel(label)
        if method != 'original':
            axes[1,0].bar(offset, [table.get(s,{}).get('metrics',{}).get('full',{}).get('new_associations',np.nan)
                                  for s in SOURCE_IDS],width*.93,color=COLORS[method], label=LABELS[method])
            axes[1,0].bar(offset, [-table.get(s,{}).get('metrics',{}).get('full',{}).get('lost_associations',np.nan)
                                  for s in SOURCE_IDS],width*.93,color=COLORS[method],alpha=.45,hatch='//')
            delta = []
            for s in SOURCE_IDS:
                m = table.get(s,{}).get('metrics',{}).get('full',{})
                delta.append(m['intersection_variant_rms_hz']-m['intersection_original_rms_hz'] if m else np.nan)
            axes[1,1].bar(offset,delta,width*.93,color=COLORS[method],label=LABELS[method])
    axes[1,0].set_ylabel('New assignments (+) / lost original assignments (−)')
    axes[1,1].set_ylabel('Retained-intersection RMS change (Hz)')
    axes[0,0].set_ylim(0,100)
    for ax in axes.flat:
        ax.set_xticks(x,SOURCE_IDS);ax.grid(axis='y',alpha=.2);ax.axhline(0,color='#555',lw=.5)
    axes[0,0].legend(fontsize=8,ncol=2)
    fig.suptitle('Full-recording fitted-c comparison: all 20,084 original observations\nA180 has a smaller budget; no independently verified satellite identities')
    fig.savefig(HERE/'iteration-context.png',dpi=160);plt.close(fig)

    fig, axes = plt.subplots(2,1,figsize=(16,9), constrained_layout=True)
    region_ids = sorted({w['region_id'] for w in windows})
    xw = np.arange(len(region_ids))
    for j,method in enumerate(methods):
        table={w['region_id']:w for w in windows if w['method']==method and w['arm']=='fitted-c'}
        offset=xw+(j-(len(methods)-1)/2)*width
        axes[0].bar(offset,[table.get(r,{}).get('association_pct',np.nan) for r in region_ids],
                    width*.93,label=LABELS[method],color=COLORS[method])
        if method!='original':
            axes[1].bar(offset,[table.get(r,{}).get('net_original_missing_restored_pct',np.nan)
                                for r in region_ids],width*.93,color=COLORS[method])
    axes[0].set_ylabel('Associated / every window observation (%)');axes[0].set_ylim(0,100)
    axes[1].set_ylabel('Net gain / originally missing observations (%)')
    axes[1].axhline(80,color='#333',ls='--',lw=1,label='80% net restoration')
    axes[0].legend(ncol=3,fontsize=8);axes[1].legend(fontsize=8)
    for ax in axes:
        ax.set_xticks(xw,[r.rsplit('-',1)[1] for r in region_ids]);ax.grid(axis='y',alpha=.2)
        ax.axhline(0,color='#555',lw=.5)
    fig.suptitle('All 15 fixed windows: 693 observations; losses are subtracted from net restoration\nCandidate identity hypotheses are not truth labels')
    fig.savefig(HERE/'iteration-windows.png',dpi=160);plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(13,5),constrained_layout=True)
    for method in methods:
        group=[r for r in headline if r['method']==method]
        for ax,scope,total in [(axes[0],'full',20084),(axes[1],'challenge',693)]:
            values=np.sort(np.concatenate([abs(r['data']['residual_hz'][r['data']['associated'] & r['masks'][scope]])
                                           for r in group])) if group else np.array([])
            if len(values):ax.step(np.maximum(values,1e-3),np.arange(1,len(values)+1)/total,
                                   where='post',label=LABELS[method],color=COLORS[method])
            ax.set_xscale('log');ax.set_ylim(0,1);ax.grid(alpha=.2)
            ax.set_xlabel('Absolute assigned frequency residual (Hz)')
    axes[0].set_ylabel('Fraction of all 20,084 original observations')
    axes[1].set_ylabel('Fraction of all 693 window observations');axes[0].legend(fontsize=8)
    fig.suptitle('Frequency residual CDFs retain missing/unassociated rows in the denominator')
    fig.savefig(HERE/'iteration-distributions.png',dpi=160);plt.close(fig)

    # Original candidate intersection fixes the relative-timing histogram count.
    fixed_count=sum(len(r['record']['full_scan']['total_timing_s']) for r in original.values())
    fig,axes=plt.subplots(2,2,figsize=(13,9),constrained_layout=True)
    timing_counts={}
    for method in methods:
        group=[r for r in headline if r['method']==method]
        common=[];relative=[];dc=[];dr=[]
        for r in group:
            m=r['record']['full_scan'];b=original[r['source_id']]['record']['full_scan']
            common.append(m['common_timing_s']);dc.append(m['common_timing_s']-b['common_timing_s'])
            for k in b['total_timing_s']:
                if k in m['total_timing_s']:
                    a=m['total_timing_s'][k]-m['common_timing_s'];bb=b['total_timing_s'][k]-b['common_timing_s']
                    relative.append(a);dr.append(a-bb)
        timing_counts[method]=dict(common_count=len(common),relative_count=len(relative),
                                  expected_common_count=5,expected_relative_count=fixed_count)
        for ax,values,bins,label in [(axes[0,0],common,np.linspace(-10,10,21),'Common timing (s)'),
            (axes[0,1],relative,np.linspace(-30,30,31),'Relative timing on original candidates (s)'),
            (axes[1,0],dc,np.linspace(-20,20,25),'Change in common timing from original (s)'),
            (axes[1,1],dr,np.linspace(-60,60,41),'Change in relative timing from original (s)')]:
            assert int(np.histogram(values,bins=bins)[0].sum())==len(values), 'Timing outside plotted bins'
            ax.hist(values,bins=bins,histtype='step',lw=1.7,color=COLORS[method],label=LABELS[method])
            ax.set_xlabel(label);ax.set_ylabel('Count');ax.grid(alpha=.2)
    axes[0,0].legend(fontsize=8)
    fig.suptitle(f'Timing histograms: five common shifts and {fixed_count} original-candidate contrasts per complete method\nCommon/relative decomposition is a gauge; it does not prove physical orbit timing error')
    fig.savefig(HERE/'iteration-timing.png',dpi=160);plt.close(fig)

    fig,axes=plt.subplots(1,2,figsize=(13,5),constrained_layout=True)
    for j,method in enumerate(methods):
        table={r['source_id']:r for r in headline if r['method']==method}
        values=[table.get(s,{}).get('record',{}).get('full_scan',{}).get('configured_reference_distance_km',np.nan)
                for s in SOURCE_IDS]
        axes[0].bar(x+(j-(len(methods)-1)/2)*width,values,width*.93,label=LABELS[method],color=COLORS[method])
        ordered=np.sort([v for v in values if np.isfinite(v)])
        axes[1].step(ordered,np.arange(1,len(ordered)+1)/5,where='post',label=LABELS[method],color=COLORS[method])
    axes[0].set_xticks(x,SOURCE_IDS);axes[0].set_ylabel('Distance to configured station (km)');axes[0].set_ylim(bottom=0)
    axes[1].set_xlabel('Distance to configured station (km)');axes[1].set_ylabel('Fraction of all five recordings');axes[1].set_ylim(0,1)
    for ax in axes:ax.grid(alpha=.2)
    axes[0].legend(fontsize=8)
    fig.suptitle('Position reported separately from frequency fit\nOperator-configured reference, not surveyed independent geographic truth')
    fig.savefig(HERE/'iteration-position.png',dpi=160);plt.close(fig)
    fig,axes=plt.subplots(3,1,figsize=(13,10),constrained_layout=True)
    control_methods=[m for m in methods if m not in ('original','A180') and not m.startswith('expanded_')]
    control_width=.8/max(1,2*len(control_methods))
    for j,method in enumerate(control_methods):
        for ai,arm in enumerate(['fitted-c','zero-c']):
            table={r['source_id']:r for r in records if (r['method'],r['arm'])==(method,arm)}
            for ax,field,label in [(axes[0],'association_pct','Full association (%)'),
                                  (axes[1],'associated_rms_hz','Assigned frequency RMS (Hz)'),
                                  (axes[2],'configured_reference_distance_km','Configured-reference distance (km)')]:
                values=[table.get(s,{}).get('record',{}).get('full_scan',{}).get(field,np.nan) for s in SOURCE_IDS]
                ax.bar(x+(j*2+ai-(2*len(control_methods)-1)/2)*control_width,values,control_width*.93,
                    color=COLORS[method],alpha=1 if ai==0 else .45,hatch=None if ai==0 else '//',
                    label=LABELS[method]+' / '+arm)
                ax.set_ylabel(label);ax.set_xticks(x,SOURCE_IDS);ax.grid(axis='y',alpha=.2)
    axes[0].set_ylim(0,100);axes[0].legend(fontsize=8,ncol=2)
    fig.suptitle('Matched calibration sensitivity: identical data, banks, priors and declared budgets\nFrequency and configured-reference position reported separately')
    fig.savefig(HERE/'iteration-calibration.png',dpi=160);plt.close(fig)
    return timing_counts


def main():
    sources,dataset,source_obs,region_rows,records,failures,verification=load_records()
    original={r['source_id']:r for r in records if r['method']=='original'}
    windows=[]
    for r in records:
        sid=r['source_id'];n=len(source_obs[sid]);challenge=np.zeros(n,bool)
        for region in dataset['regions']:
            if region['source_id']==sid:challenge[region_rows[region['region_id']]]=True
        r['masks']=dict(full=np.ones(n,bool),challenge=challenge,outside=~challenge)
        r['metrics']={scope:point_metrics(r['data'],original[sid]['data'],mask) for scope,mask in r['masks'].items()}
        rec=r['record'];r['audit']=rec.get('audit',rec.get('endpoint_audit',{}));r['major_windows']=0
        assert r['metrics']['challenge']['associated']==rec['challenge']['associated']
        for region in dataset['regions']:
            if region['source_id']!=sid:continue
            mask=np.zeros(n,bool);mask[region_rows[region['region_id']]]=True
            m=point_metrics(r['data'],original[sid]['data'],mask)
            assert m['observations']==region['observation_count']
            assert m['original_associated']==region['original_associated_count']
            major=m['net_original_missing_restored_pct'] is not None and m['net_original_missing_restored_pct']>=80-1e-10
            r['major_windows']+=int(major)
            windows.append(dict(source_id=sid,region_id=region['region_id'],method=r['method'],arm=r['arm'],
                                major_net_restoration=bool(major),**m))
    csv_out(HERE/'window-comparison.csv',windows)
    methods=[m for m in PRIMARY if any(r['method']==m for r in records)]
    methods+=sorted({r['method'] for r in records}-set(methods))
    aggregates=[]
    for arm in ['fitted-c','zero-c']:
        for method in methods:
            group=[r for r in records if r['method']==method and r['arm']==arm]
            if not group:continue
            aggregates.append(dict(arm=arm,method=method,
                full=aggregate(group,'full',20084),challenge=aggregate(group,'challenge',693),
                outside=aggregate(group,'outside',19391)))
    timing_counts=plots(records,windows,aggregates,original)
    source_rows=[]
    for r in records:
        m=r['record']['full_scan'];diag=r['record'].get('diagnostics',r['record'].get('inference_diagnostics',{}))
        b=original[r['source_id']]['record']['full_scan']
        source_rows.append(dict(source_id=r['source_id'],arm=r['arm'],method=r['method'],
            full=r['metrics']['full'],challenge=r['metrics']['challenge'],outside=r['metrics']['outside'],
            objective=m['objective'],likelihood_nll=m['likelihood_nll'],
            configured_reference_distance_km=m.get('configured_reference_distance_km'),
            original_configured_reference_distance_km=b.get('configured_reference_distance_km'),
            position_movement_km=m.get('position_movement_km'),c=m.get('c'),
            common_timing_s=m['common_timing_s'],relative_timing_rms_s=m['relative_timing_rms_s'],
            relative_timing_max_s=m['relative_timing_max_s'],
            audit=r['audit'],budget=r['record'].get('budget',{}),
            evaluations=diag.get('evaluations',0),orbit_projection_calls=diag.get('orbit_projection_calls'),
            bank_additions=r['record'].get('bank_additions',[]),
            major_windows=r['major_windows']))
    temporal=temporal_summary(source_obs,region_rows,dataset)
    expanded_records=[r for r in records if r['method'].startswith('expanded_')]
    # Keep a stable population while concurrently produced expanded results arrive.
    expanded_sources=SOURCE_IDS.copy() if expanded_records else []
    expanded_total=sum(len(source_obs[s]) for s in expanded_sources)
    expanded_challenge=sum(r['observation_count'] for r in dataset['regions'] if r['source_id'] in expanded_sources)
    expanded_groups=[]
    for arm in ['fitted-c','zero-c']:
        for method in sorted({r['method'] for r in expanded_records}):
            group=[r for r in expanded_records if (r['arm'],r['method'])==(arm,method)]
            if group:expanded_groups.append(dict(arm=arm,method=method,
                full=aggregate(group,'full',expanded_total),
                challenge=aggregate(group,'challenge',expanded_challenge)))
    expanded_fixed=[]
    for arm in ['fitted-c','zero-c']:
        group=[r for r in records if r['source_id'] in expanded_sources and
               (r['arm'],r['method'])==(arm,'profile1000')]
        if group:expanded_fixed.append(dict(arm=arm,method='profile1000',
            full=aggregate(group,'full',expanded_total),
            challenge=aggregate(group,'challenge',expanded_challenge)))
    summary=dict(kind='DSX01-iteration2-read-only-comparison',source_order=SOURCE_IDS,
        observations=20084,challenge_observations=693,windows=15,aggregates=aggregates,
        per_source=source_rows,window_rows=windows,timing_histogram_counts=timing_counts,
        failures=failures,temporal=temporal,
        expanded_subset=dict(expected_sources=expanded_sources,observations=expanded_total,
            challenge_observations=expanded_challenge,aggregates=expanded_groups,
            fixed_bank_profile_comparators=expanded_fixed),
        verification=dict(records=len(verification),record_checks=verification,
            row_order='Each NPZ times_s matches frozen source-ordered context JSONL to 1 ns',
            association_counts='Every loaded full and challenge total matches its saved JSON',
            window_denominators='All 15 windows checked against frozen membership and original assignments'),
        qualifications=['Full-data warm-start development comparison; no independent identity truth or untouched validation.',
            'Original and frozen A180 are context; profile1000 versus continuation1000 is the matched-budget comparison.',
            'Full-objective and orbit-projection call counts are distinct; report both, not equivalent runtime costs.',
            'All support losses remain visible; greater association does not establish better satellite identity or localization.',
            'Zero-c arms begin at original fitted state with c set to zero; the matched zero-c continuation is their comparison baseline.',
            'Cold temporal arms permanently freeze band contrasts at zero; they omit training-only contrast learning and are restricted stress tests, not matching production calibration inference.',
            'Expanded-bank arms are separate population/model sensitivity experiments and not fixed-bank algorithm controls.'])
    save_json(HERE/'iteration-summary.json',summary)
    write_readme(summary,windows,methods)
    print(json.dumps(dict(records=len(records),failures=len(failures),
        aggregates=[dict(method=a['method'],arm=a['arm'],associated=a['full']['associated'],
            challenge=a['challenge']['associated'],new=a['full']['new_associations'],
            lost=a['full']['lost_associations'],major_windows=a['full']['completed_major_windows'],
            strict_accepted=a['full']['strict_accepted']) for a in aggregates]),indent=2))


def write_readme(summary, windows, methods):
    fmt=lambda x,d=2: '—' if x is None else f'{x:.{d}f}'
    selected=[a for a in summary['aggregates'] if a['arm']=='fitted-c' and not a['method'].startswith('expanded_')]
    profile=next(a for a in selected if a['method']=='profile1000')
    pf,pc=profile['full'],profile['challenge']
    lines=['# DSX01 iteration 2: exact timing profiles', '',
        f"The fixed-bank exact profile associates {pc['associated']}/693 window observations and "
        f"{pf['associated']:,}/20,084 full-recording observations; {pf['completed_major_windows']}/15 windows "
        'reach at least 80% net restoration of originally missing assignments. '
        f"It gains {pf['new_associations']:,} assignments and loses {pf['lost_associations']:,} original "
        f"assignments. {pf['strict_accepted']}/5 profile endpoints pass strict KKT. These are full-data "
        'warm-start development results; satellite identity hypotheses are not truth labels and '
        'higher association does not establish better localization.', '',
        'The profile ranks signed changes in the unchanged all-point conditional NLL and exact timing prior. '
        'It debits old support lost elsewhere in the recording. It removes A\'s global 48-arc selection, '
        '16-point arc subsampling, 70% coherence gate and top-eight arc-proposal restriction. '
        'See [arc diagnosis](arc_diagnostics.md) for the measured failures of those gates.', '',
        'Profile and continuation have a 1,000-full-objective/120-second allowance per recording; '
        'orbit projections are reported separately. Frozen A used 180 evaluations. Therefore A180 '
        'versus profile1000 combines an algorithm and budget change. Continuation1000 is the available '
        'matched-budget control; Arc A1000 is included automatically when its saved results exist. '
        'Incomplete optional arms retain all-recording denominators and show their completed coverage.', '',
        '## Fixed-bank fitted-c results', '',
        '| Method | Completed / 5 | Full associations / 20,084 | Window associations / 693 | New / lost original full support | Assigned RMS Hz | Intersection RMS original → variant Hz | ≥80% net-restored windows / 15 | Strict KKT passes / 5 |',
        '| --- | ---: | ---: | ---: | ---: | ---: | --- | ---: | ---: |']
    for a in selected:
        f,c=a['full'],a['challenge']
        lines.append(f"| {LABELS[a['method']]} | {f['completed_recordings']} | {f['associated']} ({f['association_pct']:.2f}%) | {c['associated']} ({c['association_pct']:.2f}%) | {f['new_associations']} / {f['lost_associations']} | {fmt(f['associated_rms_hz'])} | {fmt(f['intersection_original_rms_hz'])} → {fmt(f['intersection_variant_rms_hz'])} | {f['completed_major_windows']} | {f['strict_accepted']} |")
    lines+=['', 'Assigned RMS uses each method\'s assigned set. The intersection RMS pair uses the '
        'same observations assigned by that method and the original; selected satellite identities '
        'may change. Missing/unassociated observations stay in all association and CDF denominators.', '',
        '## All 15 windows', '',
        'A major restored window requires `(new assignments − lost original assignments) / originally '
        'missing observations ≥ 0.80`. This is distinct from 80% association over all window rows.', '']
    display=[m for m in methods if any(w['method']==m and w['arm']=='fitted-c' for w in windows)]
    lines+=['| Window | Source | All rows | '+' | '.join(LABELS[m] for m in display)+' | Profile net missing restored |',
            '| --- | --- | ---: | '+' | '.join('---:' for _ in display)+' | ---: |']
    for rid in sorted({w['region_id'] for w in windows}):
        table={w['method']:w for w in windows if w['region_id']==rid and w['arm']=='fitted-c'}
        first=next(iter(table.values()));profile=table.get('profile1000',{})
        lines.append(f"| {rid.rsplit('-',1)[1]} | {first['source_id']} | {first['observations']} | "+' | '.join(
            f"{table[m]['associated']} ({table[m]['association_pct']:.1f}%)" if m in table else 'missing' for m in display)+
            f" | {fmt(profile.get('net_original_missing_restored_pct'),1)}% |")
    lines+=['', '## Source-level profile regressions, timing and position', '',
        '| Source | New / lost full support | New / lost outside windows | Assigned RMS Hz | Intersection RMS original → profile Hz | Configured-reference km original → profile | Common timing s original → profile | Relative timing RMS s original → profile | KKT | Strict pass |',
        '| --- | ---: | ---: | ---: | --- | --- | --- | --- | ---: | --- |']
    per={(r['source_id'],r['arm'],r['method']):r for r in summary['per_source']}
    for sid in SOURCE_IDS:
        r=per.get((sid,'fitted-c','profile1000'));b=per[(sid,'fitted-c','original')]
        if not r:continue
        f,o=r['full'],r['outside']
        lines.append(f"| {sid} | {f['new_associations']} / {f['lost_associations']} | {o['new_associations']} / {o['lost_associations']} | {fmt(f['associated_rms_hz'])} | {fmt(f['intersection_original_rms_hz'])} → {fmt(f['intersection_variant_rms_hz'])} | {fmt(b['configured_reference_distance_km'])} → {fmt(r['configured_reference_distance_km'])} | {fmt(b['common_timing_s'])} → {fmt(r['common_timing_s'])} | {fmt(b['relative_timing_rms_s'])} → {fmt(r['relative_timing_rms_s'])} | {fmt(r['audit'].get('stationarity'),6)} | {r['audit'].get('accepted',False)} |")
    lines+=['', 'A strict endpoint requires projected KKT ≤0.001. A feasible lower-objective state '
        'that fails this threshold remains a research iterate. Position is distance to the previously '
        'operator-configured station, not surveyed independent truth. Frequency-fit improvements are '
        'reported separately from position. Common and relative timing describe a parameter gauge; '
        'changes do not prove physical ephemeris error. The original table uses the present broad '
        'endpoint audit (4/5); the immutable original receipts passed their original audit options '
        '(5/5). S02 has the known broad-audit discrepancy, and is not silently reclassified as a '
        'newly accepted original fit.', '',
        '| Source | Profile full-objective calls | Profile orbit projections | Declared full-objective cap |',
        '| --- | ---: | ---: | ---: |']
    for sid in SOURCE_IDS:
        r=per.get((sid,'fitted-c','profile1000'))
        if r:lines.append(f"| {sid} | {r['evaluations']} | {r['orbit_projection_calls']} | {r['budget'].get('full_objectives','—')} |")
    lines+=['', '## Controlled c=0 sensitivity', '',
        'Fitted-c and c=0 use identical observations, fixed candidate banks, other priors and search '
        'allowances. Zero-c starts by setting the original fitted coefficient to zero while retaining '
        'the other original parameters. It therefore has its own matched continuation; comparing it '
        'only to the saved fitted-c original would conflate calibration and optimization.', '',
        '| Arm | Method | Completed / 5 | Full associations / 20,084 | Window associations / 693 | Assigned RMS Hz | KKT passes / 5 |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for a in summary['aggregates']:
        if a['method'] in ('original','A180') or a['method'].startswith('expanded_'):continue
        f,c=a['full'],a['challenge']
        lines.append(f"| {a['arm']} | {LABELS[a['method']]} | {f['completed_recordings']} | {f['associated']} | {c['associated']} | {fmt(f['associated_rms_hz'])} | {f['strict_accepted']} |")
    lines+=['', 'Source-level c, timing, configured-reference position and frequency metrics for both '
        'arms are retained in `iteration-summary.json`; calibration sensitivity is not localization '
        'accuracy evidence. Expanded-bank arms, when present, change the candidate population and '
        'are a separately labelled experiment.', '',
        '| Source | Profile fitted-c / zero-c associations | Profile fitted-c / zero-c RMS Hz | Profile fitted-c / zero-c configured-reference km |',
        '| --- | ---: | --- | --- |']
    for sid in SOURCE_IDS:
        fit=per.get((sid,'fitted-c','profile1000'));zero=per.get((sid,'zero-c','profile1000'))
        if fit and zero:
            lines.append(f"| {sid} | {fit['full']['associated']} / {zero['full']['associated']} | {fmt(fit['full']['associated_rms_hz'])} / {fmt(zero['full']['associated_rms_hz'])} | {fmt(fit['configured_reference_distance_km'])} / {fmt(zero['configured_reference_distance_km'])} |")
    temporal=summary['temporal']
    lines+=['', '## Restricted zero-contrast temporal stress test', '',
        'These runs exclude held measured CFO, but permanently fix both receiver high-minus-low '
        'band offsets to zero instead of relearning them from training data. Original learned offsets '
        'are approximately −14 to −17 kHz for RX1 and +37 to +44 kHz for RX2. The missing band '
        'columns add two independent calibration directions in every training fold. Thus this '
        'protocol does not match the original band-calibration learning procedure; low held '
        'coverage cannot be attributed entirely to generalization failure. See the '
        '[cold protocol audit](cold_protocol_audit.md).', '',
        'Profile and continuation are internally matched under this zero-contrast restriction. '
        'They use neutral training seeds and measured CFO only in the declared training half. '
        'Candidate banks originated from complete recordings, so this is also retrospective '
        'candidate-conditioned evaluation, not an untouched discovery test.', '',
        '| Direction | Arm | Method | Completed / 5 | Held associations / all held | Held assigned RMS Hz | Held-window associations / all held-window | Training KKT passes / 5 |',
        '| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for a in temporal['aggregates']:
        h,c=a['held'],a['held_challenge']
        lines.append(f"| {a['mode']} | {a['arm']} | {a['method']} | {a['completed_recordings']} | {h['associated']} / {h['observations']} ({h['association_pct']:.2f}%) | {fmt(h['associated_rms_hz'])} | {c['associated']} / {c['observations']} | {a['strict_training_accepted']} |")
    fitted_temporal=[a for a in temporal['aggregates'] if a['arm']=='fitted-c']
    if len(fitted_temporal)==4 and all(a['completed_recordings']==5 for a in fitted_temporal):
        profile=[a for a in fitted_temporal if a['method']=='profile']
        continuation=[a for a in fitted_temporal if a['method']=='continuation']
        ph=sum(a['held_challenge']['associated'] for a in profile)
        ch=sum(a['held_challenge']['associated'] for a in continuation)
        pf=sum(a['held']['associated'] for a in profile)
        cf=sum(a['held']['associated'] for a in continuation)
        lines+=['', f"Across both fitted-c directions, exact profile gives {ph}/693 held-window assignments "
            f"versus continuation's {ch}/693. Full held assignments total {pf:,}/20,084 versus {cf:,}/20,084. "
            'This supplies no clear held-window advantage within the restricted stress class. '
            'It does not adjudicate the complete production calibration procedure. Assigned-only '
            'RMS must be read with these differing support counts.']
    if not temporal['aggregates']:
        lines+=['', 'Temporal results are not present in this report snapshot.']
    expanded=summary['expanded_subset']['aggregates']
    if expanded:
        population=summary['expanded_subset'];en=population['observations'];ec=population['challenge_observations'];es=len(population['expected_sources'])
        lines+=['', '## Separate expanded-bank sensitivity', '',
            'These endpoints add candidates and therefore change the model population. They are not '
            'fixed-bank algorithm controls. This separately reported population contains '
            f"{', '.join(population['expected_sources'])}: {en:,} original observations and {ec} window rows. "
            'Pending or unattempted endpoints remain in the denominator and completed coverage is explicit. Expanded-bank '
            'arms are omitted from primary plots to preserve equal population and timing counts.', '',
            f'| Arm | Method | Completed / {es} | Full associations / {en:,} | Window associations / {ec} | New / lost original full support | KKT passes / {es} |',
            '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
        for a in expanded:
            f,c=a['full'],a['challenge']
            lines.append(f"| {a['arm']} | {LABELS[a['method']]} | {f['completed_recordings']} | {f['associated']} | {c['associated']} | {f['new_associations']} / {f['lost_associations']} | {f['strict_accepted']} |")
        for fixed in population['fixed_bank_profile_comparators']:
            match=next((a for a in expanded if (a['arm'],a['method'])==(fixed['arm'],'expanded_profile')),None)
            if match and match['full']['completed_recordings']==es:
                lines+=['', f"On exactly these same sources ({fixed['arm']}), fixed-bank profile has "
                    f"{fixed['full']['associated']:,}/{en:,} full and {fixed['challenge']['associated']}/{ec} "
                    f"window associations; expanded profile has {match['full']['associated']:,}/{en:,} "
                    f"and {match['challenge']['associated']}/{ec}. More candidates do not guarantee "
                    'better support in every window; per-window changes remain in the table above.']
    lines+=['', '## Plots and verification', '',
        '![Full context comparison](iteration-context.png)', '',
        '![All fixed windows](iteration-windows.png)', '',
        '![Residual CDFs with all observations retained in denominators](iteration-distributions.png)', '',
        '![Common and relative timing distributions](iteration-timing.png)', '',
        '![Configured-reference position comparison](iteration-position.png)', '',
        '![Matched c sensitivity](iteration-calibration.png)', '',
        *(['![Restricted zero-contrast temporal stress test](iteration-temporal.png)', ''] if temporal['aggregates'] else []),
        f"Verified {summary['verification']['records']} saved full-recording endpoints and "
        f"{temporal['completed_records']} temporal endpoints. NPZ observation times match the "
        'frozen source ordering to 1 ns; full and challenge association totals match saved JSON; every '
        'window membership count and original assignment count matches DSX01. The timing histograms '
        'use five common shifts and 215 original-candidate relative contrasts for each complete method. '
        'The separate expanded-bank arms are omitted from these plots.', '',
        'Rebuild with the pinned scientific Python: `python report_iteration.py`. The generator only '
        'reads saved JSON/NPZ endpoints, adds optional `results/*-arc` and `expanded-results` endpoints '
        'when present, and writes this report, `iteration-summary.json`, `window-comparison.csv` and '
        '`iteration-*.png`. No model evaluation or new fit occurs.']
    lines+=['', '## Latest checkpoint and outstanding work', '',
        'The [checkpoint](CHECKPOINT.md) adds the separate bounded numerical-cleanup '
        'audit, the failed training-only calibration-bootstrap smoke, the complete '
        'expanded-window plot, and the next experiments. These are not silently '
        'substituted into the original result tables above. The recovery goal remains active.']
    (HERE/'README.md').write_text('\n'.join(lines)+'\n')


if __name__=='__main__':
    main()
