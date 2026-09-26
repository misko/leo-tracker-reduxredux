"""Bounded joint-pilot regression: second-mode evidence beyond donor leakage."""
from pathlib import Path
import hashlib,json
import numpy as np
import zstandard
import pilot_extract as E
from run import RATE,split

HERE=Path(__file__).resolve().parent
OUT=HERE/'spectral-audit'

def regression(design,values,train):
    coefficient=np.linalg.lstsq(design[train],values[train],rcond=None)[0]
    error=values[~train]-design[~train]@coefficient
    return coefficient,float(np.vdot(error,error).real)

def design(result,edge,cfo,start,stop,control=False):
    base=E.qin_edge_pilot_frame(RATE,edge,**({'symbol_roll':E.CONTROL_SYMBOL_ROLL} if control else {}));columns=[]
    mixer=np.exp(2j*np.pi*cfo*(np.arange(start,stop)-result['midpoint_sample'])/RATE)
    for s,fraction in zip(result['frame_starts'],result['frame_fractional_offsets_samples']):
        col=np.zeros(stop-start,complex);col[s-start:s-start+len(base)]=E.fractional_shift(base,fraction);columns.append(col*mixer)
    return np.stack(columns,axis=1)

def assess(designs,controls,iq,train):
    output=[]
    for rx in (0,1):
        a,b=designs[rx];joint=np.column_stack([a,b]);coefficient,full=regression(joint,iq[:,rx],train);energy=float(np.sum(abs(iq[~train,rx])**2))
        for mode in (0,1):
            donor=designs[rx][1-mode];_,single=regression(donor,iq[:,rx],train);_,control=regression(np.column_stack([donor,controls[rx][mode]]),iq[:,rx],train)
            block=coefficient[:a.shape[1]] if mode==0 else coefficient[a.shape[1]:]
            output.append(dict(receiver=rx,mode=mode,incremental_held_fraction=(single-full)/energy,control_incremental_held_fraction=(single-control)/energy,joint_coefficient_power=float(np.mean(abs(block)**2))))
    return output

def main():
    plan=json.loads((HERE/'long-overlap/plan.json').read_text());pilot_train,pilot_held,_=split();rng=np.random.default_rng(20261002);rows=[];synthetic=[];selection=[]
    # Shared 200-sample blocks split once, used by every model and receiver.
    blocks=np.arange(350);chosen=rng.choice(blocks,175,replace=False);train=np.isin(np.arange(70000)//200,chosen)
    for scan in plan['scans']:
        if not scan['selected']:continue
        sid=scan['session_id'];visits=[scan['selected'][0],scan['selected'][len(scan['selected'])//2]];selection.append(dict(session_id=sid,visits=[v['visit'] for v in visits],starts_ms=[0,63]))
    (OUT/'joint-mode-protocol.json').write_text(json.dumps(dict(selection=selection,seed=20261002,training_sample_blocks=chosen.tolist(),block_samples=200,meaning='Conditional pilot regression with prior frozen timing/CFO; new sample split is not independent of earlier acquisition. One complex gain per mode per frame; raw additive model and rolled-target control.'),indent=2)+'\n')
    for scan in plan['scans']:
        if not scan['selected']:continue
        sid=scan['session_id'];chosen_visits=next(s['visits'] for s in selection if s['session_id']==sid);root=Path(scan['metadata']['recording_manifest_path']).parent
        manifest=(root/'manifest.json').read_bytes();assert 'sha256:'+hashlib.sha256(manifest).hexdigest()==scan['metadata']['recording_manifest_file_sha256'];raw=json.loads(manifest)['manifest']
        old=json.loads((HERE/'long-overlap'/(sid+'.json')).read_text())['rows']
        for v in [v for v in scan['selected'] if v['visit'] in chosen_visits]:
            chunk=raw['chunks'][v['visit']];buf=zstandard.ZstdDecompressor().decompress((root/chunk['relative_path']).read_bytes(),max_output_size=chunk['uncompressed_bytes']);assert 'sha256:'+hashlib.sha256(buf).hexdigest()==chunk['uncompressed_sha256']
            data=np.frombuffer(buf,dtype='<i2').reshape(-1,2,2);iq=data[...,0].astype(float)+1j*data[...,1].astype(float)
            for start_ms in (0,63):
                start=start_ms*10000;stop=start+70000;designs=[[],[]];controls=[[],[]]
                for mode in (0,1):
                    prior=next(r for r in old if r['visit']==v['visit'] and r['start_ms']==start_ms and r['mode']==mode);pair=[dict(r) for r in v['modes'][mode]['seeds']]
                    ep=[r['integer_epoch_sample']+r['fractional_epoch_offset_samples'] for r in pair];pair[1]['fractional_epoch_offset_samples']+=round((ep[0]-ep[1])/(RATE/750))*(RATE/750)
                    epoch=np.mean([r['integer_epoch_sample']+r['fractional_epoch_offset_samples'] for r in pair]);fraction=epoch-round(epoch)
                    for r in pair:r['fractional_epoch_offset_samples']+=prior['timing_offset_samples']-fraction
                    result=E.extract_candidate(iq,v['edge'],pair,start,stop,[0.],pilot_train,pilot_held)
                    for rx in (0,1):
                        designs[rx].append(design(result,v['edge'],pair[rx]['tracking_absolute_baseband_cfo_hz'],start,stop))
                        controls[rx].append(design(result,v['edge'],pair[rx]['tracking_absolute_baseband_cfo_hz'],start,stop,True))
                metrics=assess(designs,controls,iq[start:stop],train);rows.append(dict(session_id=sid,visit=v['visit'],start_ms=start_ms,metrics=metrics))
                if v['visit']==chosen_visits[0] and start_ms==0:
                    for source in (0,1,'both'):
                        signal=np.column_stack([sum(designs[rx][m].sum(axis=1)*np.exp(1j*rx*(.7 if m==0 else -.5)) for m in (0,1) if source=='both' or m==source) for rx in (0,1)])
                        synthetic.append(dict(session_id=sid,source=source,metrics=assess(designs,controls,signal,train)))
                print(sid,v['visit'],start_ms,'joint mode checked',flush=True)
    (OUT/'joint-mode-results.json').write_text(json.dumps(dict(real=rows,synthetic=synthetic),indent=2)+'\n')

if __name__=='__main__':main()
