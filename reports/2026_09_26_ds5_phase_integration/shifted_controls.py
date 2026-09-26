"""One selected single-mode and one two-mode dwell per scan: RX1 time mismatch."""
from pathlib import Path
import json,hashlib
import numpy as np
import zstandard
import pilot_extract as E
from run import split,summarize,RATE

HERE=Path(__file__).resolve().parent

def main(selection_policy='single-and-pair'):
    plan=json.loads((HERE/'plan.json').read_text());train,held,_=split();rows=[];selection=[]
    # Select first eligible visit by metadata order, not by measured phase.
    for scan in plan['scans']:
        if selection_policy=='long-overlap':
            visits=scan['selected']
            chosen=[visits[0],visits[len(visits)//2]] if visits else []
        else:
            chosen=[next(v for v in scan['selected'] if len(v['modes'])==n) for n in (1,2)]
        selection.append(dict(session_id=scan['session_id'],visits=[v['visit'] for v in chosen]))
    (HERE/'shifted-control-plan.json').write_text(json.dumps(dict(selection=selection,shift_samples=30000,meaning='RX1 circularly shifted by 3 ms; exact-branch timing frozen, no control parameter search'),indent=2)+'\n')
    for scan,selection_row in zip(plan['scans'],selection):
        sid=scan['session_id'];root=Path(scan['metadata']['recording_manifest_path']).parent
        raw=json.loads((root/'manifest.json').read_text())['manifest']
        exact=json.loads((HERE/(sid+'.json')).read_text())['rows']
        for v in selection_row['visits']:
            visit=next(r for r in scan['selected'] if r['visit']==v);chunk=raw['chunks'][v]
            buf=zstandard.ZstdDecompressor().decompress((root/chunk['relative_path']).read_bytes(),max_output_size=chunk['uncompressed_bytes'])
            assert 'sha256:'+hashlib.sha256(buf).hexdigest()==chunk['uncompressed_sha256']
            a=np.frombuffer(buf,dtype='<i2').reshape(-1,2,2);iq=a[...,0].astype(float)+1j*a[...,1].astype(float)
            iq[:,1]=np.roll(iq[:,1],30000)
            for old in [r for r in exact if r['visit']==v]:
                mode=old['mode'];pair=[dict(r) for r in visit['modes'][mode]['seeds']]
                ep=[r['integer_epoch_sample']+r['fractional_epoch_offset_samples'] for r in pair]
                pair[1]['fractional_epoch_offset_samples']+=round((ep[0]-ep[1])/(RATE/750))*(RATE/750)
                epoch=np.mean([r['integer_epoch_sample']+r['fractional_epoch_offset_samples'] for r in pair]);frac=epoch-round(epoch)
                for r in pair:r['fractional_epoch_offset_samples']+=old['timing_offset_samples']-frac
                start=round(old['start_ms']*RATE/1000)
                result=E.extract_candidate(iq,visit['edge'],pair,start,start+70000,[0.],train,held)
                value=summarize(result,result['alternatives'][0],len(train))
                rows.append(dict(session_id=sid,visit=v,start_ms=old['start_ms'],mode=mode,exact_R=old['coefficients']['held']['R'],shifted_R=value['coefficients']['held']['R'],exact_disagreement_rad=float(E.wrap(old['coefficients']['held']['phase_rad']-old['coefficients']['train']['phase_rad'])),shifted_disagreement_rad=float(E.wrap(value['coefficients']['held']['phase_rad']-value['coefficients']['train']['phase_rad']))))
            print(sid,'shifted control',v,flush=True)
    out=[]
    for scan in plan['scans']:
        rs=[r for r in rows if r['session_id']==scan['session_id']]
        if not rs:continue
        out.append(dict(session_id=scan['session_id'],windows=len(rs),median_exact_held_R=float(np.median([r['exact_R'] for r in rs])),median_shifted_held_R=float(np.median([r['shifted_R'] for r in rs])),exact_rms_deg=float(np.degrees(np.sqrt(np.mean([r['exact_disagreement_rad']**2 for r in rs])))),shifted_rms_deg=float(np.degrees(np.sqrt(np.mean([r['shifted_disagreement_rad']**2 for r in rs]))))))
    (HERE/'shifted-controls.json').write_text(json.dumps(dict(rows=rows,summary=out),indent=2)+'\n')
    print(json.dumps(out,indent=2))

if __name__=='__main__':main()
