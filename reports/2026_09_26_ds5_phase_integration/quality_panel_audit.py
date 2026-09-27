"""Bounded real-hypothesis diagnostic, not a full candidate-bank replay."""
from pathlib import Path
import json,time
import numpy as np
from quality_panel_reference import panel_evidence
from quality_offset_quadrature import offset_evidence

HERE=Path(__file__).resolve().parent
OUT=HERE/'quality-panel'
SCALES=3.125*2.**np.arange(10)


def main():
    OUT.mkdir(exist_ok=True);rows=[];started=time.monotonic()
    for sid in ['scan-fw-4fc9ccc9f49e637b','scan-fw-382ca32cddbfdc6a']:
        bank=np.load(HERE/'causal-quality'/f'{sid}-bank.npz')
        old=json.loads((HERE/'quality-quadrature'/f'{sid}-n64.json').read_text())
        candidate=int(np.argmax(old['models'][0]['rows'][-1]['identity_probabilities']))
        peak=int(np.argmax(bank['logprior'][candidate]))
        for ti in [peak, max(0,peak-600), min(len(bank['taus'])-1,peak+600)]:
            residual=bank['residuals'][candidate,ti]
            for kind in ['generic','timing_informed']:
                runs=[]
                for order in [4,8,16]:
                    z,nodes=panel_evidence(residual,SCALES,bank['times'],bank['pilot_flags'],kind,order=order)
                    runs.append(dict(order=order,nodes=nodes,held_score=float(z[-1]-z[7]),prefix=z.tolist()))
                oldruns=[]
                for n in [32,64,128]:
                    z=offset_evidence(residual,SCALES,bank['times'],bank['pilot_flags'],kind,nodes=n)
                    oldruns.append(dict(nodes=n,held_score=float(z[-1]-z[7])))
                error=np.array(runs[-1]['prefix'])-runs[-2]['prefix']
                expanded,_=panel_evidence(residual,SCALES,bank['times'],bank['pilot_flags'],kind,order=16,tail=24)
                tail_error=expanded-np.array(runs[-1]['prefix'])
                row=dict(session_id=sid,candidate_index=candidate,candidate_id=str(bank['candidate_ids'][candidate]),tau_s=float(bank['taus'][ti]),model=kind,panels=runs,hermite=oldruns,max_prefix_change=float(abs(error[7:]).max()),max_block_change=float(abs(np.diff(error)[7:]).max()),max_tail_expansion_change=float(abs(tail_error[7:]).max()))
                rows.append(row);print(sid,ti,kind,'panel',runs[-1]['held_score'],'change',row['max_prefix_change'],flush=True)
    result=dict(protocol='Diagnostic selection: n64 generic final top candidate; peak-prior time and +/-30 seconds. This retrospective subset investigates integration accuracy only, not association performance. All prefix model likelihoods and priors are unchanged.',elapsed_s=time.monotonic()-started,rows=rows)
    (OUT/'audit.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':main()
