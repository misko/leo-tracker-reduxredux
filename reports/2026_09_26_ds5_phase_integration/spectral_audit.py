"""Measure tone-dependent phase with the frozen DS5 extraction seeds."""
from pathlib import Path
import argparse,hashlib,json,time
import numpy as np
import zstandard
import pilot_extract as E
from run import split,RATE

HERE=Path(__file__).resolve().parent
OUT=HERE/'spectral-audit'

def fit_delay(z,frequencies):
    f=np.asarray(frequencies)-np.mean(frequencies)
    grid=np.linspace(-1e-6,1e-6,1001)
    response=np.exp(-2j*np.pi*grid[:,None]*f)@np.asarray(z)
    index=int(np.argmax(abs(response)))
    return float(grid[index]),bool(index in (0,len(grid)-1))

def tone_summary(tones,symbols,result,differential_hz):
    z=tones[1]*np.conj(tones[0])
    center=(np.rint(np.asarray(symbols)*RATE*E.OFDM_SYMBOL_DURATION_S)+np.rint((np.asarray(symbols)+1)*RATE*E.OFDM_SYMBOL_DURATION_S))/2
    time=result['frame_starts'][:,None]+center[None,:]-result['midpoint_sample']
    z*=np.exp(-2j*np.pi*differential_hz*time/RATE)[...,None]
    mean=z.mean(axis=(0,1));R=abs(mean)/np.maximum(np.mean(abs(z),axis=(0,1)),1e-30)
    return mean,R

def atom(result,edge,cfo,start,stop):
    out=np.zeros(stop-start,complex);base=E.qin_edge_pilot_frame(RATE,edge)
    for s,fraction in zip(result['frame_starts'],result['frame_fractional_offsets_samples']):
        out[s-start:s-start+len(base)]+=E.fractional_shift(base,fraction)
    return out*np.exp(2j*np.pi*cfo*(np.arange(start,stop)-result['midpoint_sample'])/RATE)

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--scan',type=int,choices=[0,1],required=True);args=parser.parse_args()
    OUT.mkdir(exist_ok=True);plan=json.loads((HERE/'long-overlap/plan.json').read_text());scan=[s for s in plan['scans'] if s['selected']][args.scan];sid=scan['session_id']
    exact=json.loads((HERE/'long-overlap'/(sid+'.json')).read_text());lookup={(r['visit'],r['start_ms'],r['mode']):r for r in exact['rows']}
    protocol=dict(session_id=sid,plan_sha256=hashlib.sha256((HERE/'long-overlap/plan.json').read_bytes()).hexdigest(),exact_sha256=hashlib.sha256((HERE/'long-overlap'/(sid+'.json')).read_bytes()).hexdigest(),selection='All existing longer-overlap windows; freeze prior training-selected timing and differential rate',delay_fit='Training tone means only; +/-1 microsecond in 2ns steps; phase pivot at mean pilot frequency; no across-time trend subtraction',meaning='Tone response diagnostic, not independent proof of satellite identity')
    (OUT/(sid+'-protocol.json')).write_text(json.dumps(protocol,indent=2)+'\n')
    root=Path(scan['metadata']['recording_manifest_path']).parent;manifest=(root/'manifest.json').read_bytes()
    assert 'sha256:'+hashlib.sha256(manifest).hexdigest()==scan['metadata']['recording_manifest_file_sha256']
    raw=json.loads(manifest)['manifest'];train,held,_=split();rows=[];overlap=[];started=time.monotonic()
    for visit in scan['selected']:
        v=visit['visit'];chunk=raw['chunks'][v];buf=zstandard.ZstdDecompressor().decompress((root/chunk['relative_path']).read_bytes(),max_output_size=chunk['uncompressed_bytes'])
        assert 'sha256:'+hashlib.sha256(buf).hexdigest()==chunk['uncompressed_sha256']
        a=np.frombuffer(buf,dtype='<i2').reshape(-1,2,2);iq=a[...,0].astype(float)+1j*a[...,1].astype(float)
        for start_ms in plan['starts_ms']:
            start=round(start_ms*RATE/1000);stop=start+70000;atoms=[]
            for mode in (0,1):
                old=lookup[v,start_ms,mode];pair=[dict(r) for r in visit['modes'][mode]['seeds']]
                ep=[r['integer_epoch_sample']+r['fractional_epoch_offset_samples'] for r in pair]
                pair[1]['fractional_epoch_offset_samples']+=round((ep[0]-ep[1])/(RATE/750))*(RATE/750)
                epoch=np.mean([r['integer_epoch_sample']+r['fractional_epoch_offset_samples'] for r in pair]);frac=epoch-round(epoch)
                for r in pair:r['fractional_epoch_offset_samples']+=old['timing_offset_samples']-frac
                result=E.extract_candidate(iq,visit['edge'],pair,start,stop,[0.],train,held)
                traintones=np.stack([E._tone_channels(iq,visit['edge'],result['frame_starts'],pair[rx]['tracking_absolute_baseband_cfo_hz'],result['midpoint_sample'],rx,train,result['frame_fractional_offsets_samples'])[0] for rx in (0,1)])
                frequency=old['coefficients']['residual_frequency_hz'];ztr,rtr=tone_summary(traintones,train,result,frequency);zte,rte=tone_summary(result['held_tone_channels'],held,result,frequency)
                bins=result['tone_frequencies_hz'];delay,boundary=fit_delay(ztr,bins);rotation=np.exp(-2j*np.pi*(bins-np.mean(bins))*delay)
                rows.append(dict(visit=v,start_ms=start_ms,mode=mode,utc_ns=old['utc_ns'],bins_hz=bins.tolist(),train_complex=[[float(z.real),float(z.imag)] for z in ztr],held_complex=[[float(z.real),float(z.imag)] for z in zte],train_R=rtr.tolist(),held_R=rte.tolist(),delay_s=delay,delay_boundary=boundary,train_pivot_phase=float(np.angle(np.sum(ztr*rotation))),held_pivot_phase=float(np.angle(np.sum(zte*rotation))),original_train_phase=old['coefficients']['train']['phase_rad'],original_held_phase=old['coefficients']['held']['phase_rad']))
                atoms.append(atom(result,visit['edge'],pair[1]['tracking_absolute_baseband_cfo_hz'],start,stop))
            coherence=abs(np.vdot(atoms[0],atoms[1]))/np.sqrt(np.vdot(atoms[0],atoms[0]).real*np.vdot(atoms[1],atoms[1]).real)
            overlap.append(dict(visit=v,start_ms=start_ms,template_coherence=float(coherence)))
        print(sid,'visit',v,'tone windows',len(rows),flush=True)
    output=dict(protocol=protocol,rows=rows,template_overlaps=overlap,elapsed_s=time.monotonic()-started)
    (OUT/(sid+'.json')).write_text(json.dumps(output,indent=2)+'\n')

if __name__=='__main__':main()
