"""Audit unchanged-denominator solver rerun and make scan-wide plots."""
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from solve_refined_scan_A import RefinedCalibration,SOURCE
from replay import NAMESPACE,digest
from greedy_restart_scan import compile_mode,evaluate
from candidate_guided_refinement import circular

def main():
    base=NAMESPACE/'full-scan-A-refinement';out=base/'solver'
    cal=RefinedCalibration();d=cal.d;lookup={int(r):i for i,r in enumerate(d.original_rows)}
    pool=json.loads((out/'scan-A/candidate-pool.json').read_text());assert pool['original_rows']==d.original_rows.tolist()
    for path,h in pool['sources'].items():assert digest(__import__('pathlib').Path(path))==h
    refined=json.loads(SOURCE.read_text());records=refined['records'];rrmap={r['row_index']:r for r in records}
    assert len(rrmap)==7382
    stats=dict(refined=sum(r['refinement']['status']=='refined' for r in records),fallback=sum(r['refinement']['status']!='refined' for r in records),wall_s=refined['elapsed_s'],workers=refined['workers'])
    arms=[]
    for arm in ('fitted-c','zero-c'):
        result=json.loads((out/f'A-{arm}.json').read_text());f=result['final'];old=json.loads((NAMESPACE/'absolute-timing-penalty10'/f'A-{arm}.json').read_text())['final']
        aa=f['assignments'];assert len(aa)==f['assigned']==len({r['row_index'] for r in aa})
        assert len(aa)==len({(r['catalog_number'],int(d.group[lookup[r['row_index']]])) for r in aa})
        assert f['objective']==f['assigned']-10*f['satellites']
        for m in f['selected']:
            raw=pool['arms'][arm][m['mode_index']];assert raw['catalog_number']==m['catalog_number'] and raw['offset_s']==m['offset_s']
            chosen=[r for r in aa if r['catalog_number']==m['catalog_number']];ix=np.array([lookup[r['row_index']] for r in chosen])
            e,v,_=cal.residual(arm,raw['satellite_index'],raw['offset_s']);assert np.all(v[ix]) and np.all(abs(e[ix])<=600)
            assert np.allclose(e[ix],[r['residual_hz'] for r in chosen],atol=1e-6,rtol=0)
            used=np.ones(len(d.times),bool);used[ix]=False
            assert set(evaluate(compile_mode(raw,d.receiver,d.channel),used,d.group,d.times)['rows'])==set(ix)
        # Fixed old memberships and old orbit residuals: isolate measurement change.
        olde=np.array([r['residual_hz'] for r in old['assignments']])
        newe=np.array([circular(r['residual_hz']+rrmap[r['row_index']]['output_hz']-rrmap[r['row_index']]['original_hz']) for r in old['assignments']])
        off=abs(olde)>300
        metric=dict(arm=arm,before_assigned=old['assigned'],after_assigned=f['assigned'],before_coverage=old['coverage'],after_coverage=f['coverage'],before_satellites=old['satellites'],after_satellites=f['satellites'],before_score=old['objective'],after_score=f['objective'],converged=result['converged'],unassigned=7382-f['assigned'],fixed_old_membership_rms_before=float(np.sqrt(np.mean(olde**2))),fixed_old_membership_rms_after=float(np.sqrt(np.mean(newe**2))),old_assigned_outside300=int(sum(off)),moved_inside300=int(sum(off&(abs(newe)<=300))),previously_inside_moved_outside300=int(sum(~off&(abs(newe)>300))))
        arms.append(metric);print(metric,flush=True)
        assigned=np.zeros(len(d.times),bool);assigned[[lookup[r['row_index']] for r in aa]]=True
        for kind,mask in [('unassigned',~assigned),('assigned',assigned)]:
            fig,axes=plt.subplots(4,2,figsize=(14,12),sharex=True,sharey=True)
            for ci,ch in enumerate(sorted(set(d.channel))):
                for rx in (0,1):
                    ix=mask&(d.channel==ch)&(d.receiver==rx);ax=axes[ci,rx]
                    ax.scatter(d.times[ix],circular(d.measured[ix])/1000,s=8,c='#777777' if kind=='unassigned' else '#0072b2')
                    ax.set(title=f'RX{rx} · CH{ch} · {sum(ix)} {kind}',xlim=(0,300),ylim=(-114,114));ax.grid(alpha=.15)
                    if rx==0:ax.set_ylabel('Wrapped CFO (kHz)')
                    if ci==3:ax.set_xlabel('Receive time (s)')
            fig.suptitle(f'Scan A · candidate-only GLRT refinement · {arm}\n{f["assigned"]}/7382 assigned ({f["coverage"]:.1%}) · {kind} only')
            fig.text(.5,.015,'Original denominator and peak exclusivity retained. No duplicate merging; frozen receiver/RF calibration.\nRaw in-sample assignments, not identity-certified coverage.',ha='center',fontsize=9)
            fig.tight_layout(rect=(0,.05,1,.94));fig.savefig(out/f'{arm}-{kind}.png',dpi=150);plt.close(fig)
    (out/'audit.json').write_text(json.dumps(dict(status='passed',refinement=stats,arms=arms),indent=2))
    fig,ax=plt.subplots(figsize=(8,4));x=np.arange(2)
    for dx,key,label,color in [(-.2,'before_coverage','Original GLRT','#aaaaaa'),(.2,'after_coverage','Refined GLRT','#0072b2')]:
        bars=ax.bar(x+dx,[100*r[key] for r in arms],.38,label=label,color=color);ax.bar_label(bars,fmt='%.1f%%',padding=3)
    ax.set(xticks=x,xticklabels=['Fitted c','c = 0'],ylabel='Assigned original hypotheses (%)',ylim=(0,100),title='Scan A · same penalty-10 solver · 7,382 original hypotheses');ax.legend();fig.tight_layout();fig.savefig(out/'coverage-comparison.png',dpi=170)

if __name__=='__main__':main()
