"""Compare fixed versus phase-continuous per-dwell GLRT frequency correction."""
import csv
import hashlib
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import zstandard

HERE = Path(__file__).resolve().parent
RATE = 10_000_000
WINDOW = 16384


def main():
    selection = json.loads((HERE/'selection.json').read_text())
    visits = {int(r['visit_index']): r for r in csv.DictReader((HERE.parent/'acquisition/visit-inventory.csv').open())}
    candidates = {(int(r['visit_index']), int(r['receiver_id'])): r for r in selection['candidate_rows']}
    indices = selection['visit_indices']
    counters = np.array([int(visits[i]['valid_start_counter']) for i in indices], dtype=np.int64)
    starts = (counters-counters[0])/RATE
    frequencies = np.array([float(candidates[i, 1]['tracking_absolute_baseband_cfo_hz'])-float(candidates[i, 0]['tracking_absolute_baseband_cfo_hz']) for i in indices])
    # Integrate piecewise-constant frequency. Previous frequency spans each gap.
    cycles_at_start = np.r_[0., np.cumsum(frequencies[:-1]*np.diff(starts))]
    assert np.allclose(cycles_at_start[1:], cycles_at_start[:-1]+frequencies[:-1]*np.diff(starts), atol=1e-9)
    source = Path('/srv/bulk/leo/scanner-adaptive-recordings/scan-fw-32a202b6e55630ec')
    manifest = json.loads((source/'manifest.json').read_text())['manifest']
    taper = np.hanning(WINDOW)**2
    rows, summaries = [], []
    for k, index in enumerate(indices):
        chunk = manifest['chunks'][index]
        raw = zstandard.ZstdDecompressor().decompress((source/chunk['relative_path']).read_bytes(), max_output_size=chunk['uncompressed_bytes'])
        assert 'sha256:'+hashlib.sha256(raw).hexdigest() == chunk['uncompressed_sha256']
        iq = np.frombuffer(raw,dtype='<i2').reshape(-1,2,2)
        x = iq[...,0].astype(float)+1j*iq[...,1].astype(float)
        dwell_rows = []
        for start in range(0,len(x)-WINDOW+1,WINDOW):
            local = np.arange(start,start+WINDOW)/RATE
            t = starts[k]+local
            a,b = x[start:start+WINDOW,0],x[start:start+WINDOW,1]
            product = np.conj(a)*b*taper
            denominator = np.sqrt(np.sum(abs(a)**2*taper)*np.sum(abs(b)**2*taper))
            fixed = np.sum(product*np.exp(-2j*np.pi*frequencies[0]*t))
            variable = np.sum(product*np.exp(-2j*np.pi*(cycles_at_start[k]+frequencies[k]*local)))
            row = dict(visit_index=index,time_s=float(t.mean()),fixed_phase_deg=float(np.angle(fixed,deg=True)),dwell_phase_deg=float(np.angle(variable,deg=True)),fixed_coherence=float(abs(fixed)/denominator),dwell_coherence=float(abs(variable)/denominator),delta_f_hz=float(frequencies[k]))
            rows.append(row)
            dwell_rows.append(row)
        summary = dict(visit_index=index,delta_f_hz=float(frequencies[k]),change_from_first_hz=float(frequencies[k]-frequencies[0]))
        for name in ('fixed','dwell'):
            summary[name+'_median_coherence'] = float(np.median([r[name+'_coherence'] for r in dwell_rows]))
            summary[name+'_phase_R'] = float(abs(np.mean(np.exp(1j*np.radians([r[name+'_phase_deg'] for r in dwell_rows])))))
        summaries.append(summary)
    # Same samples and first-dwell correction must reproduce the baseline.
    baseline = list(csv.DictReader((HERE/'phase-vs-time.csv').open()))
    assert len(baseline)==len(rows)
    for original, row in zip(baseline, rows):
        error = (float(original['phase_difference_deg'])-row['fixed_phase_deg']+180)%360-180
        assert abs(error)<1e-5
    assert all(abs(r['fixed_phase_deg']-r['dwell_phase_deg'])<1e-7 for r in rows if r['visit_index']==indices[0])
    with (HERE/'dwell-cfo-comparison.csv').open('w',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=rows[0].keys());writer.writeheader();writer.writerows(rows)
    result = dict(policy='Per-dwell physical GLRT difference, unchanged candidate ranks/aliases; integrated phase continuous at dwell starts; previous frequency held over gaps; no phase fit.',dwells=summaries,
                  fixed_median_coherence=float(np.median([r['fixed_coherence'] for r in rows])),dwell_median_coherence=float(np.median([r['dwell_coherence'] for r in rows])))
    (HERE/'dwell-cfo-summary.json').write_text(json.dumps(result,indent=2)+'\n')
    fig, axes = plt.subplots(4,1,figsize=(12,10),sharex=True,constrained_layout=True,gridspec_kw={'height_ratios':[2,2,1,1]})
    t=np.array([r['time_s'] for r in rows])
    for ax,name,title in zip(axes[:2],('fixed','dwell'),('Fixed first-dwell Δf','Each dwell’s GLRT Δf · integrated continuously')):
        ax.scatter(t,[r[name+'_phase_deg'] for r in rows],s=11,c=[r[name+'_coherence'] for r in rows],cmap='viridis',vmin=0,vmax=.1)
        ax.set(ylabel='RX1 − RX0 (degrees)',ylim=(-185,185),yticks=[-180,-90,0,90,180],title=title)
    for name,label in [('fixed','Fixed'),('dwell','Per dwell')]:
        axes[2].plot(t,[r[name+'_coherence'] for r in rows],'.',ms=3,label=label,alpha=.7)
    axes[2].set(ylabel='Cross-coherence',ylim=(0,None));axes[2].legend(loc='upper right')
    axes[3].stairs(frequencies-frequencies[0],np.r_[starts,starts[-1]+.12],baseline=None,color='#a46432')
    axes[3].set(ylabel='Δf − first Δf (Hz)',xlabel='Seconds from first selected dwell')
    for k,start in enumerate(starts):
        for ax in axes:
            ax.axvline(start,color='gray',alpha=.3,lw=.7)
            ax.axvspan(start,start+.02,color='#74a9cf',alpha=.08)
        axes[0].text(start+.06,169,str(indices[k]),ha='center',fontsize=8)
    fig.suptitle('Same strong GLRT segment · CH1 upper · visits 259–263',fontsize=15)
    fig.supxlabel('Same IQ windows and candidates. No fitted phase offset/rate or gap unwrapping. Point color: cross-coherence, 0–0.10.',fontsize=9)
    for ext in ('png','svg'):fig.savefig(HERE/f'dwell-cfo-comparison.{ext}',dpi=170)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
