"""Replay a bounded frozen raw-IQ panel and independently refine known pilots."""

import argparse
import json
from pathlib import Path
import numpy as np
from local_pilot_refinement import PilotWorkspace
from probe_native_dynamic_timing import BUILD
from probe_native_fft_bias import response_curve,debias
from run_algo01_ds23_sample import ROOT,read,write,sha
from leo.analysis.starlink.native_short_window import NativeShortWindow
from leo.analysis.starlink.templates import qin_edge_pilot_frame,CONTROL_SYMBOL_ROLL
from leo.analysis.starlink.fast_scan_scores import conditioned_glrt64_score

OUT=ROOT/'reports/2026_10_19_ds23_raw_pilot_refinement'


def replay_match(candidates,peak,fs):
    eligible=[c for c in candidates if c['fractional_epoch']['status']=='complete']
    if not eligible:return None
    count=round(fs/750);target=peak['integer_epoch_sample']+peak['fractional_epoch_offset_samples']
    def difference(c):
        epoch=c['refined_epoch']+c['fractional_epoch']['offset_samples'];delta=abs(epoch-target)%count
        return min(delta,count-delta)
    chosen=min(eligible,key=lambda c:abs(c['fractional_epoch']['tracking_cfo_hz']-peak['fractional_tracking_cfo_hz'])/50+difference(c))
    return dict(candidate=chosen,CFO_difference_hz=float(chosen['fractional_epoch']['tracking_cfo_hz']-peak['fractional_tracking_cfo_hz']),
        epoch_difference_samples=float(difference(chosen)),margin_difference=float(chosen['fractional_epoch']['margin']-peak['fractional_margin']))


def run(case,panel_label='initial'):
    suffix='' if panel_label=='initial' else '_'+panel_label
    name=case+suffix;panel=OUT/(name+'_panel.npz');z=np.load(panel,allow_pickle=False);metadata=json.loads(str(z['metadata_json']))
    assert metadata['case']==case;fs=metadata['sample_rate_hz'];library=BUILD/'libleo-adaptive-detector.so'
    assert sha(library)==read(BUILD/'build-receipt.json')['outputs'][library.name]
    contexts={};replayed={};curves={};rows=[]
    try:
        for number,point in enumerate(metadata['points']):
            edge=point['edge'];values=np.array(z[point['window_key']],copy=True)
            if edge not in contexts:
                exact=np.asarray(qin_edge_pilot_frame(fs,edge),dtype='<c16');control=np.asarray(qin_edge_pilot_frame(fs,edge,symbol_roll=CONTROL_SYMBOL_ROLL),dtype='<c16')
                contexts[edge]=NativeShortWindow(str(library),exact,control,sample_rate_hz=fs,receiver_count=2,fractional_epoch=True)
                curves[edge]=response_curve(fs,edge)
            if point['window_key'] not in replayed:replayed[point['window_key']]=contexts[edge].analyze(values)
            native=replayed[point['window_key']]['rows'][point['receiver_offset']]['candidates'];peak=point['peak']
            match=replay_match(native,peak,fs)
            original=peak['fractional_tracking_cfo_hz'];epoch=peak['integer_epoch_sample']+peak['fractional_epoch_offset_samples']
            samples=values[:,point['receiver_offset'],0].astype(float)+1j*values[:,point['receiver_offset'],1].astype(float)
            public=conditioned_glrt64_score(samples,fs,epoch_sample=peak['integer_epoch_sample'],acquired_cfo_hz=original,
                edge=edge,fractional_epoch_offset_samples=peak['fractional_epoch_offset_samples'])
            workspace=PilotWorkspace(samples,fs,edge,epoch)
            fixed=workspace.frequency_fit(original);joint=workspace.joint_fit(fixed['CFO_hz'])
            odd=workspace.frequency_fit(original,subset='odd');even=workspace.frequency_fit(original,subset='even')
            for r in (fixed,joint,odd,even):r['effective_time_from_probe_start_s']=workspace.effective_time(r)
            supported=1000<abs(original)<399000
            record=dict(point=point,archived_CFO_hz=original,template_debiased_CFO_hz=float(debias(original,curves[edge])) if supported else original,
                template_debias_supported=supported,
                public_scorer_replay=dict(exact_score_difference=public.exact_score-peak['fractional_exact_score'],
                    control_score_difference=public.control_score-peak['fractional_control_score'],residual_CFO_hz=public.residual_cfo_hz),
                replay=match,fixed_epoch_CFO=fixed,joint_CFO_epoch_rate=joint,odd_frames=odd,even_frames=even,
                odd_even_CFO_difference_hz=odd['CFO_hz']-even['CFO_hz'],
                archived_score_in_local_model=float(workspace.evaluate([original])[0]),
                archived_control_in_local_model=float(workspace.evaluate([original],control=True)[0]))
            rows.append(record)
            write(OUT/(name+'_partial.json'),dict(case=case,rows=rows,source_sha256=sha(Path(__file__))))
            print(case,number,'RX',point['receiver_id'],'CH',point['channel'],'replay delta',None if match is None else round(match['CFO_difference_hz'],4),
                'local delta',round(fixed['CFO_hz']-original,2),'joint delta',round(joint['CFO_hz']-original,2),'ppm',joint['modulation_ppm'],flush=True)
    finally:
        for c in contexts.values():c.close()
    write(OUT/(name+'.json'),dict(case=case,panel_label=panel_label,rows=rows,panel_sha256=sha(panel),panel_metadata=metadata,
        source_sha256=sha(Path(__file__)),refinement_source_sha256=sha(ROOT/'tools/local_pilot_refinement.py'),
        native_library_sha256=sha(library),native_build_receipt_sha256=sha(BUILD/'build-receipt.json'),
        public_scorer_source_sha256={n:sha(ROOT/'src/leo/analysis/starlink'/n) for n in ['fast_scan_scores.py','fast_scan_fractional.py','templates.py']},
        no_GPS_TLE_satellite_or_position_input=True,original_GLRT_contracts_not_modified=True,
        raw_IQ_is_local_replay_prerequisite_not_published_payload=True,
        higher_in_sample_score_is_not_proof_of_more_accurate_CFO=True))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--case',required=True)
    parser.add_argument('--panel-label',choices=['initial','tracks'],default='initial')
    args=parser.parse_args();run(args.case,args.panel_label)
