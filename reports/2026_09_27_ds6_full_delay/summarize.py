"""Summarize matched response models and conservative quadrature bounds."""
import json
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

HERE=Path(__file__).resolve().parent


def log_error_bound(df,step):
    # For L=exp(sum cos(theta-w*d)), |L''| <= (A^2+B)*L.
    # Composite trapezoid Peano kernel <= h^2/8, hence relative error
    # <= h^2/8*(A^2+B), preserved by positive hypothesis mixtures.
    w=2*np.pi*np.array(df);relative=step**2/8*(sum(abs(w))**2+sum(w*w))
    return dict(relative_integral_bound=float(relative),log_integral_bound=float(-np.log1p(-relative)) if relative<1 else None)


def main():
    result=json.loads((HERE/'results-101.json').read_text());assert result['complete'];rows=[]
    fig,axes=plt.subplots(1,2,figsize=(11,4.5))
    for si,scan in enumerate(result['scans']):
        plan=json.loads((HERE.parent/'2026_09_27_ds6_common_rate_validation'/(scan['session_id']+'-plan.json')).read_text())
        df=[];train=[]
        for g in scan['groups']:
            for visit,f in zip(g['visits'],g['df_hz']):
                v=next(v for v in plan['selected'] if v['visit']==visit and v['group']==g['group']);df.append(f)
                if v['partition']=='train':train.append(f)
        b=log_error_bound(df,2e-7);bt=log_error_bound(train,2e-7)
        s=scan['scores'];row=dict(session_id=scan['session_id'],scores=s,
            shared_delay_minus_pair_offsets_phase=s['delay_geometry']['held_phase']-s['offset_geometry']['held_phase'],
            shared_delay_minus_pair_offsets_cfo=s['delay_geometry']['held_cfo']-s['offset_geometry']['held_cfo'],
            delay_geometry_minus_null=s['delay_geometry']['held_phase']-s['delay_null']['held_phase'],
            quadrature_all=b,quadrature_train=bt,
            held_phase_log_error_bound=b['log_integral_bound']+bt['log_integral_bound'],
            held_cfo_log_error_bound=2*bt['log_integral_bound'])
        rows.append(row);names=['offset_null','offset_geometry','delay_null','delay_geometry'];labels=['Pair offsets\nno geometry','Pair offsets\ngeometry','Shared delay\nno geometry','Shared delay\ngeometry']
        axes[si].bar(labels,[s[n]['held_phase'] for n in names],color=['gray','steelblue','gray','darkorange'],yerr=[0,0,row['held_phase_log_error_bound'],row['held_phase_log_error_bound']],capsize=4);axes[si].set_title(scan['session_id'][-8:]);axes[si].set_ylabel('Held phase log score relative to uniform');axes[si].tick_params(axis='x',labelsize=8)
    fig.suptitle('DS6: full-catalogue receiver response test, fixed κ = 1\nBars show conservative numerical error bounds, not statistical uncertainty');fig.tight_layout();fig.savefig(HERE/'response-comparison.png',dpi=180)
    output=dict(scans=rows,elapsed_s=result['elapsed_s']);(HERE/'summary.json').write_text(json.dumps(output,indent=2)+'\n');print(json.dumps(output,indent=2))


if __name__=='__main__':main()
