"""Export a complete native target through the verified short-window reader."""
import argparse,hashlib,inspect
from pathlib import Path
import numpy as np
from debug_fast_graph_unassociated import read,write
from evaluate_ds22_merged_tracks import digest
from leo.contracts.digests import canonical_digest
from leo.storage.short_window import ShortWindowReader


def measurement_point(track,probe,candidate,k,receiver_id):
    """Only measurement information enters the local frequency-estimation plan."""
    return dict(observation_id=track['observation_ids'][k],component=track['key'],time_s=track['times'][k],
        visit_index=probe['visit_index'],receiver_id=receiver_id,sample_start=probe['valid_start_counter'],edge=probe['edge'],
        CFO_hz=candidate['fractional_tracking_cfo_hz'],epoch_sample=candidate['integer_epoch_sample']+candidate['fractional_epoch_offset_samples'],
        candidate_rank=candidate['candidate_rank'])


def run(args):
    args.output.mkdir(parents=True,exist_ok=False);panel=args.output/'panel';panel.mkdir()
    inventory=read(args.inventory);pr=read(args.trial/'protocol.json');target=pr['targets'][0]
    if len(pr['targets'])!=1:raise ValueError('one native target required')
    invpath=args.study/'all-large-track-recovery'/pr['job']['job_id']/'inventory.json';inv=read(invpath)
    root=Path(inv['job']['root'])/inv['job']['case'];doc=read(root/'tracking.json');source=doc['source'];track=read(root/'tracks.json')[target['track_index']]
    if canonical_digest(inventory)!=source['input_manifest_sha256']:raise ValueError('input inventory digest differs')
    if track['observation_ids']!=target['observation_ids'] or len(track['observation_ids'])>100:
        raise ValueError('complete native target and at most 100 points required')
    probes={digest(f"{source['session_id']}:{p['receiver_id']}:{p['valid_start_counter']}".encode()):p for p in source['probes']}
    selected={}
    for k,oid in enumerate(track['observation_ids']):
        p=probes[oid];eligible=[c for c in p['candidates'] if c['passed_fractional_margin_gate']]
        c=max(eligible,key=lambda c:(c['fractional_margin'],-c['candidate_rank']))
        if p['visit_index'] in selected:raise ValueError('duplicate target visit')
        selected[p['visit_index']]=measurement_point(track,p,c,k,p['receiver_id'])
    hashes=[];points=[];exported=[];manifests=[];count=0
    for entry in inventory['segments']:
        reader=ShortWindowReader(Path(entry['path']))
        if canonical_digest(reader.manifest.model_dump(mode='json'))!=entry['manifest_digest']:
            raise ValueError('recording manifest differs')
        if reader.manifest.sample_rate_hz!=source['sample_rate_hz']:raise ValueError('sample rate differs')
        manifests.append(dict(path=str(reader.path/'manifest.json'),sha256=hashlib.sha256((reader.path/'manifest.json').read_bytes()).hexdigest()))
        for w in reader.windows():
            a=w.index.acquisition;visit=a['global_visit']
            if visit!=count:raise ValueError('nonconsecutive source visit')
            count+=1;hashes.append(w.index.iq_sha256)
            if visit not in selected:continue
            point=selected[visit]
            if a['sample_start']!=point['sample_start']:raise ValueError('native sample counter differs')
            rx=reader.manifest.receiver_ids.index(point['receiver_id']);values=np.array(w.samples[:,rx,:],copy=True)
            if values.shape!=(round(source['sample_rate_hz']*.02),2):raise ValueError('unexpected window size')
            name=f'visit-{visit:06d}.npy'
            with (panel/name).open('xb') as f:np.save(f,values,allow_pickle=False)
            point=dict(point,iq_sha256=w.index.iq_sha256);points.append(point)
            exported.append(dict(point,array=name,array_sha256=hashlib.sha256((panel/name).read_bytes()).hexdigest()))
        print('verified windows',count,'exported',len(points),flush=True)
    if count!=inventory['window_count'] or len(points)!=len(selected):raise ValueError('incomplete source replay')
    authority=canonical_digest([source['input_manifest_sha256'],hashes])
    if authority!=source['raw_recording_authority_digest']:raise ValueError('raw authority differs from GLRT source')
    plan=dict(points=points,sample_rate_hz=source['sample_rate_hz'],window_samples=round(source['sample_rate_hz']*.02),
        input_manifest_digest=source['input_manifest_sha256'],workers=4,seconds_per_worker=600,
        methods=['fixed_epoch','joint_all','joint_odd','joint_even'],joint_starts=1,joint_iterations=16,
        frequency_radius_hz=800,scout_radius_hz=600,epoch_radius_samples=.75,code_rate_radius_ppm=40,
        selection='complete original native graph target; no point selection by residual',
        no_GPS_or_TLE_in_measurement_plan=True,odd_even_independently_fitted=True,
        odd_even_share_archived_full_window_nomination=True)
    write(args.output/'plan.json',plan)
    write(panel/'manifest.json',dict(points=exported,sample_rate_hz=source['sample_rate_hz'],raw_windows_read=count,
        plan_sha256=hashlib.sha256((args.output/'plan.json').read_bytes()).hexdigest(),raw_recording_authority_digest=authority,
        raw_authority_matches_tracking=True,recording_manifests=manifests,
        source_hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [args.inventory,args.trial/'protocol.json',invpath,root/'tracking.json',root/'tracks.json',Path(__file__),Path(inspect.getfile(ShortWindowReader))]},
        all_selected_windows_hash_verified=True,no_new_RF=True))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('study','trial','inventory','output'):p.add_argument('--'+name,type=Path,required=True)
    run(p.parse_args())
