"""Project frozen integer GLRT outputs and evaluate the unchanged tracker."""
import csv
from collections import Counter
import hashlib
import json
from pathlib import Path
import statistics
import subprocess
import sys
import time
from types import SimpleNamespace

from leo.application.persistent_hop_trajectory import fractional_glrt64_support_geometry
from leo.contracts.digests import canonical_digest

HERE=Path(__file__).resolve().parent
REPORTS=HERE.parent
BASE=REPORTS/'2026_09_30_arm_fast_tracks/server-baseline/output'
OLD=REPORTS/'2026_09_30_arm_streaming_tracks/qualification/rolling-backfill'
sys.path.insert(0,str(REPORTS/'2026_09_30_arm_streaming_tracks'))
from evaluate import fit_quality
sys.path.insert(0,str(REPORTS/'2026_09_30_arm_curvature_tracks/evaluation'))
import compare_membership as m


def calls(folder):
    result={}
    for p in sorted(folder.glob('batch-*.jsonl')):
        begin=int(p.stem.split('-')[1])
        for line in p.read_text().splitlines():
            doc=json.loads(line)
            if 'result' not in doc:continue
            call=doc['result'];visit=begin+call['sequence']
            assert visit not in result
            result[visit]=call
    assert set(result)==set(range(2215))
    return result


def project(arm,out):
    done=json.loads((arm/'completion.json').read_text());assert done['status']=='PASS'
    manifest=json.loads((arm/'capture-manifest.json').read_text())
    inv=json.loads((arm/'inventory.json').read_text());assert len(inv)==2215
    cs=calls(arm)
    analysis=canonical_digest({'algorithm':'coarse-gate-disabled-full-scan-v1',
        'completion':m.digest(arm/'completion.json'),'inventory':m.digest(arm/'inventory.json'),
        'batches':[(p.name,m.digest(p)) for p in sorted(arm.glob('batch-*.jsonl'))]})
    capture='sha256:b74c950fb172433dab804ddd14b46a3f4c6c1d2e85a09855b0bfdff5da78e015'
    timing=manifest['timing'];fs=2500000
    obs=['candidate_id\tsource_group_id\treceiver_id\tchannel\tedge\tactual_rf_hz\tsupport_start_utc_ns\tsupport_center_utc_ns\tsupport_end_utc_ns\tmeasured_cfo_hz\texact_score\tcontrol_score\tmargin']
    mapping=['candidate_id\tsource_group_id\tvisit\treceiver_id\tprobe_index\tcandidate_rank\tepoch_kind\tdetector_side']
    for visit,call in sorted(cs.items()):
        event=inv[visit]['event']
        for row in call['rows']:
            rx=row['receiver_id'];assert row['probe_index']==0 and row['probe_start_ms']==0
            group=canonical_digest({'capture':capture,'visit':visit,'rx':rx,'probe':0})
            for rank,c in enumerate(row['candidates']):
                if c['margin']<.025:continue
                geometry=fractional_glrt64_support_geometry(SimpleNamespace(integer_epoch_sample=c['epoch'],
                    fractional_epoch_offset_samples=0.),sample_rate_hz=fs,probe_sample_count=50000)
                relative=event['valid_start_counter']-timing['session_start_device_sample_counter']
                utc=lambda local:timing['first_sample_estimate_utc_ns']+round((relative+local)*1e9/fs)
                cid=canonical_digest({'group':group,'rank':rank,'analysis':analysis})
                values=[cid,group,rx,event['target']['channel'],event['target']['edge'],
                    float(event['target']['rf_center_hz']-event['actual_if_offset_hz']),
                    utc(geometry.source_start_in_probe),utc(geometry.center_in_probe_samples),utc(geometry.source_end_in_probe),
                    c['tracking_cfo_hz'],c['exact_score'],c['control_score'],c['margin']]
                obs.append('\t'.join(map(str,values)))
                mapping.append('\t'.join(map(str,[cid,group,visit,rx,0,rank,'integer','arm-ungated'])))
    (out/'observations.tsv').write_text('\n'.join(obs)+'\n')
    (out/'candidate-map.tsv').write_text('\n'.join(mapping)+'\n')
    return cs,analysis


def main():
    out=HERE/'analysis';out.mkdir(exist_ok=False)
    cs,analysis=project(HERE/'arm',out)
    subset=REPORTS/'2026_10_01_arm_glrt_missing_diagnosis/physical'
    repeated=0
    for p in sorted(subset.glob('visits-*.json')):
        visits=json.loads(p.read_text());suffix=p.stem.split('-')[1]
        for line in (subset/f'ungated-{suffix}.jsonl').read_text().splitlines():
            doc=json.loads(line)
            if 'result' not in doc:continue
            call=doc['result'];visit=visits[call['sequence']]
            for before,after in zip(call['rows'],cs[visit]['rows']):
                assert {k:v for k,v in before.items() if k!='timings_ms'}=={k:v for k,v in after.items() if k!='timings_ms'},visit
            repeated+=1
    assert repeated==85
    binary=REPORTS/'2026_10_01_arm_rolling_backfill/component/leo-streaming-rolling-backfill'
    times=[]
    for repeat in range(3):
        start=time.monotonic();r=subprocess.run([str(binary),str(out/'observations.tsv')],text=True,capture_output=True,check=True,timeout=90)
        (out/f'tracks-{repeat}.tsv').write_text(r.stdout);(out/f'tracks-{repeat}.stderr').write_text(r.stderr)
        times.append({'whole_s':time.monotonic()-start,'tracking_s':next(float(l.split('\t')[2]) for l in r.stderr.splitlines() if l.startswith('TIMING\treconstruct_s\t'))})
    assert len({m.digest(out/f'tracks-{i}.tsv') for i in range(3)})==1
    so=m.read_observations(BASE/'server-observations.tsv');ao=m.read_observations(out/'observations.tsv')
    ss=m.read_sources(BASE/'server-candidate-map.tsv',so);ars=m.read_sources(out/'candidate-map.tsv',ao)
    refs=m.read_tracks(BASE/'server-tracks.tsv',so);tracks=m.read_tracks(out/'tracks-0.tsv',ao)
    settings=json.loads((REPORTS/'2026_09_30_arm_curvature_tracks/evaluation/thresholds.json').read_text())
    evaluation=m.compare(refs,tracks,so,ao,ss,ars,settings)
    represented=set(evaluation['primary']['reference_segments_with_any_complete_output_indexes'])-{10}
    old=json.loads((OLD/'arm-evaluation.json').read_text())
    before=set(old['primary']['reference_segments_with_any_complete_output_indexes'])-{10}
    evaluation['reviewed']={'represented_count':len(represented),'excluded_reference_indexes':[10],
        'eligible_references':62,'gained':sorted(represented-before),'lost':sorted(before-represented),
        'missing_indexes':sorted(set(range(63))-{10}-represented)}
    evaluation['fit_quality']=fit_quality(tracks,ao)
    evaluation['duration_buckets']={}
    for name,lo,hi in [('short',0,15),('medium',15,30),('long',30,float('inf'))]:
        ids={r.index for r in refs.values if lo<=(r.end_ns-r.start_ns)/1e9<hi and r.index!=10}
        evaluation['duration_buckets'][name]={'before':len(ids&before),'after':len(ids&represented),'denominator':len(ids)}
    (out/'evaluation.json').write_text(json.dumps(evaluation,indent=2)+'\n')
    # Count outputs with no reference support separately from duplicated/partial hypotheses.
    def reference_support(bank,observations,sources):
        result=[]
        for t in bank.values:
            consistent=set()
            for ref in refs.values:
                if ref.lane==t.lane:
                    met=m.membership_metrics(ref,t,so,observations,ss,sources,settings)
                    consistent.update(met['consistent_sources'])
            result.append({'output_index':t.index,'points':len(t.points),'sources_matching_any_reference':len(consistent),
                'fraction':len(consistent)/len(t.points),'duration_s':(t.end_ns-t.start_ns)/1e9})
        return result
    support=reference_support(tracks,ao,ars)
    oldobs=m.read_observations(BASE/'arm-observations.tsv')
    oldsupport=reference_support(m.read_tracks(OLD/'arm-0.tsv',oldobs),oldobs,m.read_sources(BASE/'arm-candidate-map.tsv',oldobs))
    (out/'output-reference-support.json').write_text(json.dumps(support,indent=2)+'\n')
    (out/'original-output-reference-support.json').write_text(json.dumps(oldsupport,indent=2)+'\n')
    def detector_stats(values):
        ms=[c['call_wall_ms'] for c in values.values()];candidates=[p for c in values.values() for r in c['rows'] for p in r['candidates']]
        return {'dwells':len(ms),'evaluated_candidates':len(candidates),'passing_candidates':sum(p['margin']>=.025 for p in candidates),
            'mean_ms':statistics.mean(ms),'median_ms':statistics.median(ms),'p95_ms':sorted(ms)[__import__('math').ceil(.95*len(ms))-1],
            'max_ms':max(ms),'calls_at_least_120ms':sum(t>=120 for t in ms),'sum_s':sum(ms)/1000}
    original_calls=calls(REPORTS/'2026_09_30_arm_full_scan_comparison/arm-v2')
    lost_candidates=[]
    for visit,original in original_calls.items():
        for before_row,after_row in zip(original['rows'],cs[visit]['rows']):
            assert before_row['receiver_id']==after_row['receiver_id']
            before_candidates=Counter(json.dumps(c,sort_keys=True) for c in before_row['candidates'] if c['margin']>=.025)
            after_candidates=Counter(json.dumps(c,sort_keys=True) for c in after_row['candidates'] if c['margin']>=.025)
            if before_candidates-after_candidates:
                lost_candidates.append({'visit':visit,'receiver':before_row['receiver_id'],
                    'candidates':[json.loads(c) for c in (before_candidates-after_candidates).elements()]})
    (out/'original-candidate-inclusion-differences.json').write_text(json.dumps(lost_candidates,indent=2)+'\n')
    summary={'detector':{'original':detector_stats(original_calls),
                         'ungated':detector_stats(cs)},'tracking':evaluation['reviewed'],
        'duration_buckets':evaluation['duration_buckets'],'hypotheses_before':old['output']['tracks'],'hypotheses_after':len(tracks.values),
        'prediction_p95_before_hz':old['fit_quality']['p95_hz'],'prediction_p95_after_hz':evaluation['fit_quality']['p95_hz'],
        'outputs_without_any_reference_support':sum(r['sources_matching_any_reference']==0 for r in support),
        'outputs_below_50pct_reference_support':sum(r['fraction']<.5 for r in support),
        'original_outputs_without_any_reference_support':sum(r['sources_matching_any_reference']==0 for r in oldsupport),
        'original_outputs_below_50pct_reference_support':sum(r['fraction']<.5 for r in oldsupport),
        'long_outputs_without_reference_support':sum(r['sources_matching_any_reference']==0 and r['duration_s']>=30 for r in support),
        'original_long_outputs_without_reference_support':sum(r['sources_matching_any_reference']==0 and r['duration_s']>=30 for r in oldsupport),
        'original_passing_candidates_not_exactly_preserved':sum(len(r['candidates']) for r in lost_candidates),
        'prior_85_dwell_ablation_scientific_results_identical':True,
        'host_tracking_repeats':times,'tracker_binary_sha256':m.digest(binary),'analysis_digest':analysis}
    (out/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps(summary,indent=2))

if __name__=='__main__':main()
