"""Fixed kappa-16 model on other cached development dwells; no per-case tuning."""
import hashlib
import json
from pathlib import Path
import numpy as np
from run import fit,base,log_density

HERE=Path(__file__).resolve().parent;ROOT=HERE.parent


def main():
    src=ROOT/'2026_09_27_ds6_dwell_phase';old=json.loads((src/'results.json').read_text());paths={r['session_id']:src/(r['session_id']+'-frames.json') for r in old['results']}
    protocol=dict(kappa=16.,outlier_fraction=.1,source_hashes={sid:hashlib.sha256(p.read_bytes()).hexdigest() for sid,p in paths.items()},
        selection='All original qualified windows; retain unavailable scans',
        scope='Fixed-arm transfer to ten other cached DS6 dwells, previously used by other diagnostics; not untouched validation')
    pp=HERE/'transfer-protocol.json';pp.write_text(json.dumps(protocol,indent=2)+'\n');rows=[]
    for sid,path in paths.items():
        windows=[]
        for i,w in enumerate(json.loads(path.read_text())):
            if not w['result']['both_qualified']:continue
            arms={}
            for name in ['equal_weight','mixture_k16']:
                model=base.fit(*base.extract(w,'fit'),0) if name=='equal_weight' else fit(*base.extract(w,'fit'),16)
                ev=base.evaluate(model,*base.extract(w,'evaluation'));arms[name]=dict(model=model,**ev,common_k4_held_log_score=float(log_density(np.array(ev['errors_rad']),4).sum()))
            windows.append(dict(window=i,arms=arms))
        summary={}
        for name in ['equal_weight','mixture_k16']:
            if not windows:continue
            e=np.concatenate([w['arms'][name]['errors_rad'] for w in windows]);z=np.mean([np.exp(1j*w['arms'][name]['phase_dd_rad']) for w in windows])
            summary[name]=dict(held_pilot_rms_deg=float(np.degrees(np.sqrt(np.mean(e**2)))),mean_dwell_dd_rad=float(np.angle(z)),within_dwell_R=float(abs(z)),common_k4_held_log_score=float(sum(w['arms'][name]['common_k4_held_log_score'] for w in windows)))
        rows.append(dict(session_id=sid,windows=windows,summary=summary,unavailable_reason=None if windows else 'No originally qualified windows'))
    (HERE/'transfer-results.json').write_text(json.dumps(dict(complete=True,protocol_sha256=hashlib.sha256(pp.read_bytes()).hexdigest(),scans=rows),indent=2)+'\n')
    print(json.dumps([dict(session_id=r['session_id'],windows=len(r['windows']),summary=r['summary']) for r in rows],indent=2))


if __name__=='__main__':main()
