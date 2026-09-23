"""Bounded saved-IQ comparison with phase-blind selection and per-dwell references."""
import dataclasses, hashlib, importlib.util, json, sys, time
from pathlib import Path
import numpy as np
from scipy.signal import fftconvolve, firwin
REPO=Path('/home/mouse9911/gits/leo-scan-9a10-50km-report')
RESEARCH=Path('/home/mouse9911/gits/leo-tracker-adaptive-geometry-phase')
OUT=Path('/tmp/phase-1aa-review')
sys.path.insert(0,str(RESEARCH/'tools'))
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(spec);sys.modules[name]=m;spec.loader.exec_module(m);return m
guided=load('leo.analysis.starlink.glrt_guided_broadband_phase',RESEARCH/'src/leo/analysis/starlink/glrt_guided_broadband_phase.py')
from report_glrt_guided_broadband_phase import bootstrap_frequency
curve=load('phase_curve_existing',REPO/'reports/figures/2026_09_22_adaptive_phase_fit/fit_visits.py')
from leo.analysis.starlink.broadband_alignment import estimate_broadband_alignment
from leo.analysis.starlink.broadband_phase_tracking import frequency_held_out_tracking
from leo.analysis.starlink.relative_phase import extract_relative_phase, normalize_response, refined_pilot
from leo.analysis.starlink.adaptive_dual_rx_phase_extract import extract_dual_receiver_phase, extract_dual_receiver_phase_with_offset_authority, extract_dual_receiver_phase_with_offset_authority_shared_residual
from leo.analysis.starlink.pilot_methods import _conditioned_correlation_workspace
from leo.application.adaptive_relative_phase import relative_phase_probes
from leo.application.adaptive_dual_rx_phase_v2 import extract_phase_visit_v2
from leo.scanner.adaptive_hop_analysis import analyze_adaptive_hop_visit
from leo.scanner.host_adaptive_products import bind_actual_visit_analysis
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis import AdaptiveHopAnalysisStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore
def serial(v):
    if dataclasses.is_dataclass(v):return serial(dataclasses.asdict(v))
    if isinstance(v,dict):return {str(k):serial(x) for k,x in v.items()}
    if isinstance(v,(list,tuple)):return [serial(x) for x in v]
    if isinstance(v,np.ndarray):return serial(v.tolist())
    if isinstance(v,np.generic):return serial(v.item())
    if isinstance(v,complex):return {'real':v.real,'imag':v.imag}
    return v
def save(path,data):path.write_text(json.dumps(serial(data),indent=2,allow_nan=False)+'\n')
def wrap(x):return np.angle(np.exp(1j*np.asarray(x)))
def run():
    inv=json.loads((OUT/'inventory.json').read_text());sid=inv['session_id'];selected=[]
    for ch in range(1,5):
        rows=[r for r in inv['visits'] if r['priority'] is not None and r['target']['channel']==ch]
        selected.extend(r['visit_index'] for r in sorted(rows,key=lambda r:-r['priority'])[:2])
    multi=[r['visit_index'] for r in inv['visits'] if r['paired_count']>=2]
    save(OUT/'selection.json',dict(selected_visits=selected,double_difference_visits=multi,selection='Top two minimum RX-paired GLRT margins per RF channel; no phase metric selection',input_manifest_sha256=inv['input_manifest_sha256']))
    print('Frozen selection',selected,'two-source',multi,flush=True)
    captures=AdaptiveHopIqStore(Path('/srv/bulk/leo'),read_only=True);analyses=AdaptiveHopAnalysisStore(Path('/srv/bulk/leo'),read_only=True)
    pub=captures.inspect(sid);assert pub.manifest_sha256==inv['input_manifest_sha256']
    binding=bind_actual_visit_analysis(pub.manifest.receipt,input_manifest_sha256=pub.manifest_sha256,probe_stride_ms=120)
    config=binding.configuration.model_copy(update={'probe_stride_ms':20});started=time.monotonic();results=[]
    with AdaptiveHopAnalysisInputStore(captures).source(sid) as source, analyses.job(binding) as job:
        ordinals={v.event.visit_index:i for i,v in enumerate(source.visits)}
        for index in selected:
            dest=OUT/f'visit-{index}.json'
            if dest.exists():results.append(json.loads(dest.read_text()));continue
            ordinal=ordinals[index];iq=source.read_visit(ordinal);rate=config.sample_rate_hz
            row=dict(visit=index,sample_rate_hz=rate,iq_shape=list(iq.shape),iq_sha256=hashlib.sha256(iq.tobytes()).hexdigest(),inventory=next(r for r in inv['visits'] if r['visit_index']==index),failures=[])
            try:
                dense=analyze_adaptive_hop_visit(source,ordinal,configuration=config);row['dense_glrt']=dense.model_dump(mode='json')
                probes=relative_phase_probes(dense);row['paired_probe_count']=len(probes)
                row['production_relative_phase']=extract_relative_phase(iq,rate,dense.target.edge,probes)
                train=[p for p in probes if p.start_sample+rate*20//1000<=len(iq)//2]
                seed=float(np.median([p.seeds[1].acquired_cfo_hz-p.seeds[0].acquired_cfo_hz for p in train]))
                fit=estimate_broadband_alignment(iq,rate,receiver_cfo_seed_hz=seed,cfo_search_half_width_hz=900000);m=fit.model;row['broadband']=serial(fit)
                def carrier(sample):
                    dt=(np.asarray(sample)-m.reference_sample)/rate
                    return 2*np.pi*(m.relative_cfo_hz*dt+.5*m.relative_cfo_rate_hz_s*dt**2)
                row['original_response_tracking']=frequency_held_out_tracking(iq,rate,m)
                n=4096;freq=np.fft.fftshift(np.fft.fftfreq(n,1/rate));win=np.hanning(n);left=[];right=[]
                for start in range(0,len(iq)//2-n+1,n):
                    left.append(np.fft.fftshift(np.fft.fft(iq[start:start+n,0]*win)))
                    right.append(np.fft.fftshift(np.fft.fft(iq[start:start+n,1]*np.exp(-1j*carrier(np.arange(start,start+n)))*win)))
                eligible=abs(freq)<rate/2-40000
                shifts=[m.relative_cfo_hz+m.relative_cfo_rate_hz_s*(s-m.reference_sample)/rate for s in (0,len(iq)-1)]
                for shift in shifts:eligible&=abs(freq+shift)<rate/2-40000
                ids,h=normalize_response(np.array(left),np.array(right),freq,np.searchsorted(freq,m.frequency_hz),m.channel_transfer,eligible)
                updated=dataclasses.replace(m,frequency_hz=tuple(freq[ids]),channel_transfer=tuple(h))
                allphase=frequency_held_out_tracking(iq,rate,updated,training_fraction=0);held=frequency_held_out_tracking(iq,rate,updated)
                row.update(normalized_model=serial(updated),all_band_phase=allphase,held_band_phase=held)
                tt=np.array([r['center_sample']/rate for r in allphase['rows']]);a=np.array([r['training_band_phase_rad'] for r in allphase['rows']])
                best,curves,errors,sigma=curve.select_fit(tt,a)
                ht=np.array([r['center_sample']/rate for r in held['rows']]);bp=np.array([r['training_band_phase_rad']+r['held_band_residual_phase_rad'] for r in held['rows']]);validation={}
                for name,values in curves.items():
                    residual=wrap(bp-np.interp(ht,tt,values))
                    validation[name]=dict(B_rms_deg=float(np.degrees(np.sqrt(np.mean(residual**2)))),B_resultant=float(abs(np.mean(np.exp(1j*residual)))))
                row['curve_fits']=dict(selected=best,time_s=tt,curves_rad=curves,A_cv_rms_deg={k:float(np.degrees(v)) for k,v in errors.items()},B_validation=validation)
                row['pilot_variants']=[];guides=[]
                for pi,p in enumerate(probes):
                    start=p.start_sample;stop=start+rate*20//1000;chunk=iq[start:stop]
                    authority=m.relative_cfo_hz+m.relative_cfo_rate_hz_s*((start+stop)/2-m.reference_sample)/rate
                    for name in ('principal','branch_lifted','offset_authority','shared_residual','refined_shared'):
                        try:
                            if name in ('principal','branch_lifted'):
                                obs=extract_dual_receiver_phase(chunk,rate,dense.target.edge,p.epoch_sample,p.seeds,frame_radius=16,lift_frame_frequency_branch=name=='branch_lifted')
                            elif name=='refined_shared':obs=refined_pilot(chunk,rate,dense.target.edge,p,authority)
                            else:
                                fn=extract_dual_receiver_phase_with_offset_authority if name=='offset_authority' else extract_dual_receiver_phase_with_offset_authority_shared_residual
                                obs=fn(chunk,rate,dense.target.edge,p.epoch_sample,p.seeds,authority,common_reference_sample=0,frame_radius=16).observation
                            center=start+obs.center_sample
                            row['pilot_variants'].append(dict(method=name,time_s=center/rate,support_start_s=start/rate,support_end_s=stop/rate,residual_phase_rad=float(wrap(obs.wrapped_phase_rad-carrier(center))),resultant=obs.resultant_length,phase_se_deg=obs.phase_standard_error_deg,relative_frequency_hz=obs.relative_frequency_hz,observation=serial(obs)))
                        except ValueError as exc:row['failures'].append(dict(method=name,probe=pi,reason=str(exc)))
                    if stop<=len(iq)//2:
                        try:
                            estimates=[]
                            for rx,s in enumerate(p.seeds):
                                epoch=int(round(s.reference_sample));offset=s.reference_sample-epoch
                                ws=_conditioned_correlation_workspace(chunk[:,rx],rate,epoch,s.acquired_cfo_hz,edge=dense.target.edge,selected_symbols=np.arange(2,66),fractional_epoch_offset_samples=offset)
                                estimates.append(bootstrap_frequency(ws.select(np.arange(2,66)),s.acquired_cfo_hz,seed=index+100*rx+pi))
                            guides.append(guided.GuidePoint((start+stop)/2,estimates[1]['frequency_hz']-estimates[0]['frequency_hz'],float(np.hypot(*[e['sigma_hz'] for e in estimates]))))
                        except ValueError as exc:row['failures'].append(dict(method='GLRT_guide',probe=pi,reason=str(exc)))
                row['guides']=serial(guides);row['guided']={}
                for name,bias in [('absolute',False),('evolution',True)]:
                    try:row['guided'][name]=serial(guided.estimate_glrt_guided_broadband_phase(iq,rate,guides,broadband_cfo_seed_hz=m.relative_cfo_hz,cfo_search_half_width_hz=2000,fit_guide_bias=bias))
                    except ValueError as exc:row['failures'].append(dict(method='guided_'+name,reason=str(exc)))
                corrected=iq[:,1]*np.exp(-1j*carrier(np.arange(len(iq))))
                taps=np.sinc(np.arange(-32,33)+m.fractional_delay_samples)*np.hanning(65);corrected=fftconvolve(corrected,taps/taps.sum(),mode='same')
                low=max([-rate/2]+[-rate/2-s for s in shifts])+40000;high=min([rate/2]+[rate/2-s for s in shifts])-40000
                taps=firwin(513,(high-low)/2,fs=rate)*np.exp(2j*np.pi*(high+low)/2*(np.arange(513)-256)/rate)
                aligned=np.column_stack([fftconvolve(iq[:,0],taps,mode='same'),fftconvolve(corrected,taps,mode='same')]);ix=np.arange(rate*60//1000,rate*62//1000)
                row['sample_excerpt']=dict(time_s=ix/rate,raw_phase_rad=np.angle(iq[ix,1]*iq[ix,0].conj()),corrected_phase_rad=np.angle(aligned[ix,1]*aligned[ix,0].conj()))
                row['state']='replayed'
                print(index,'done',row['production_relative_phase']['supported'],'B coherence',held['tracked']['coherence'],'curve',best,validation[best],'elapsed',round(time.monotonic()-started,1),flush=True)
            except Exception as exc:
                row['state']='abstained';row['reason']=f'{type(exc).__name__}: {exc}';print(index,row['reason'],flush=True)
            save(dest,row);results.append(serial(row))
        doubles=[]
        for index in multi:
            try:
                result=extract_phase_visit_v2(source.read_visit(ordinals[index]),job.read_visit(index),glrt_binding_sha256=binding.sha256)
                doubles.append(result.model_dump(mode='json'));print('double',index,result.state,len(result.hypotheses),flush=True)
            except Exception as exc:doubles.append({'visit_index':index,'error':str(exc)})
    captures.close();analyses.close()
    save(OUT/'double-differences.json',doubles);save(OUT/'comparison.json',dict(session_id=sid,selection=selected,elapsed_s=time.monotonic()-started,visits=results))
    modules=[sys.modules[name].__file__ for name in ('leo.analysis.starlink.relative_phase','leo.analysis.starlink.broadband_alignment','leo.analysis.starlink.adaptive_dual_rx_phase_extract')]+[guided.__file__,curve.__file__,str(RESEARCH/'tools/report_glrt_guided_broadband_phase.py')]
    save(OUT/'source-digests.json',{path:hashlib.sha256(Path(path).read_bytes()).hexdigest() for path in modules})
if __name__=='__main__':run()
