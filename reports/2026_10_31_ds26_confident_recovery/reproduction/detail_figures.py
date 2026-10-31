"""Plot sealed selected tracks; example selection is descriptive, never inferential."""
import csv
import gzip
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from summarize import OUT

def make_figures():
    rows=list(csv.DictReader((OUT/'per-case.csv').open()))
    changed=[r for r in rows if r['method']=='combined_policy' and r['arm']=='fitted_c'
             and r['state']=='complete' and int(r['added_points'])>0]
    # Plot the largest change in each direction, then the next largest absolute
    # changes. Geographic truth is used only to choose illustrative figures.
    ordered=sorted(changed,key=lambda r:float(r['error_m'])-float(r['baseline_error_m']))
    examples=[]
    for r in ([ordered[0],ordered[-1]] if ordered else [])+sorted(changed,key=lambda r:-abs(float(r['error_m'])-float(r['baseline_error_m']))):
        if r['case'] not in {e['case'] for e in examples}:examples.append(r)
        if len(examples)>=4:break
    packets=json.loads(gzip.decompress((OUT/'evidence/trial-diagnostics.json.gz').read_bytes()))
    written=[]
    for row in examples:
        packet=next(p for p in packets if p['trial_path']==row['trial_path'] and p['qualification']['qualified'])
        fig,axs=plt.subplots(2,2,figsize=(13,7),layout='constrained')
        for j,arm in enumerate(('c0','fitted_c')):
            a=packet['arms'][arm];d=a['target_diagnostics'][0]
            t=np.asarray(d['times_s']);y=np.asarray(d['CFO_hz']);res=np.asarray(d['residual_hz'])
            # Residual is after profiled source bias; plot the identical adjusted
            # prediction, rather than confusing bias with an orbital discrepancy.
            axs[0,j].scatter(t,y,s=14,color='#0072b2',label='Recovered native GLRT CFO')
            axs[0,j].plot(t,y-res,color='#d55e00',lw=1.5,label='Fitted orbit + receiver/source terms')
            axs[0,j].set(ylabel='Alias-unwrapped CFO (Hz)',title=arm)
            axs[0,j].legend(fontsize=8)
            axs[1,j].plot(t,res,'.-',ms=4,lw=.7,color='#0072b2');axs[1,j].axhline(0,color='black',lw=.7)
            axs[1,j].set(xlabel='Time in scan (s)',ylabel='Profiled residual (Hz)')
            rr=next(r for r in rows if r['case']==row['case'] and r['method']=='combined_policy' and r['arm']==arm)
            axs[1,j].set_title(f"RMS {d['RMS_hz']:.1f} Hz; error {float(rr['baseline_error_m']):.0f} → {float(rr['error_m']):.0f} m\n"
                f"Matched no-addition control: {float(rr['control_error_m']):.0f} m",fontsize=10)
            for ax in axs[:,j]:ax.grid(alpha=.2)
        fig.suptitle(f"{row['case']} · {d['component']} · hypothesis NORAD {d['norad']}\n"
            f"{row['selected_mode']}; +{row['added_points']} unique GLRT points; both arms qualified",fontsize=11)
        name=f"figures/{row['case']}-selected-track.png";fig.savefig(OUT/name,dpi=160);plt.close(fig)
        written.append(dict(case=row['case'],path=name,mode=row['selected_mode'],track_id=row['track_id'],
            selection='Largest error changes for illustration after inference seal'))
    (OUT/'illustrated-cases.json').write_text(json.dumps(written,indent=2)+'\n')

if __name__=='__main__':make_figures()
