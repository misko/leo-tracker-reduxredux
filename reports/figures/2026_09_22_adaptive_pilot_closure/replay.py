"""Refined known-pilot phase versus broadband on identical adaptive frame times."""
import argparse
import gzip
import json
import sys
from pathlib import Path
from types import SimpleNamespace
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / '2026_09_22_pilot_support_closure'))
sys.path.insert(0, str(ROOT / '2026_09_22_multi_dwell_track_phase'))
from refined_pilot import refine_shared_pilot
from plot_multi_dwell_phase import compensate, common_band
from report_broadband_alignment import serializable
from leo.analysis.starlink.adaptive_dual_rx_phase_extract import ReceiverPhaseSeed
from leo.analysis.starlink.adaptive_dual_rx_phase import fit_linear_phasor
from leo.application.adaptive_dual_rx_phase_v2 import _phase_blind_pairs
from leo.scanner.adaptive_hop_analysis import AdaptiveHopAnalysisConfigurationV1, analyze_adaptive_hop_visit
from leo.storage.adaptive_hop import AdaptiveHopIqStore
from leo.storage.adaptive_hop_analysis_source import AdaptiveHopAnalysisInputStore

def wrap(x): return np.angle(np.exp(1j * x))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--visits', type=int, nargs='*')
    parser.add_argument('--inject-phase', type=float, default=0.0, help='Known RX1 phase rotation in radians for an equivariance check')
    args = parser.parse_args(); args.output.mkdir(parents=True, exist_ok=True)
    previous = json.loads(gzip.decompress((ROOT / '2026_09_22_adaptive_phase_fit/results.json.gz').read_bytes()))
    store = AdaptiveHopIqStore(Path('/srv/bulk/leo'), read_only=True)
    results = []
    with AdaptiveHopAnalysisInputStore(store).source(previous['session']) as source:
        assert source.input_manifest_sha256 == previous['input_manifest_sha256']
        fs = source.receipt.plan.geometry.sample_rate_hz
        for saved in previous['rows']:
            index = saved['visit']
            if args.visits and index not in args.visits: continue
            print('Start', index, flush=True)
            iq = source.read_visit(index); m = SimpleNamespace(**saved['model'])
            if args.inject_phase:
                iq=iq.copy(); iq[:,1]*=np.exp(1j*args.inject_phase)
            aligned = common_band(compensate(iq, m))
            centers=[]; phases=[]; coherence=[]
            for start in range(1250, len(iq)-2500, 500):
                x,y=aligned[start:start+1250].T
                z=np.vdot(x,y); centers.append((start+624.5)/fs)
                phases.append(float(np.angle(z)))
                coherence.append(float(abs(z)/np.sqrt(np.vdot(x,x).real*np.vdot(y,y).real)))
            times=np.array(centers); phi=np.unwrap(phases)
            def carrier(t):
                dt=np.asarray(t)-m.reference_sample/fs
                return 2*np.pi*(m.relative_cfo_hz*dt+.5*m.relative_cfo_rate_hz_s*dt**2)
            visit=analyze_adaptive_hop_visit(source,index,configuration=AdaptiveHopAnalysisConfigurationV1(sample_rate_hz=fs,probe_stride_ms=20))
            rows=[]; failures=[]
            for probe_index in sorted({p.probe_index for p in visit.probes}):
                subset=visit.model_copy(update={'probes':tuple(p for p in visit.probes if p.probe_index==probe_index)})
                pairs=_phase_blind_pairs(subset)
                if not pairs:
                    failures.append(dict(probe=probe_index,reason='No phase-blind shared candidate'));continue
                left,right,_,start=pairs[0]
                chunk=iq[start:start+fs*20//1000]
                seeds=tuple(ReceiverPhaseSeed(c.acquired_cfo_hz,c.integer_epoch_sample+(c.fractional_epoch_offset_samples or 0)) for c in (left,right))
                authority=m.relative_cfo_hz+m.relative_cfo_rate_hz_s*((start+len(chunk)/2)-m.reference_sample)/fs
                try:
                    initial,refined=refine_shared_pilot(chunk,fs,visit.target.edge,left.integer_epoch_sample,seeds,authority)
                except ValueError as exc:
                    failures.append(dict(probe=probe_index,reason=str(exc)));continue
                for method,obs in [('shared_initial',initial),('refined',refined)]:
                    o=serializable(obs); center=(start+o['center_sample'])/fs
                    ft=(start+np.array(o['receivers'][0]['frame_starts']))/fs
                    if min(ft)<min(times) or max(ft)>max(times):
                        failures.append(dict(probe=probe_index,method=method,reason='Frame outside valid broadband centers'));continue
                    z=[np.array([complex(v['real'],v['imag']) for v in rx['frame_phasors']]) for rx in o['receivers']]
                    basef=m.relative_cfo_hz+m.relative_cfo_rate_hz_s*(center-m.reference_sample/fs)
                    for weighting in ['pilot_amplitude','uniform']:
                        weights=np.sqrt(abs(z[0])*abs(z[1])) if weighting=='pilot_amplitude' else np.ones(len(ft))
                        values=np.exp(1j*(np.interp(ft,times,phi)+carrier(ft)-carrier(center)-2*np.pi*basef*(ft-center)))
                        frequency,expected,resultant=fit_linear_phasor(values,ft,weights,center)
                        measured=wrap(obs.wrapped_phase_rad-carrier(center))
                        rows.append(dict(probe=probe_index,method=method,weighting=weighting,time_s=center,
                            support_start_s=start/fs,support_stop_s=(start+len(chunk))/fs,
                            pilot_phase_rad=float(measured),broadband_phase_rad=float(expected),difference_rad=float(wrap(measured-expected)),
                            pilot_residual_frequency_hz=obs.relative_frequency_hz-basef,broadband_residual_frequency_hz=float(frequency),
                            pilot_resultant=obs.resultant_length,broadband_resultant=float(resultant),frame_times_s=ft.tolist(),
                            observation=o,source_candidates=[c.model_dump(mode='json') for c in (left,right)]))
            summaries=[]
            for method in ['shared_initial','refined']:
                for weighting in ['pilot_amplitude','uniform']:
                    selected=[r for r in rows if r['method']==method and r['weighting']==weighting]
                    train=[r for r in selected if r['support_stop_s']<=.06]
                    held=[r for r in selected if r['support_start_s']>=.06]
                    if not train or not held:continue
                    offset=float(np.angle(np.mean(np.exp(1j*np.array([r['difference_rad'] for r in train])))))
                    for r in selected:r['offset_corrected_difference_deg']=float(np.degrees(wrap(r['difference_rad']-offset)))
                    error=np.array([r['offset_corrected_difference_deg'] for r in held])
                    summaries.append(dict(method=method,weighting=weighting,train_count=len(train),held_count=len(held),
                        training_offset_deg=float(np.degrees(offset)),held_rms_deg=float(np.sqrt(np.mean(error**2))),held_max_deg=float(max(abs(error))),
                        held_frequency_rms_hz=float(np.sqrt(np.mean([(r['pilot_residual_frequency_hz']-r['broadband_residual_frequency_hz'])**2 for r in held])))))
            result=dict(visit=index,broadband_status=saved['status'],model=saved['model'],rows=rows,summaries=summaries,failures=failures,
                scalar_time_s=centers,scalar_unwrapped_phase_rad=phi.tolist(),scalar_coherence=coherence)
            results.append(result)
            (args.output/f'visit-{index}.json').write_text(json.dumps(serializable(result),indent=2)+'\n')
            print(index,summaries,'failures',len(failures),flush=True)
    (args.output/'results.json').write_text(json.dumps(dict(session=previous['session'],input_manifest_sha256=previous['input_manifest_sha256'],injected_phase_rad=args.inject_phase,visits=results),indent=2)+'\n')

if __name__=='__main__':main()
