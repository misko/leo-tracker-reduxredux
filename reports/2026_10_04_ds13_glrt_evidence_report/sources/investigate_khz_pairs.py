"""Read-only IQ cross-epoch checks for five near-1-kHz candidate pairs."""
import json,hashlib
from pathlib import Path
import numpy as np
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.analysis.starlink.pilot_methods import conditioned_glrt64_score
from candidate_guided_refinement import circular
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

B=Path('/srv/bulk/leo/ds13-spline-replay.4hywxT');BASE=B/'full-scan-A-refinement'
ROOT=Path('/home/mouse9911/gits/leo-tracker-reduxredux/reports')
bundle=json.loads((ROOT/'2026_10_02_ds13_timing_em/scans/scan-fw-911c4e5db9243281/bundle.json').read_text())
meta=bundle['alias_grouping']['representative_rows']
receipt=json.loads((BASE/'refined.json').read_text());records={r['row_index']:r for r in receipt['records']}
final=json.loads((BASE/'solver/A-fitted-c.json').read_text())['final'];owners={r['row_index']:r for r in final['assignments']}
with np.load(ROOT/'2026_10_03_ds13_coverage_goal/frozen/A-observations.npz') as z:times=z['times_s'].copy();channels=z['channel'].copy()
selected=[(4037,6433),(1829,5941),(3169,4735),(458,3707),(1334,1712)]
out=BASE/'khz-pair-audit';out.mkdir(exist_ok=True);results=[]
store=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True)
try:
    pub=store.inspect('scan-fw-911c4e5db9243281');assert pub.manifest_sha256==receipt['input_manifest_sha256']
    fs=int(pub.manifest.receipt.plan.geometry.sample_rate_hz)
    for pair in selected:
        r=[records[i] for i in pair];assert r[0]['probe_key']==r[1]['probe_key']
        visit_id,rx,probe=r[0]['probe_key'];assert probe==0
        visit,iq=store.read_visit_ci16(pub,visit_id);block=iq[:fs//50,rx,:]
        samples=(block[:,0].astype(float)+1j*block[:,1].astype(float))/32768.
        f=[x['output_hz'] for x in r];epochs=[x['refinement']['epoch'] for x in r];matrix=[]
        for e in epochs:
            row=[]
            for frequency in f:
                integer=int(round(e));s=conditioned_glrt64_score(samples,fs,epoch_sample=integer,fractional_epoch_offset_samples=e-integer,acquired_cfo_hz=frequency,edge=visit.event.target.edge,glrt_size=4096)
                row.append(dict(margin=s.margin,exact=s.exact_score,control=s.control_score,tracking_hz=s.tracking_cfo_hz))
            matrix.append(row)
        dt=abs((epochs[0]-epochs[1]+fs/750/2)%(fs/750)-fs/750/2)
        result=dict(rows=list(pair),probe=r[0]['probe_key'],channel=int(channels[pair[0]]),time_s=float(times[pair[0]]),separation_hz=abs(circular(f[0]-f[1])),epoch_separation_samples=dt,epoch_separation_us=dt/fs*1e6,original_frequencies_hz=[x['original_hz'] for x in r],refined_frequencies_hz=f,epochs=epochs,owners=[owners.get(i) for i in pair],glrt_epoch_by_frequency=matrix,probe_sha256=hashlib.sha256(block.tobytes()).hexdigest())
        results.append(result);print(json.dumps(result),flush=True)
finally:store.close()
(out/'audit.json').write_text(json.dumps(dict(results=results,selection='Five illustrative different-owner pairs near lower edge of >=1 kHz bin; not random.',caveat='GLRT retains residual frequency search; cross-epoch checks are not fixed-frequency or two-source model evidence. Satellite assignments are in-sample hypotheses.'),indent=2))
fig,axes=plt.subplots(1,5,figsize=(16,4),sharey=True)
for ax,r in zip(axes,results):
    labels=[str(x['catalog_number']) for x in r['owners']]
    # Different timing maxima can coexist even when frequency estimates are close.
    f=np.array(r['refined_frequencies_hz']);f=circular(f-f[0]);e=np.array(r['epochs']);e=(e-e[0]+fs/750/2)%(fs/750)-fs/750/2;e=e/fs*1e6
    ax.scatter(f/1000,e,s=65,c=['#0072b2','#d55e00'])
    for j in (0,1):ax.annotate(labels[j],(f[j]/1000,e[j]),xytext=(5,7),textcoords='offset points',fontsize=10)
    ax.set(title=f"{r['time_s']:.2f} s · RX{r['probe'][1]} CH{r['channel']}\nΔf = {r['separation_hz']:.0f} Hz",xlabel='Frequency relative to first (kHz)',xlim=(min(f/1000)-.5,max(f/1000)+.65));ax.grid(alpha=.2)
axes[0].set_ylabel('Frame epoch relative to first (µs)');axes[0].set_ylim(-450,450)
fig.suptitle('Near-1-kHz pairs occupy widely separated timing hypotheses in the SAME 20 ms probe')
fig.text(.5,.01,'Labels are current satellite assignments, not independently confirmed identities. Each panel has its own frequency origin.\nContrast: the converged 66204 alternatives differed by at most 0.181 sample (0.018 µs) in the targeted replay.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.12,1,.89));fig.savefig(out/'frequency-and-epoch-separation.png',dpi=150)
