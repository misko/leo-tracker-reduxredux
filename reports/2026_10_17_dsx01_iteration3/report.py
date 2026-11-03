"""Read-only comparisons of complete iteration-3 protocols on frozen DSX01."""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
OLD=REPORTS/'2026_10_16_dsx01_models'
PREV=REPORTS/'2026_10_16_dsx01_iteration2'
DATA=REPORTS/'2026_10_16_dsx01_fast_association_losses'
SOURCES=['S01','S02','S03','S04','S05']
LABELS={'original':'Original','fixed':'Exact profile, fixed candidates',
        'expanded':'Exact profile, expanded candidates','sigma1':'Fixed profile, timing prior 1 s',
        'sigma0p5':'Fixed profile, timing prior 0.5 s','space-track':'Fixed profile, causal Space-Track',
        'annealing':'Fixed profile + frequency-width continuation',
        'extra-continuation':'Fixed profile + extra 125 Hz continuation'}
COLORS=dict(zip(LABELS,['#777777','#0072b2','#d55e00','#009e73','#cc79a7','#9467bd','#e6ab02','#4d4d00']))


def csv_read(path):
    with path.open() as stream:return list(csv.DictReader(stream))


def csv_write(path,rows):
    with path.open('w',newline='') as stream:
        writer=csv.DictWriter(stream,fieldnames=list(rows[0]))
        writer.writeheader();writer.writerows(rows)


def rms(values):
    return float(np.sqrt(np.mean(np.asarray(values)**2))) if len(values) else None


def path_for(method,sid,arm):
    if method=='original':return OLD/'results'/f'{sid}-full-fitted-c-original.json'
    if method=='fixed':return PREV/'results'/f'{sid}-{arm}-profile.json'
    if method=='expanded':return PREV/'expanded-results'/f'{sid}-{arm}-profile.json'
    if method in ('sigma1','sigma0p5'):
        return HERE/'timing/results'/f'{sid}-{method}-{arm}-profile.json'
    if method=='space-track':
        if sid in ('S01','S05'):return HERE/'ephemeris/results'/f'{sid}-{arm}-profile.json'
        # These three original snapshots are byte-identical to causal latest ST.
        return PREV/'results'/f'{sid}-{arm}-profile.json'
    if method in ('annealing','extra-continuation'):
        name='annealing' if method=='annealing' else 'continuation'
        return HERE/'support/annealing'/f'uniform_fit_{sid}_{arm}_{name}.json'
    raise ValueError(method)


def main():
    regions=csv_read(DATA/'regions.csv')
    observations=[json.loads(line) for line in (DATA/'context-observations.jsonl').read_text().splitlines()]
    source_obs={s:[o for o in observations if o['source_id']==s] for s in SOURCES}
    lookup={s:{o['observation_id']:i for i,o in enumerate(source_obs[s])} for s in SOURCES}
    members=csv_read(DATA/'membership.csv')
    indices={r['region_id']:np.array([lookup[r['source_id']][m['observation_id']] for m in members
                                    if m['region_id']==r['region_id']],int) for r in regions}
    states={};records={};bindings={}
    anneal_path=HERE/'support/annealing/uniform_evaluation.json'
    anneal_rows=json.loads(anneal_path.read_text())['rows'] if anneal_path.exists() else []
    def state_path(path):
        return path.with_name(path.name.replace('uniform_fit_','uniform_eval_')).with_suffix('.npz')
    complete={};incomplete=[]
    for arm in ['fitted-c','zero-c']:
        complete[arm]=[]
        for method in LABELS:
            if method=='original' and arm=='zero-c':continue
            paths=[path_for(method,sid,arm) for sid in SOURCES]
            missing=[str(p) for p in paths if not p.exists() or not state_path(p).exists()]
            if missing:
                incomplete.append(dict(method=method,arm=arm,missing=missing));continue
            complete[arm].append(method)
            for sid,path in zip(SOURCES,paths):
                record=json.loads(path.read_text())
                if method in ('annealing','extra-continuation'):
                    name='annealing' if method=='annealing' else 'continuation'
                    row=next(r for r in anneal_rows if r['source_id']==sid and r['arm']==arm and r['method']==name)
                    record=dict(record,full_scan=row['full'],audit=row['audit'])
                    bindings[str(anneal_path.resolve())]='sha256:'+hashlib.sha256(anneal_path.read_bytes()).hexdigest()
                with np.load(state_path(path)) as data:state={k:data[k] for k in data.files}
                # Frozen context stores time_s; inspect it explicitly rather than
                # accepting equal row counts as proof of row alignment.
                expected=np.array([o['time_s'] for o in source_obs[sid]])
                np.testing.assert_allclose(state['times_s'],expected,atol=1e-9,rtol=0)
                assert int(state['associated'].sum())==record['full_scan']['associated']
                records[arm,method,sid]=record;states[arm,method,sid]=state
                for p in [path,state_path(path)]:
                    bindings[str(p.resolve())]='sha256:'+hashlib.sha256(p.read_bytes()).hexdigest()
    summary=[];window_rows=[];source_rows=[]
    for arm,methods in complete.items():
        for method in methods:
            assigned=[];old_assigned=[];residuals=[];old_residuals=[];intersection_residuals=[];changed_identity=0
            for sid in SOURCES:
                state=states[arm,method,sid];old=states['fitted-c','original',sid]
                a,b=state['associated'],old['associated'];use=a&b
                assigned.extend(a);old_assigned.extend(b)
                residuals.extend(state['residual_hz'][a]);old_residuals.extend(old['residual_hz'][use])
                intersection_residuals.extend(state['residual_hz'][use])
                changed_identity+=int(np.sum(use&(state['satellite_number']!=old['satellite_number'])))
                record=records[arm,method,sid]
                audit=record.get('audit',record.get('endpoint_audit',{}))
                source_rows.append(dict(arm=arm,method=method,source_id=sid,associated=int(a.sum()),
                    original_associated=int(b.sum()),new=int(np.sum(a&~b)),lost=int(np.sum(b&~a)),
                    assigned_rms_hz=rms(state['residual_hz'][a]),
                    intersection_original_rms_hz=rms(old['residual_hz'][use]),
                    intersection_variant_rms_hz=rms(state['residual_hz'][use]),
                    configured_reference_km=record['full_scan'].get('configured_reference_distance_km'),
                    nll=record['full_scan']['likelihood_nll'],objective=record['full_scan']['objective'],
                    kkt=audit.get('stationarity'),strict=audit.get('accepted',False)))
            a,b=np.array(assigned),np.array(old_assigned)
            for region in regions:
                sid=region['source_id'];ix=indices[region['region_id']]
                aa=states[arm,method,sid]['associated'][ix]
                bb=states['fitted-c','original',sid]['associated'][ix]
                assert len(ix)==int(region['observation_count'])
                assert int(bb.sum())==int(region['original_associated_count'])
                new,lost=int(np.sum(aa&~bb)),int(np.sum(bb&~aa))
                window_rows.append(dict(arm=arm,method=method,source_id=sid,region_id=region['region_id'],
                    observations=len(ix),original=int(bb.sum()),associated=int(aa.sum()),new=new,lost=lost,
                    net_missing_restored_pct=100*(new-lost)/int((~bb).sum())))
            selected=[r for r in window_rows if r['arm']==arm and r['method']==method]
            assert sum(r['observations'] for r in selected)==693 and len(a)==20084
            summary.append(dict(arm=arm,method=method,observations=len(a),associated=int(a.sum()),
                new=int(np.sum(a&~b)),lost=int(np.sum(b&~a)),identity_swaps_on_retained=changed_identity,
                window_associated=sum(r['associated'] for r in selected),
                major_windows=sum(r['net_missing_restored_pct']>=80 for r in selected),
                assigned_rms_hz=rms(residuals),strict_endpoints=sum(r['strict'] for r in source_rows
                    if r['arm']==arm and r['method']==method),
                intersection_original_rms_hz=rms(old_residuals),
                intersection_variant_rms_hz=rms(intersection_residuals)))
    csv_write(HERE/'comparison.csv',summary);csv_write(HERE/'windows.csv',window_rows)
    csv_write(HERE/'sources.csv',source_rows)
    fig,axes=plt.subplots(1,2,figsize=(13,5),constrained_layout=True)
    for method in complete['fitted-c']:
        values=np.concatenate([states['fitted-c',method,s]['residual_hz'][states['fitted-c',method,s]['associated']] for s in SOURCES])
        x=np.sort(abs(values))
        grid=np.r_[1.,x[(x>1)&(x<1000)],1000.]
        axes[0].step(grid,np.searchsorted(x,grid,side='right')/20084,where='post',
            color=COLORS[method],label=LABELS[method])
        dist=sorted(records['fitted-c',method,s]['full_scan']['configured_reference_distance_km'] for s in SOURCES)
        grid=np.r_[.1,dist,1000.]
        axes[1].step(grid,np.searchsorted(dist,grid,side='right')/5,where='post',color=COLORS[method],label=LABELS[method])
    axes[0].set(xlim=(1,1000),ylim=(0,1),xscale='log',xlabel='Absolute assigned CFO residual (Hz)',
                ylabel='Fraction of all 20,084 observations')
    axes[1].set(xlim=(.1,1000),ylim=(0,1),xscale='log',xlabel='Configured-reference distance (km)',
                ylabel='Fraction of five recordings')
    for ax in axes:ax.grid(alpha=.2)
    axes[0].legend(fontsize=7,loc='upper left')
    fig.suptitle('DSX01 iteration 3: frequency coverage and position remain separate\nFitted-c warm development fits; unassociated observations stay in the left denominator')
    fig.savefig(HERE/'performance-cdfs.png',dpi=170);plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(12,4.8),constrained_layout=True)
    for method in complete['fitted-c']:
        total=[];relative=[]
        for sid in SOURCES:
            baseline=records['fitted-c','original',sid]['full_scan']['total_timing_s']
            metric=records['fitted-c',method,sid]['full_scan']
            for number in baseline:
                t=metric['total_timing_s'][number];total.append(t);relative.append(t-metric['common_timing_s'])
        assert len(total)==215
        for ax,values in zip(axes,[total,relative]):
            bins=np.arange(-32,34,2)
            assert np.histogram(values,bins=bins)[0].sum()==215
            ax.hist(values,bins=bins,histtype='step',lw=1.7,color=COLORS[method],label=LABELS[method])
    axes[0].set_xlabel('Total fitted orbit-time offset (s)')
    axes[1].set_xlabel('Offset after removing common recording shift (s)')
    for ax in axes:ax.set_ylabel('Same 215 recording–satellite pairs / 2 s bin');ax.grid(axis='y',alpha=.2)
    axes[0].legend(fontsize=7)
    fig.suptitle('DSX01 iteration 3: matched-cohort timing histograms, fitted c\nFitted model offsets do not independently measure ephemeris error')
    fig.savefig(HERE/'timing-histograms.png',dpi=170);plt.close(fig)
    methods=complete['fitted-c']
    matrix=np.array([[100*next(w['associated']/w['observations'] for w in window_rows
                             if w['arm']=='fitted-c' and w['method']==m and w['region_id']==r['region_id'])
                      for m in methods] for r in regions])
    fig,ax=plt.subplots(figsize=(12.8,9.5),constrained_layout=True)
    im=ax.imshow(matrix,vmin=0,vmax=100,cmap='Blues',aspect='auto')
    ax.set_yticks(np.arange(15),[f"{r['region_id'][-3:]} {r['source_id']} RX{r['receiver']}/CH{r['channel']} {float(r['start_s']):g}–{float(r['end_s']):g}s" for r in regions])
    short={'original':'Original','fixed':'Fixed\n2 s prior','expanded':'Expanded\n2 s prior',
           'sigma1':'Fixed\n1 s prior','sigma0p5':'Fixed\n0.5 s prior','space-track':'Fixed\ncausal ST',
           'annealing':'Profile +\nwidth stages','extra-continuation':'Profile +\n125 Hz refit'}
    ax.set_xticks(np.arange(len(methods)),[short[m] for m in methods])
    for row,r in enumerate(regions):
        for col,m in enumerate(methods):
            w=next(w for w in window_rows if w['arm']=='fitted-c' and w['method']==m and w['region_id']==r['region_id'])
            ax.text(col,row,f"{w['associated']}/{w['observations']}",ha='center',va='center',
                    color='white' if matrix[row,col]>65 else 'black',fontsize=9)
    fig.colorbar(im,ax=ax,label='Associated / all frozen window observations (%)',shrink=.65)
    ax.set_title('DSX01: same 15 windows across complete protocols, fitted c\nCounts describe association, not verified identity or position accuracy',pad=15)
    fig.savefig(HERE/'window-coverage.png',dpi=170);plt.close(fig)
    lines=['# DSX01 iteration 3: controlled recovery experiments','',
        'All results retain the same 15 windows, 693 window observations and 20,084 complete-scan observations. '
        'These are full-data warm development comparisons; identities are hypotheses, and configured-reference '
        'distances are not surveyed truth. Station coordinates do not seed or select any fit. '
        'Incomplete methods are excluded from aggregate plots and listed in summary.json.', '',
        '| Arm | Method | Full associations | Window associations | ≥80% net-restored windows | New / lost original support | Assigned RMS Hz | Strict endpoints |',
        '|---|---|---:|---:|---:|---:|---:|---:|']
    for r in summary:
        lines.append(f"| {r['arm']} | {LABELS[r['method']]} | {r['associated']}/20084 | {r['window_associated']}/693 | {r['major_windows']}/15 | {r['new']} / {r['lost']} | {r['assigned_rms_hz']:.2f} | {r['strict_endpoints']}/5 |")
    lines+=['','Width continuation reaches 455/693 window associations versus its matched extra-125-Hz '
            'control’s 422/693, but replaces more original full-scan support and has only two strict raw '
            'endpoints. Expanded profile reaches 434/693 and retains more complete-scan assignments. '
            'No method wins all criteria. See [the measured findings](FINDINGS.md) for the tradeoffs '
            'and why the recovery/generalization goal remains active.', '',
            'Assigned RMS uses each variant’s own associated set and can improve through selection. '
            'New/lost support and the all-observation CDF expose this change. '
            'Original fitted-c is a context baseline for both arms; c=0 comparisons require their '
            'matched c=0 method controls. Total objectives across different priors are not comparable.', '',
            '![All 15 window counts](window-coverage.png)','','![Coverage and position CDFs](performance-cdfs.png)','','![Timing histograms](timing-histograms.png)','',
            'Causal Space-Track changes only S01/S05. S02–S04 already used the identical latest-causal '
            'Space-Track digest, so their original fixed-profile receipts are exact identity controls. '
            'Both providers retain the same selected candidate IDs, original warm seed, fixed band '
            'contrasts, priors and 1000-call/120-second profile allowance. This is not a rerun of '
            'candidate discovery or an end-to-end provider comparison.', '',
            'Frequency-width continuation starts at the saved fixed profile, uses intermediate widths '
            '1000→500→250→125 Hz, and evaluates final counts, RMS and selection at the original 125 Hz. '
            'It has an additional 1000-objective/120-second allowance after the profile. Its matched '
            'control uses that same extra allowance entirely at 125 Hz. Thus comparisons to a profile '
            'alone combine algorithm and added budget. These curves use the raw algorithm endpoints '
            'uniformly across all five sources; supplementary numerical finishing is separate.', '',
            'Training-only calibration and support-portfolio pilots are documented in their component '
            'directories and are not pooled with these full five-source protocols unless complete.', '',
            '[Window-level CSV](windows.csv) · [Source-level CSV](sources.csv) · [Protocol](PROTOCOL.md)']
    (HERE/'README.md').write_text('\n'.join(lines)+'\n')
    (HERE/'summary.json').write_text(json.dumps(dict(comparisons=summary,incomplete=incomplete,
         input_bindings=[dict(path=p,sha256=s) for p,s in sorted(bindings.items())]),indent=2)+'\n')
    print(json.dumps(dict(comparisons=summary,incomplete_protocol_count=len(incomplete)),indent=2))


if __name__=='__main__':main()
