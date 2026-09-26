"""Replay all frozen longer-overlap windows with joint pilot components."""
from pathlib import Path
import argparse,hashlib,json,time
import numpy as np
import zstandard
import pilot_extract as E
from joint_mode_audit import design
from joint_phase import extract
from run import RATE

HERE=Path(__file__).resolve().parent
OUT=HERE/'joint-phase'

def geometry(pair,edge,start,stop):
    epoch=np.mean([r['integer_epoch_sample']+r['fractional_epoch_offset_samples'] for r in pair]);midpoint=(start+stop)/2;nearest=round((midpoint-epoch)*750/RATE);frames=np.array([epoch+(nearest+k)*RATE/750 for k in range(-2,3)]);starts=np.rint(frames).astype(int);width=len(E.qin_edge_pilot_frame(RATE,edge));valid=(starts>=start)&(starts+width<=stop)
    return dict(frame_starts=starts[valid],frame_fractional_offsets_samples=frames[valid]-starts[valid],midpoint_sample=midpoint)

def build(visit,old,start_ms):
    start=start_ms*10000;stop=start+70000;designs=[[],[]];controls=[[],[]]
    for mode in (0,1):
        prior=next(r for r in old if r['visit']==visit['visit'] and r['start_ms']==start_ms and r['mode']==mode);pair=[dict(r) for r in visit['modes'][mode]['seeds']]
        ep=[r['integer_epoch_sample']+r['fractional_epoch_offset_samples'] for r in pair];pair[1]['fractional_epoch_offset_samples']+=round((ep[0]-ep[1])/(RATE/750))*(RATE/750)
        epoch=np.mean([r['integer_epoch_sample']+r['fractional_epoch_offset_samples'] for r in pair]);fraction=epoch-round(epoch)
        for r in pair:r['fractional_epoch_offset_samples']+=prior['timing_offset_samples']-fraction
        result=geometry(pair,visit['edge'],start,stop)
        for rx in (0,1):
            designs[rx].append(design(result,visit['edge'],pair[rx]['tracking_absolute_baseband_cfo_hz'],start,stop))
            controls[rx].append(design(result,visit['edge'],pair[rx]['tracking_absolute_baseband_cfo_hz'],start,stop,True))
    return designs,controls

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',type=int,choices=[0,1],required=True);args=parser.parse_args();OUT.mkdir(exist_ok=True)
    plan=json.loads((HERE/'long-overlap/plan.json').read_text());scan=[s for s in plan['scans'] if s['selected']][args.scan];sid=scan['session_id'];old=json.loads((HERE/'long-overlap'/(sid+'.json')).read_text())['rows']
    protocol=dict(session_id=sid,plan_sha256=hashlib.sha256((HERE/'long-overlap/plan.json').read_bytes()).hexdigest(),seed=20261003,blocks_samples=200,split='175 fit / 87 qualification / 88 phase-evaluation blocks per 7ms',qualification='Both RX: target gain beyond donor >1e-8 fraction and z>3, gain beyond rolled-target control z>3, on qualification blocks only. Block z is heuristic, not a calibrated false-alarm probability.',phase='Joint components; differential frame rate fitted on fit blocks, frozen for evaluation; retain midpoint intercept',selection='All existing windows retained; qualification is separate metadata',conditioning='Acquisition and prior timing selection used overlapping support; the three new masks are disjoint but not independent of original acquisition')
    (OUT/(sid+'-protocol.json')).write_text(json.dumps(protocol,indent=2)+'\n');root=Path(scan['metadata']['recording_manifest_path']).parent;manifest=(root/'manifest.json').read_bytes();assert 'sha256:'+hashlib.sha256(manifest).hexdigest()==scan['metadata']['recording_manifest_file_sha256'];raw=json.loads(manifest)['manifest'];rows=[];synthetic=[];started=time.monotonic()
    for visit in scan['selected']:
        chunk=raw['chunks'][visit['visit']];buf=zstandard.ZstdDecompressor().decompress((root/chunk['relative_path']).read_bytes(),max_output_size=chunk['uncompressed_bytes']);assert 'sha256:'+hashlib.sha256(buf).hexdigest()==chunk['uncompressed_sha256'];a=np.frombuffer(buf,dtype='<i2').reshape(-1,2,2);iq=a[...,0].astype(float)+1j*a[...,1].astype(float)
        for start_ms in plan['starts_ms']:
            designs,controls=build(visit,old,start_ms);start=start_ms*10000;result=extract(designs,controls,iq[start:start+70000]);result.update(visit=visit['visit'],start_ms=start_ms,utc_ns=next(r['utc_ns'] for r in old if r['visit']==visit['visit'] and r['start_ms']==start_ms));rows.append(result)
            if visit==scan['selected'][0] and start_ms==0:
                for source in (0,1,'both'):
                    for residual in (0,125):
                        t=(np.arange(70000)-35000)/RATE
                        signal=np.column_stack([sum(designs[rx][m].sum(axis=1)*np.exp(1j*rx*((.7 if m==0 else -.5)+2*np.pi*residual*t)) for m in (0,1) if source=='both' or source==m) for rx in (0,1)])
                        synthetic.append(dict(source=source,residual_hz=residual,result=extract(designs,controls,signal)))
        print(sid,visit['visit'],'joint windows',len(rows),'qualified pairs',sum(r['both_qualified'] for r in rows),flush=True)
    (OUT/(sid+'.json')).write_text(json.dumps(dict(protocol=protocol,rows=rows,synthetic=synthetic,elapsed_s=time.monotonic()-started),indent=2)+'\n')

if __name__=='__main__':main()
