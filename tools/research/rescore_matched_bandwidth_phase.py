"""Rescore preserved matched-bandwidth rows without opening IQ."""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from tools.research.matched_bandwidth_phase import circular_affine, wrapped_phase_error

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "reports/figures/2026_09_23_matched_bandwidth_phase"
OUT = BASE / "v3-2pi-rescore"


def score(rows: list[dict], label: str) -> dict:
    summaries=[]
    fig, axes=plt.subplots(2,1,figsize=(9,6),sharex=True,layout='constrained')
    cases=sorted({(r['session_id'],r['visit']) for r in rows})
    for ax,(session,visit) in zip(axes,cases,strict=True):
        case=[r for r in rows if (r['session_id'],r['visit'])==(session,visit)]
        summary={'session_id':session,'visit':visit,'groups':{'train':[r['group_id'] for r in case if r['partition']=='train'],'held':[r['group_id'] for r in case if r['partition']=='held']},'arms':{}}
        for arm,color in (('full','tab:blue'),('narrow_2p5','tab:orange')):
            t=np.array([r['time_s'] for r in case]); p=np.array([r['arms'][arm]['pilot_phase_rad'] for r in case]); train=np.array([r['partition']=='train' for r in case]); held=~train
            intercept,hz=circular_affine(t,p,train); err=wrapped_phase_error(p,intercept+2*np.pi*hz*t)
            summary['arms'][arm]={'held_phase_rms_rad':float(np.sqrt(np.mean(err[held]**2))),'held_phase_rms_deg':float(np.sqrt(np.mean(err[held]**2))*180/np.pi),'held_phase_resultant':float(abs(np.mean(np.exp(1j*err[held])))),'train_phase_resultant':float(abs(np.mean(np.exp(1j*err[train])))),'training_only_principal_slope_hz':hz}
            ax.plot(t[train]*1e3,err[train]*180/np.pi,'o',color=color,label=f'{arm} train')
            ax.plot(t[held]*1e3,err[held]*180/np.pi,'x',color=color,label=f'{arm} held')
        ax.set_title(f'{label}: {session} visit {visit} residual')
        ax.set_ylabel('2π phase residual [deg]');ax.legend(ncol=2,fontsize=8); summaries.append(summary)
    axes[-1].set_xlabel('physical group center [ms]'); fig.savefig(OUT/f'{label}-residuals.png',dpi=160)
    return {'input':label,'summaries':summaries}


def main():
    OUT.mkdir(parents=True,exist_ok=False)
    docs=[]
    for label,path in (('v1',BASE/'results.json'),('v2',BASE/'v2/results.json')):
        doc=json.loads(path.read_text());docs.append(score(doc['rows'],label))
    (OUT/'results.json').write_text(json.dumps({'score_contract':'ordinary 2pi complex-vector phase; no IQ reread','inputs':docs},indent=2)+'\n')


if __name__=='__main__': main()
