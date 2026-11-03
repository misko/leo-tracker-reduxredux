"""Display exactly the archived Huber-line residuals, without reselecting pairs."""
import csv
import hashlib
import json
from pathlib import Path
import numpy as np

HERE=Path(__file__).resolve().parent


def prediction(model,times,channels):
    x=np.asarray(times)-150.
    offset=np.array([model['channel_intercepts_hz_at_150s'][str(int(c))] for c in channels])
    return offset+model['slope_hz_s_at_150s']*x+model['quadratic_coefficient_hz_s2']*x*x


def main():
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    paths=sorted((HERE/'cases').glob('DS9-*.json'))
    assert len(paths)==16
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),*paths]}
    fig,axes=plt.subplots(4,4,figsize=(18,13),sharey=True)
    points=[];summary=[];limit=0.
    for ax,path in zip(axes.ravel(),paths,strict=True):
        case=json.loads(path.read_text());pairs=case['pairs']
        t=np.array([p['time_s'] for p in pairs]);ch=np.array([p['channel'] for p in pairs])
        y=np.array([p['rx1_minus_rx0_modulo_alias_hz'] for p in pairs])
        models=case['summary']['channel_offset_controlled_models']
        line=prediction(models['1'],t,ch);residual=y-line
        quadratic_remainder=prediction(models['2'],t,ch)-line
        rms=float(np.sqrt(np.mean(residual**2)))
        assert np.isclose(rms,models['1']['all_selected_rms_hz'],atol=1e-7,rtol=0)
        limit=max(limit,float(np.max(abs(residual))),float(np.max(abs(quadratic_remainder))))
        ax.axhline(0,color='black',lw=.8,label='Removed relative line')
        ax.scatter(t,residual,s=10,alpha=.8,label='Paired observations − fitted line')
        order=np.argsort(t);ax.plot(t[order],quadratic_remainder[order],color='#e67e22',lw=1.5,
                                    label='Quadratic fit − fitted line')
        ax.set_title(f"{case['case_id']} · candidate {case['catalog_number']}\n{len(pairs)} pairs · residual RMS {rms:.1f} Hz",fontsize=10)
        ax.grid(alpha=.2);ax.set_xlabel('Receive time (s)',fontsize=8)
        if ax in axes[:,0]:ax.set_ylabel('RX1−RX0 after line removal (Hz)',fontsize=9)
        for p,r,baseline in zip(pairs,residual,line,strict=True):
            points.append(dict(case_id=case['case_id'],session_id=case['session_id'],**p,
                               removed_line_hz=float(baseline),detrended_difference_hz=float(r)))
        summary.append(dict(case_id=case['case_id'],session_id=case['session_id'],candidate=case['catalog_number'],
            pair_count=len(pairs),removed_slope_hz_s=models['1']['slope_hz_s_at_150s'],rms_hz=rms,
            median_absolute_error_hz=float(np.median(abs(residual))),mean_hz=float(np.mean(residual)),
            held_linear_median_absolute_error_hz=models['1']['five_time_block_held_median_absolute_error_hz'],
            held_quadratic_median_absolute_error_hz=models['2']['five_time_block_held_median_absolute_error_hz']))
    limit=25*np.ceil((limit+10)/25)
    axes[0,0].set_ylim(-limit,limit)
    handles,labels=axes[0,0].get_legend_handles_labels()
    fig.legend(handles,labels,loc='upper center',bbox_to_anchor=(.5,.947),ncol=3,fontsize=10)
    fig.suptitle('DS9 · the same 16 dual-receiver tracks after relative linear drift removal',fontsize=16)
    fig.text(.5,.014,'Same pairs, no rejection. Archived 100-Hz Huber offset + line removed independently per track; common vertical scale.\nOrange is a diagnostic overlay, not an applied correction. This is an in-sample view, not a shared full-scan receiver calibration.',ha='center',fontsize=10)
    fig.tight_layout(rect=(0,.055,1,.905))
    output=HERE/'linear-detrended';output.mkdir(exist_ok=False)
    fig.savefig(output/'sixteen-tracks.png',dpi=160)
    for name,rows in [('points.csv',points),('summary.csv',summary)]:
        with (output/name).open('w',newline='') as stream:
            writer=csv.DictWriter(stream,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    for path,sha in hashes.items():assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha
    (output/'receipt.json').write_text(json.dumps(dict(source_sha256=hashes,cases=summary,
        scope='Exact archived per-track Huber line (offset plus slope), evaluated in native Hz and subtracted from '
        'the same modulo-alias RX1-RX0 observations. No new fitting, selection or rejection. '
        'Quadratic-minus-line overlay only. Not a joint per-scan RX calibration; mean need not be exactly zero under Huber loss.'),indent=2))
    print(json.dumps(summary,indent=2))


if __name__=='__main__':main()
