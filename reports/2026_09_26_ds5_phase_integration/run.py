"""Bounded raw DS5 pilot replay using the frozen metadata plan."""
from pathlib import Path
import hashlib,json,time
import numpy as np
import zstandard
import pilot_extract as E

HERE=Path(__file__).resolve().parent
RATE=10_000_000

def split():
    rng=np.random.default_rng(20260926)
    held=set(rng.choice(np.arange(5),2,replace=False).tolist()+rng.choice(np.arange(5,10),3,replace=False).tolist())
    train=np.concatenate([np.arange(4+30*b,30*b+30) for b in range(10) if b not in held])
    test=np.concatenate([np.arange(4+30*b,30*b+30) for b in range(10) if b in held])
    return train,test,sorted(held)

def summarize(result,a,ntrain):
    times=result['frame_starts'][:,None]+result['frame_symbol_offsets_samples']
    outputs={}
    for name in ('coefficients','controls'):
        z=a[name][1]*np.conj(a[name][0]);tr=z[:,:ntrain].ravel()
        frequency,_,_=E.fit_linear_phasor(tr,times[:,:ntrain].ravel()/RATE,np.maximum(abs(tr),1e-30),result['midpoint_sample']/RATE)
        corrected=z*np.exp(-2j*np.pi*frequency*(times-result['midpoint_sample'])/RATE)
        def stat(x):
            m=np.mean(x);return dict(phase_rad=float(np.angle(m)),R=float(abs(m)/max(np.mean(abs(x)),1e-30)))
        outputs[name]=dict(train=stat(corrected[:,:ntrain]),held=stat(corrected[:,ntrain:]),full=stat(corrected),residual_frequency_hz=float(frequency))
    ratios=[]
    for rx in range(2):
        exact=np.sum(abs(a['coefficients'][rx,:,ntrain:].sum(axis=1))**2)
        null=np.sum(abs(a['controls'][rx,:,ntrain:].sum(axis=1))**2)
        ratios.append(float(exact/max(null,1e-30)))
    outputs['held_exact_control_ratios']=ratios
    return outputs

def main():
    plan=json.loads((HERE/'plan.json').read_text());train,held,held_blocks=split()
    for scan in plan['scans']:
        sid=scan['session_id'];destination=HERE/(sid+'.json')
        if destination.exists():
            saved=json.loads(destination.read_text())
            if saved['plan_sha256']!=hashlib.sha256((HERE/'plan.json').read_bytes()).hexdigest():
                raise ValueError('cached scan does not match the frozen plan; use a new report directory')
            print('already completed',sid,flush=True);continue
        root=Path(scan['metadata']['recording_manifest_path']).parent
        rawbytes=(root/'manifest.json').read_bytes()
        assert 'sha256:'+hashlib.sha256(rawbytes).hexdigest()==scan['metadata']['recording_manifest_file_sha256']
        raw=json.loads(rawbytes)['manifest'];timing=raw['timing'];rows=[];audits=[];errors=[];t0=time.monotonic()
        events={x['visit_index']:x for x in raw['receipt']['events']}
        for visit in scan['selected']:
            v=visit['visit'];chunk=raw['chunks'][v]
            buf=zstandard.ZstdDecompressor().decompress((root/chunk['relative_path']).read_bytes(),max_output_size=chunk['uncompressed_bytes'])
            assert 'sha256:'+hashlib.sha256(buf).hexdigest()==chunk['uncompressed_sha256']
            assert events[v]['valid_start_counter']==visit['valid_start_counter']
            a=np.frombuffer(buf,dtype='<i2').reshape(-1,2,2)
            iq=a[...,0].astype(float)+1j*a[...,1].astype(float)
            audits.append(dict(visit=v,chunk_sha256=chunk['uncompressed_sha256'],sample_count=len(iq),max_abs_ci16=int(np.max(np.abs(a.astype(np.int32)))),clipped_rows=int(np.count_nonzero(np.any(abs(a.astype(np.int32))>=32767,axis=(1,2))))))
            for start_ms in plan['starts_ms']:
                start=round(start_ms*RATE/1000);stop=start+round(plan['width_ms']*RATE/1000)
                for mode,m in enumerate(visit['modes']):
                    try:
                        pair=[dict(r) for r in m['seeds']]
                        ep=[float(r['integer_epoch_sample'])+float(r['fractional_epoch_offset_samples']) for r in pair]
                        # Equivalent frame origins must be near each other before averaging.
                        shift=round((ep[0]-ep[1])/(RATE/750))*(RATE/750)
                        pair[1]['fractional_epoch_offset_samples']+=shift
                        epoch=np.mean([r['integer_epoch_sample']+r['fractional_epoch_offset_samples'] for r in pair]);fraction=epoch-round(epoch)
                        results=[]
                        for offset in np.unique([0.,fraction-.25,fraction,fraction+.25]):
                            seeds=[dict(r,fractional_epoch_offset_samples=r['fractional_epoch_offset_samples']-fraction+offset) for r in pair]
                            result=E.extract_candidate(iq,visit['edge'],seeds,start,stop,[0.],train,held)
                            results.append((result['alternatives'][0]['train_score'],float(offset),result))
                        _,offset,result=max(results,key=lambda x:x[0]);value=summarize(result,result['alternatives'][0],len(train))
                        counter=visit['valid_start_counter']+result['midpoint_sample']
                        utc=int(timing['first_sample_estimate_utc_ns'])+round((counter-timing['session_start_device_sample_counter'])*1e9/RATE)
                        value.update(session_id=sid,visit=v,start_ms=start_ms,mode=mode,channel=visit['channel'],edge=visit['edge'],group=visit['group'],partition=visit['partition'],utc_ns=utc,utc_bracket_ms=timing['first_sample_bracket_width_ns']/1e6,rf_estimate_hz=visit['rf_center_hz']+float(pair[0]['tracking_absolute_baseband_cfo_hz']),rx0_cfo_hz=float(pair[0]['tracking_absolute_baseband_cfo_hz']),rx1_cfo_hz=float(pair[1]['tracking_absolute_baseband_cfo_hz']),rx0_track_ids=m['rx0_track_ids'],rx1_track_ids=m['rx1_track_ids'],frame_count=int(len(result['frame_starts'])),timing_offset_samples=offset)
                        rows.append(value)
                    except Exception as exc:
                        errors.append(dict(visit=v,start_ms=start_ms,mode=mode,error=repr(exc)))
            print(sid,'visit',v,'rows',len(rows),'errors',len(errors),flush=True)
        payload=dict(schema='ds5-phase-replay/v1',session_id=sid,plan_sha256=hashlib.sha256((HERE/'plan.json').read_bytes()).hexdigest(),held_pilot_blocks=held_blocks,rows=rows,chunk_audits=audits,errors=errors,elapsed_s=time.monotonic()-t0)
        destination.write_text(json.dumps(payload,indent=2)+'\n')

if __name__=='__main__':main()
