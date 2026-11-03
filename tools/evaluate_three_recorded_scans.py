"""Stage-by-stage independent controls for three distinct physical ARM replays."""
import argparse
import csv
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import time

from compare_regional_results import compare as compare_search
from evaluate_arm_cadence import timing, json_lines
from evaluate_recorded_pacing import load_reference
from leo.native_pipeline.paced_projection import project_paced
from leo.native_pipeline.membership import SOURCE_HEADER
from leo.native_pipeline.runner import digest


ROOT=Path(__file__).resolve().parents[1]


def save(path, value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False)+'\n')


def verify_iq(server, inventory, events):
    paths=sorted((server/'visits').glob('visit-*.json'))
    if len(paths)!=len(events) or len(inventory)!=len(events):
        raise ValueError('incomplete IQ inventory')
    for i,(p,row,event) in enumerate(zip(paths,inventory,events)):
        result=json.loads(p.read_text())
        if (row['visit']!=i or result['visit']!=i or row['event']!=event or
            result['source']['event']!=event or result['source']['raw_sha256']!=row['raw_sha256'] or
            result['source']['raw_bytes']!=row['size_bytes'] or row['size_bytes']!=2400000):
            raise ValueError('server/staged raw IQ authority mismatch')
    return {'passed':True,'visits':len(events),'bytes':len(events)*2400000,
            'scope':'Independent server decompression versus exported raw bytes/events; device verification receipt required separately'}


def candidate_points(calls, events):
    first=events[0]['valid_start_counter'];points=[]
    for visit,candidates in enumerate(calls):
        event=events[visit]
        for c in candidates:
            rx,probe,rank,epoch,acquired,tracking,exact,control,margin,complete=c
            points.append(dict(visit=visit,time=(event['valid_start_counter']-first)/2500000,
                rx=rx,rank=rank,channel=event['target']['channel'],epoch=epoch,acquired_cfo=acquired,
                cfo=tracking,margin=margin,passing=margin>=.025))
    return points


def native_glrt_parity(arm, host, policy):
    discrete=True;decisions=True;max_cfo=0.;max_score=0.
    if len(arm)!=len(host):raise ValueError('native control visit inventory differs')
    for actual,reference in zip(arm,host):
        if len(actual)!=len(reference):
            discrete=False;decisions=False;continue
        for a,b in zip(actual,reference):
            if not all(math.isfinite(v) for v in a+b):raise ValueError('nonfinite detector output')
            discrete &= all(a[k]==b[k] for k in (0,1,2,3,9))
            decisions &= (a[8]>=.025)==(b[8]>=.025)
            max_cfo=max(max_cfo,*(abs(a[k]-b[k]) for k in (4,5)))
            max_score=max(max_score,*(abs(a[k]-b[k]) for k in (6,7,8)))
    return {'discrete_fields_exact':discrete,'passing_decisions_exact':decisions,
        'maximum_cfo_delta_hz':max_cfo,'maximum_score_delta':max_score,
        'passed':discrete and decisions and max_cfo<=policy['native_glrt_cfo_absolute_tolerance_hz']
                 and max_score<=policy['native_glrt_score_absolute_tolerance']}


def position_stage_wall(rows, total):
    stages={r['stage']:r['wall_s'] for r in rows if r.get('kind')=='stage'}
    for name in ('track_conversion','orbit_generation'):
        if name not in stages:raise ValueError('missing position stage timing')
    points=[r['wall_s'] for r in rows if r.get('kind')=='search_point']
    associations=[r['wall_s'] for r in rows if r.get('kind')=='selected_associations']
    if len(points)!=400 or len(associations)!=1:raise ValueError('incomplete position timing inventory')
    result={k+'_s':v for k,v in stages.items()}
    result.update(search_points_s=sum(points),selected_associations_s=associations[0])
    residual=total-sum(result.values())
    if residual < -1e-6:raise ValueError('position stage clocks exceed total')
    result['other_process_overhead_s']=max(0,residual)
    return result


def host_projection(arm, scan, authority, output, compare_to_arm=True):
    lines=[]
    for row,source in zip(json_lines(arm/'detector.stdout')[:-1],authority):
        for c in row['candidates']:
            rx,probe,rank,epoch,acquired,tracking,exact,control,margin,complete=c
            fields=source.copy();fields[6]=str(probe);fields[7]=str(rx)
            fields+=list(map(str,[rank,epoch,0,tracking,exact,control,margin,int(complete)]))
            lines.append('\t'.join(fields))
    encoded='\n'.join(lines)+'\n';binary='/var/tmp/leo-three-project-host'
    (output/'projection-input.tsv').write_text(encoded)
    r=subprocess.run([binary,'--checkpoint'],input=encoded,text=True,capture_output=True,check=True,timeout=90)
    (output/'observations.tsv').write_text(r.stdout)
    s=subprocess.run([binary],input=encoded,text=True,capture_output=True,check=True,timeout=90)
    support=[]
    for line in s.stdout.splitlines():
        if line=='unavailable':continue
        f=line.split('\t');support.append('\t'.join([f[0],*f[2:5],'1.0','0.0',*f[7:9]]))
    header='META\t'+scan['session_id']+'\t'+scan['manifest_sha256']+'\t'+authority[0][2]+'\n'
    header+='candidate_id\tstart_utc_ns\tcenter_utc_ns\tend_utc_ns\tm0\tm1\tm2\tm3\n'
    (output/'graph.tsv').write_text(header+'\n'.join(support)+'\n')
    if not compare_to_arm:
        return {name:digest(output/name) for name in ('observations.tsv','graph.tsv')}
    return {name:digest(output/name)==digest(arm/name) for name in ('observations.tsv','graph.tsv')}


def evaluate_scan(report, scan, index, sequence='arm-sequence-v1'):
    directory=report/scan['session_id'];arm=report/sequence/f'scan-{index}'
    output=directory/'comparison';output.mkdir()
    capture=json.loads((directory/'capture-manifest.json').read_text());events=capture['receipt']['events']
    iq=Path('/var/tmp/leo-modular-ds9-iq-v2' if index==0 else '/var/tmp/leo-three-iq-'+scan['session_id'])
    iq_result=verify_iq(directory/'server',json.loads((iq/'inventory.json').read_text()),events)
    staging=json.loads((directory/'staging/receipt.json').read_text())
    if staging['status']!='complete' or staging['visits']!=len(events) or staging['capture_digest']!=scan['manifest_sha256']:
        raise ValueError('device IQ verification incomplete')
    rows=json_lines(arm/'detector.stdout');summary=rows[-1]
    if len(rows)!=len(events)+1 or [r['sequence'] for r in rows[:-1]]!=list(range(len(events))):
        raise ValueError('missing detector arrivals')
    lossless=all(r['accepted'] and r['status']==0 for r in rows[:-1]) and summary['completed']==len(events) and summary['rejected']==summary['failed']==0
    if not lossless:raise ValueError('cannot evaluate full scan with rejected/failed detector calls')
    authority=[l.split('\t') for l in (directory/('prepared-reuse' if index==0 else 'prepared')/'authority.tsv').read_text().splitlines()]
    projection_exact=host_projection(arm,scan,authority,output)
    projected=project_paced(capture,rows,scan['manifest_sha256'],authority[0][13])
    sources=['\t'.join(SOURCE_HEADER)]+['\t'.join(map(str,p.source)) for p in projected]
    (output/'candidate-map.tsv').write_text('\n'.join(sources)+'\n')
    actual=list(csv.DictReader((arm/'observations.tsv').open(),delimiter='\t'))
    if len(projected)!=len(actual) or any(p.observation[0]!=r['candidate_id'] for p,r in zip(projected,actual)):
        raise ValueError('independent Python projection IDs differ')
    # Independent Python projection also checks scientific values, not just identities.
    python_max_ns=0;python_max_numeric=0.
    for p,r in zip(projected,actual):
        values=list(r.values()); expected=p.observation
        if any(str(expected[k])!=values[k] for k in (0,1,2,3,4)):
            raise ValueError('projection source/lane differs')
        python_max_ns=max(python_max_ns,*(abs(int(values[k])-expected[k]) for k in (6,7,8)))
        python_max_numeric=max(python_max_numeric,*(abs(float(values[k])-expected[k]) for k in (5,9,10,11,12)))
    projection_exact['python_identity_lane_cfo_score_exact']=python_max_numeric==0 and python_max_ns<=1
    projection_exact['python_maximum_utc_delta_ns']=python_max_ns
    # Reuse the pre-existing matching rule, preserving the historical comparison's meaning.
    sys.path.insert(0,str(ROOT/'reports/2026_09_30_arm_full_scan_comparison'))
    from plot_comparison import match_passing
    arm_points=candidate_points([r['candidates'] for r in rows[:-1]],events)
    host_calls=load_reference(directory/'native-host-glrt')
    if len(host_calls)!=len(events):raise ValueError('incomplete native host control')
    host_points=candidate_points(host_calls,events)
    server_points=[]
    for path in sorted((directory/'server/visits').glob('visit-*.json')):
        doc=json.loads(path.read_text());visit=doc['visit'];event=events[visit]
        for rx,cs in doc['candidates'].items():
            for c in cs:
                if c['fractional_status']!='complete':continue
                server_points.append(dict(visit=visit,time=(event['valid_start_counter']-events[0]['valid_start_counter'])/2500000,
                    rx=int(rx),rank=c['rank'],channel=event['target']['channel'],epoch=c['epoch'],
                    acquired_cfo=c['acquired_cfo_hz'],cfo=c['fractional_tracking_cfo_hz'],
                    margin=c['fractional_margin'],passing=c['passed_fractional_margin_gate']))
    glrt={}
    for label,points in [('native_host',host_points),('standard_server',server_points)]:
        matches=match_passing(arm_points,points)
        a=sum(p['passing'] for p in arm_points);b=sum(p['passing'] for p in points)
        glrt[label]={'arm_passing':a,'reference_passing':b,'one_to_one_matches':len(matches),
            'reference_recall':len(matches)/b if b else None,'arm_unmatched':a-len(matches),
            'rule':'Same visit/RX, circular integer epoch <=2 samples, acquired CFO <=10 kHz; one-to-one greedy'}
        save(output/(label+'-matches.json'),matches)
    glrt['native_host']['candidate_rows_bit_exact']=all(r['candidates']==h for r,h in zip(rows[:-1],host_calls))
    glrt['native_host']['rank_aligned_max_cfo_delta_hz']=max(abs(c[5]-h[5]) for r,hs in zip(rows[:-1],host_calls) for c,h in zip(r['candidates'],hs))
    glrt['native_host']['rank_aligned_max_margin_delta']=max(abs(c[8]-h[8]) for r,hs in zip(rows[:-1],host_calls) for c,h in zip(r['candidates'],hs))
    policy=json.loads((report/'comparison-policy.json').read_text())
    glrt['native_host']['numerical_parity']=native_glrt_parity([r['candidates'] for r in rows[:-1]],host_calls,policy)
    binaries={
        'seeds':ROOT/'reports/2026_09_30_arm_fast_tracks/grid/grid-trial-v3',
        'tracks':ROOT/'reports/2026_09_30_arm_curvature_tracks/hybrid-v1/artifacts/leo-curvature-tracks',
        'search':Path('/var/tmp/leo-three-position-host')}
    commands={
        'seeds':[binaries['seeds'],arm/'observations.tsv',151,8,512,8,4,16],
        'tracks':[binaries['tracks'],arm/'observations.tsv','--acceleration',250,'--seeds',output/'seeds.stdout'],
        'search':[binaries['search'],arm/'observations.tsv',arm/'graph.tsv',output/'tracks.stdout',directory/'native-orbit/selected.tle',
                  -60,10,43,38.5816,-121.4944,250,1,output/'associations.json']}
    host_times={}
    for name,command in commands.items():
        start=time.monotonic()
        with (output/(name+'.stdout')).open('x') as out,(output/(name+'.stderr')).open('x') as err:
            subprocess.run(list(map(str,command)),stdout=out,stderr=err,check=True,timeout=180)
        host_times[name]=time.monotonic()-start
    native_exact={name:digest(output/(name+'.stdout'))==digest(arm/'results'/(name+'.stdout')) for name in ('seeds','tracks')}
    native_exact['associations']=digest(output/'associations.json')==digest(arm/'results/associations.json')
    search=compare_search(json.loads((arm/'results/search.stdout').read_text()),json.loads((output/'search.stdout').read_text()),1e-9)
    sys.path.insert(0,str(ROOT/'reports/2026_09_30_arm_curvature_tracks/evaluation'))
    import compare_membership as m
    server=directory/'server-tracking'
    so=m.read_observations(server/'server-observations.tsv');ao=m.read_observations(arm/'observations.tsv')
    ss=m.read_sources(server/'server-candidate-map.tsv',so);ars=m.read_sources(output/'candidate-map.tsv',ao)
    refs=m.read_tracks(server/'server-tracks.tsv',so);tracks=m.read_tracks(arm/'results/tracks.stdout',ao)
    full=directory/'native-host-pipeline-v2'
    if json.loads((full/'receipt.json').read_text())['status']!='complete':
        raise ValueError('independent full native host pipeline incomplete')
    full_observations=m.read_observations(full/'observations.tsv')
    full_tracks=m.read_tracks(full/'tracks.stdout',full_observations)
    def memberships(bank):
        return [(t.lane,t.start_ns,t.end_ns,sorted((p.candidate,p.alias) for p in t.points)) for t in bank.values]
    full_search=compare_search(json.loads((arm/'results/search.stdout').read_text()),json.loads((full/'search.stdout').read_text()),1e-9)
    end_to_end={'observation_ids_times_lanes_cfos_exact':ao==full_observations,
        'support_graph_bytes_exact':digest(arm/'graph.tsv')==digest(full/'graph.tsv'),
        'track_memberships_exact':memberships(tracks)==memberships(full_tracks),
        'track_checkpoint_bytes_exact':digest(arm/'results/tracks.stdout')==digest(full/'tracks.stdout'),
        'associations_json_exact':json.loads((arm/'results/associations.json').read_text())==json.loads((full/'associations.json').read_text()),
        'search':full_search,'scope':'Independent raw IQ to final output on x86 native control; not the standard server algorithm'}
    settings=json.loads((ROOT/'reports/2026_09_30_arm_curvature_tracks/evaluation/thresholds.json').read_text())
    track_eval=m.compare(refs,tracks,so,ao,ss,ars,settings)
    if index==0 and not json.loads((directory/'historical-reference-identity.json').read_text())['reference_10_unchanged']:
        raise ValueError('historical exception no longer identifies the same segment')
    excluded={10} if index==0 else set()
    represented=set(track_eval['primary']['reference_segments_with_any_complete_output_indexes'])-excluded
    matched={p['reference_track_index'] for p in track_eval['primary']['matches']}-excluded
    eligible={t.index for t in refs.values}-excluded
    buckets={}
    for name,lo,hi in [('short',0,15),('medium',15,30),('long',30,float('inf'))]:
        ids={t.index for t in refs.values if lo<=(t.end_ns-t.start_ns)/1e9<hi}-excluded
        buckets[name]={'represented':len(ids&represented),'one_to_one':len(ids&matched),'total':len(ids)}
    track_eval['reviewed']={'represented':len(represented),'one_to_one':len(matched),'eligible':len(eligible),
        'excluded_reference_indexes':sorted(excluded),'duration_buckets':buckets,
        'additional_outputs':len(tracks.values)-len(track_eval['primary']['matches'])}
    save(output/'track-membership.json',track_eval)
    cpu={k.removesuffix('_ms')+'_s':sum(r.get(k,0) for r in rows[:-1])/1000
         for k in ('detector_cpu_ms','projection_cpu_ms','service_cpu_ms')}
    service={k.removesuffix('_ms')+'_s':sum(r.get(k,0) for r in rows[:-1])/1000
             for k in ('detector_ms','projection_ms','service_ms','io_ms')}
    timings={name:timing(arm/'results'/(name+'.stderr')) for name in ('seeds','tracks','search')}
    timings.update(detector=timing(arm/'detector.stderr'),downstream=timing(arm/'downstream.stderr'))
    position_wall=position_stage_wall([json.loads(l) for l in (arm/'results/search.stderr').read_text().splitlines() if l.startswith('{')],timings['search']['wall_s'])
    native_result=json.loads((arm/'results/search.stdout').read_text())
    published=json.loads((directory/'published-server-position.json').read_text())['priors'][0]
    result={'session':scan['session_id'],'iq':iq_result,'projection':projection_exact,'glrt':glrt,
        'native_controls':native_exact,'native_search':search,'native_end_to_end':end_to_end,'tracks':track_eval['reviewed'],
        'arm_track_count':len(tracks.values),'server_track_count':len(refs.values),
        'published_server_position':published['selected'],'arm_position':native_result['selected'],
        'position_search_complete':native_result['complete'],'position_stop_reason':native_result['stop_reason'],
        'timings':timings,'position_stage_wall_s':position_wall,'summed_thread_cpu_s':cpu,'summed_dwell_service_s':service,'host_control_wall_s':host_times,
        'queue':{**summary,'maximum_dwell_latency_ms':max(r['due_to_finish_ms'] for r in rows[:-1])},
        'input_sha256':{str(p):digest(p) for p in [arm/'detector.stdout',arm/'observations.tsv',arm/'graph.tsv',directory/'server/summary.json',directory/'staging/receipt.json']},
        'host_binary_sha256':{k:digest(p) for k,p in binaries.items()},
        'scope':'Physical recorded-IQ pipeline; distinct native/server algorithms and memberships; position is a budget-limited diagnostic'}
    result['native_stage_controls_passed']=glrt['native_host']['numerical_parity']['passed'] and all(projection_exact[k] for k in ('observations.tsv','graph.tsv','python_identity_lane_cfo_score_exact')) and all(native_exact.values()) and search['passed']
    save(output/'evaluation.json',result)
    save(output/'plot-points.json',{'arm':arm_points,'server':server_points})
    print(json.dumps({'session':scan['session_id'],'native_controls_passed':result['native_stage_controls_passed'],'glrt':glrt,'tracks':result['tracks']}),flush=True)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('report',type=Path)
    p.add_argument('--sequence',default='arm-sequence-v1');a=p.parse_args()
    selection=json.loads((a.report/'selection.json').read_text())['scans']
    execution=json.loads((a.report/a.sequence/'execution.json').read_text())
    if execution['exit_code']!=0 or execution['protocol_sha256']!=digest(a.report/a.sequence/'protocol.json'):
        raise ValueError('successful immutable ARM sequence required')
    results=[evaluate_scan(a.report,s,i,a.sequence) for i,s in enumerate(selection)]
    save(a.report/'stage-comparison.json',results)


if __name__=='__main__':main()
