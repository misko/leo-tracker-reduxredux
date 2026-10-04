"""Selected 46-probe experiment; orbit used only after refinement for reporting."""
import json,time,hashlib
from pathlib import Path
import numpy as np
from candidate_guided_refinement import refine,circular
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

B=Path('/srv/bulk/leo/ds13-spline-replay.4hywxT')
SOURCE=B/'66204-orbit-glrt-replay-all/replay.json'
BUNDLE=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports/2026_10_02_ds13_timing_em/scans/scan-fw-911c4e5db9243281/bundle.json')
def main():
    prior=json.loads(SOURCE.read_text());meta=json.loads(BUNDLE.read_text())['alias_grouping']['representative_rows']
    out=B/'66204-candidate-guided-refinement';out.mkdir(exist_ok=True)
    assert not (out/'results.json').exists()
    store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True);start=time.monotonic();results=[];compute=0.;baseline=0.
    try:
        pub=store.inspect('scan-fw-911c4e5db9243281');assert pub.manifest_sha256==prior['manifest_sha256']
        fs=prior['sample_rate_hz']
        for p in prior['results']:
            if time.monotonic()-start>180:raise TimeoutError('Bounded replay')
            visit_id,rx,probe_id=p['probe_key'];assert probe_id==0
            visit,iq=store.read_visit_ci16(pub,visit_id);block=iq[:fs//50,rx,:]
            assert hashlib.sha256(block.tobytes()).hexdigest()==p['probe_sha256']
            samples=(block[:,0].astype(float)+1j*block[:,1].astype(float))/32768.
            def score(f,e,size=4096):
                integer=int(round(e));s=conditioned_glrt64_score(samples,fs,epoch_sample=integer,
                    fractional_epoch_offset_samples=e-integer,acquired_cfo_hz=float(f),edge=visit.event.target.edge,glrt_size=size)
                return dict(tracking_cfo_hz=s.tracking_cfo_hz,margin=s.margin,exact=s.exact_score,control=s.control_score)
            rows=[]
            for old in p['rows']:
                m=meta[old['row']];epoch=m['integer_epoch_sample']+m['fractional_epoch_offset_samples']
                tic=time.monotonic();original=score(m['acquired_cfo_hz'],epoch,512);baseline+=time.monotonic()-tic
                assert abs(original['margin']-old['original']['margin'])<1e-4
                tic=time.monotonic();r=refine(score,m['tracking_cfo_hz'],epoch);compute+=time.monotonic()-tic
                # Orbit first enters here, strictly after candidate-only refinement.
                if r['status']=='refined':r['orbit_residual_hz']=float(circular(r['tracking_cfo_hz']-p['predicted_wrapped_hz']))
                rows.append(dict(row=old['row'],assigned=old['assigned'],original=old['original'],orbit_guided=old['orbit_centered'],refined=r))
            results.append(dict(time_s=p['time_s'],probe_key=p['probe_key'],rows=rows))
            print('completed',len(results),'of',len(prior['results']),flush=True)
    finally:store.close()
    summary=dict(probes=len(results),hypotheses=sum(len(p['rows']) for p in results),refinement_seconds=compute,baseline_glrt_seconds=baseline,wall_seconds=time.monotonic()-start)
    assert all(r['refined']['status']=='refined' for p in results for r in p['rows'])
    for stage in ('original','refined'):
        summary[stage]={}
        for name,assigned in [('assigned',True),('alternatives',False)]:
            v=[r[stage] for p in results for r in p['rows'] if r['assigned']==assigned]
            summary[stage][name]=dict(rms_hz=float(np.sqrt(np.mean([x['orbit_residual_hz']**2 for x in v]))),median_margin=float(np.median([x['margin'] for x in v])))
        sep=[abs(circular(r[stage]['tracking_cfo_hz']-p['rows'][0][stage]['tracking_cfo_hz'])) for p in results for r in p['rows'][1:]]
        summary[stage]['pair_separation_hz']=dict(median=float(np.median(sep)),max=float(max(sep)),within_60=sum(v<=60 for v in sep),within_100=sum(v<=100 for v in sep))
    summary['margin_improved']=sum(r['refined']['margin']>r['original']['margin'] for p in results for r in p['rows'])
    (out/'results.json').write_text(json.dumps(dict(summary=summary,results=results,selection='Same previously orbit-selected 46 probes; refinement itself uses no orbit or satellite ID.',source_hashes={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in (SOURCE,BUNDLE,Path(__file__),B/'candidate_guided_refinement.py')},limitations=['Selected single-track diagnostic, not blind population validation.','No production detector, assignments or denominators changed.','Full 4096-bin GLRT maximum searched; maxima beyond local 1 kHz gate rejected, not a direct local-only optimizer.']),indent=2))
    fig,axes=plt.subplots(2,1,figsize=(12,8),sharex=True,sharey=True)
    for ax,stage,title in zip(axes,['original','refined'],['Before','After candidate-guided refinement — no orbit input']):
        for assigned in (False,True):
            pairs=[(p['time_s'],r[stage]['orbit_residual_hz']) for p in results for r in p['rows'] if r['assigned']==assigned]
            ax.scatter(*np.array(pairs).T,s=45 if assigned else 24,facecolors='none' if assigned else '#777777',edgecolors='#0072b2' if assigned else '#777777',label='Originally assigned' if assigned else 'Originally unassigned alternatives',zorder=4 if assigned else 3)
        ax.axhline(0,c='#d55e00',lw=1);ax.grid(alpha=.15);ax.set(ylim=(-650,650),ylabel='GLRT − saved orbit prediction (Hz)',title=title+f"\nRMS: assigned {summary[stage]['assigned']['rms_hz']:.1f} Hz · alternatives {summary[stage]['alternatives']['rms_hz']:.1f} Hz")
    axes[0].legend();axes[1].set_xlabel('Receive time (s)')
    fig.suptitle('Scan A · RX1 / CH3 · 135 hypotheses in the same 46 probes',fontsize=14)
    fig.text(.5,.015,'Each candidate starts from its own saved frequency and epoch. Orbit used only to calculate these residuals.\nThree bounded iterations; neighboring alias branches; fractional-epoch refinement; no merging or reassignment.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.07,1,.94));fig.savefig(out/'before-after.png',dpi=160)
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
