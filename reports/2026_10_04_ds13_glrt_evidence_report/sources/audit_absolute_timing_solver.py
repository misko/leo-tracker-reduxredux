"""Validate corrected solver assignments and compare with the same old solver."""
import csv,json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from absolute_timing_solver import OUT,AbsoluteCalibration
import greedy_pool_two_scans as g
from greedy_restart_scan import compile_mode,evaluate
from replay import ROOT,NAMESPACE,digest
from benchmark import ALIAS_HZ
from plot_relaxed_coverage_leftovers import partition

def main():
    rows=[];sources={};ridge_audit={}
    ridge_source=NAMESPACE/'audit-A-RX1-CH4-ridge/audit.json';ridge=json.loads(ridge_source.read_text())
    for scan in ('A','B'):
        g.SCAN=scan;cal=AbsoluteCalibration();d=cal.d
        source=OUT/f'scan-{scan}'/'candidate-pool.json';pool=json.loads(source.read_text());orig=np.array(pool['original_rows']);lookup={int(r):i for i,r in enumerate(orig)}
        assert np.array_equal(orig,d.original_rows)
        for p,h in pool['sources'].items():assert digest(Path(p))==h
        oldpool=json.loads((NAMESPACE/f'greedy-restart-scan-{scan}'/'candidate-pool.json').read_text());assert pool['original_rows']==oldpool['original_rows']
        with np.load(ROOT/'frozen'/f'{scan}-observations.npz') as z:a={k:z[k].copy() for k in z.files}
        for arm in ('fitted-c','zero-c'):
            path=OUT/f'{scan}-{arm}.json';result=json.loads(path.read_text());assert result['source_sha256']==digest(source)
            oldpath=NAMESPACE/'penalty10-replacement'/f'{scan}-{arm}.json';old=json.loads(oldpath.read_text())['final'];sources.update({str(p):digest(p) for p in (source,path,oldpath)})
            for stage in ('initial','final'):
                r=result[stage];aa=r['assignments'];assert len(aa)==r['assigned']
                assert len(aa)==len({x['row_index'] for x in aa})==len({(int(a['group'][x['row_index']]),x['catalog_number']) for x in aa})
                assert len(r['selected'])==r['satellites']==len({x['catalog_number'] for x in aa})
                assert r['objective']==r['assigned']-10*r['satellites']
                for m in r['selected']:
                    raw=pool['arms'][arm][m['mode_index']];assert raw['catalog_number']==m['catalog_number'] and raw['offset_s']==m['offset_s']
                    assigned=[x for x in aa if x['catalog_number']==m['catalog_number']];rr=[lookup[x['row_index']] for x in assigned]
                    assert len(rr)==m['count'] and {x['mode_index'] for x in assigned}=={m['mode_index']}
                    mode=compile_mode(raw,d.receiver,d.channel);used=np.ones(len(orig),bool);used[rr]=False
                    assert set(evaluate(mode,used,d.group,d.times)['rows'])==set(rr)
                    if stage=='final':
                        e,v,_=cal.residual(arm,raw['satellite_index'],raw['offset_s'])
                        assert np.all(v[rr]) and np.all(abs(e[rr])<=600)
                        assert np.allclose(e[rr],[x['residual_hz'] for x in assigned],atol=1e-6,rtol=0)
                        if scan=='A' and m['catalog_number']==58622:
                            ridx=np.array([lookup[i] for i in ridge['ridge_rows']]);own={x['row_index']:x['catalog_number'] for x in aa}
                            ridge_audit[arm]=dict(selected_absolute_timing_s=m['offset_s'],rms_on_fixed_93_ridge_probes_hz=float(np.sqrt(np.mean(e[ridx]**2))),within600=int(sum(abs(e[ridx])<=600)),assigned_to_58622=sum(own.get(int(i))==58622 for i in ridge['ridge_rows']),unassigned=sum(int(i) not in own for i in ridge['ridge_rows']))
                            if arm=='fitted-c':
                                before=g.FrozenCalibration();bi=int(np.flatnonzero(before.data.numbers==58622)[0]);oldm=next(x for x in old['selected'] if x['catalog_number']==58622)
                                olde,_,_=before.residual(arm,bi,oldm['offset_s'])
                                fig,ax=plt.subplots(figsize=(12,4));ax.scatter(d.times[ridx],olde[ridx],s=20,c='#d65f27',label='Before fix: selected restart timing')
                                ax.scatter(d.times[ridx],e[ridx],s=20,c='#16845e',label='After fix: newly selected absolute timing')
                                ax.axhline(0,color='#555555',lw=.8)
                                for y in (-600,600):ax.axhline(y,color='#999999',ls=':')
                                ax.set(xlabel='Receive time (s)',ylabel='GLRT − predicted CFO (Hz)',title=f'Scan A RX1/CH4 · 58622 · same 93 ridge probes\nActual rerun solution: timing {m["offset_s"]:+.3f} s; RMS {ridge_audit[arm]["rms_on_fixed_93_ridge_probes_hz"]:.1f} Hz')
                                ax.grid(alpha=.2);ax.legend(fontsize=9);fig.tight_layout();fig.savefig(OUT/'58622-selected-timing-regression.png',dpi=160);plt.close(fig)
            f=result['final'];initial=result['initial'];old_by={x['row_index']:x for x in old['assignments']};new_by={x['row_index']:x for x in f['assignments']}
            same=[i for i in set(old_by)&set(new_by) if old_by[i]['catalog_number']==new_by[i]['catalog_number']]
            rms=lambda records,rr:float(np.sqrt(np.mean([records[i]['residual_hz']**2 for i in rr]))) if rr else None
            assert f['objective']>=initial['objective']
            row=dict(scan=scan,arm=arm,total=len(orig),before_assigned=old['assigned'],before_satellites=old['satellites'],before_score=old['objective'],before_coverage=old['coverage'],corrected_greedy_assigned=initial['assigned'],after_assigned=f['assigned'],after_unassigned=f['unassigned'],after_satellites=f['satellites'],after_score=f['objective'],after_coverage=f['coverage'],net_added=f['assigned']-old['assigned'],new_peaks=len(set(new_by)-set(old_by)),lost_peaks=len(set(old_by)-set(new_by)),same_identity_common_peaks=len(same),same_before_rms_hz=rms(old_by,same),same_after_rms_hz=rms(new_by,same),all_after_rms_hz=rms(new_by,list(new_by)),replacement_score_gain=f['objective']-initial['objective'],converged=result['converged'])
            rows.append(row);print(row,flush=True)
            remaining=partition(a['canonical_rows'],f['assignments']);assert len(remaining)==f['unassigned']
            y=((a['measured_hz']+ALIAS_HZ/2)%ALIAS_HZ-ALIAS_HZ/2)/1000
            fig,axes=plt.subplots(4,2,figsize=(16,13),sharex=True,sharey=True)
            for ci,ch in enumerate(sorted(np.unique(a['channel']))):
                for rx in (0,1):
                    rr=remaining[(a['receiver'][remaining]==rx)&(a['channel'][remaining]==ch)];ax=axes[ci,rx]
                    ax.scatter(a['times_s'][rr],y[rr],s=10,c='#555555',alpha=.75,lw=0);ax.set_title(f'RX{rx} · CH{ch} · {len(rr)} unassigned')
                    ax.set(xlim=(0,300),ylim=(-ALIAS_HZ/2000,ALIAS_HZ/2000));ax.grid(alpha=.18)
                    if rx==0:ax.set_ylabel('Wrapped measured CFO (kHz)')
                    if ci==3:ax.set_xlabel('Receive time (s)')
            fig.suptitle(f'Scan {scan} · corrected absolute timing · {arm}\n{f["assigned"]:,}/{len(orig):,} assigned ({f["coverage"]:.1%}); {len(remaining):,} unassigned',fontsize=15)
            fig.text(.5,.02,'Unassigned peaks only. Same penalty-10 greedy/replacement solver, ±600 Hz gate and coherence rules.\nRaw in-sample assignments; identities not certified. Receiver/RF calibration unchanged.',ha='center',fontsize=10)
            fig.tight_layout(rect=(0,.065,1,.94));fig.savefig(OUT/f'{scan}-{arm}-unassigned.png',dpi=150);plt.close(fig)
    with (OUT/'comparison.csv').open('x',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    with (OUT/'audit.json').open('x') as f:json.dump(dict(status='passed',rows=rows,ridge_58622=ridge_audit,sources=sources,limitations=['Raw posthoc coverage, not held-out or identity-certified.','Receiver/RF nuisance calibration is still fold-specific; only satellite timing consistency changed.','Local greedy-repair fixed point is not global optimality.']),f,indent=2)
    fig,ax=plt.subplots(figsize=(10,5));labels=[f"{r['scan']} · {r['arm']}" for r in rows];xx=np.arange(len(rows))
    for shift,key,label,color in [(-.2,'before_coverage','Before timing fix','#aaaaaa'),(.2,'after_coverage','After timing fix','#16845e')]:
        values=[100*r[key] for r in rows];bars=ax.bar(xx+shift,values,.38,label=label,color=color)
        ax.bar_label(bars,labels=[f'{v:.1f}%' for v in values],padding=3)
    ax.axhline(90,color='#555555',ls='--',label='90% target');ax.set_xticks(xx,labels);ax.set(ylabel='Assigned canonical GLRT peaks (%)',ylim=(0,100),title='One absolute timing shift per satellite · same penalty-10 solver')
    ax.legend(loc='lower right');ax.grid(axis='y',alpha=.2);ax.set_axisbelow(True);fig.tight_layout();fig.savefig(OUT/'coverage-before-after.png',dpi=160);plt.close(fig)
    print('AUDIT PASSED; 58622',ridge_audit,flush=True)

if __name__=='__main__':main()
