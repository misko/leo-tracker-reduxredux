"""Explicit track/support/orbit adapter; native code builds partitions and LOC1."""
import argparse
from pathlib import Path
import json
import subprocess

from leo.native_pipeline import membership as m
from leo.native_pipeline.location_input import graph_authority, overlap_audit
from leo.native_pipeline.runner import digest,finite_json,write_json


def build(projection, tracks, authority, binary, output, exclusive=False):
    receipt=finite_json(projection/'receipt.json')
    for name,key in [('observations.tsv','observation_sha256'),('support.json','support_sha256')]:
        if digest(projection/name)!=receipt[key]:raise ValueError('projection product hash mismatch')
    meta=finite_json(authority/'authority.json')
    if digest(authority/'authority.loc1')!=meta['files']['authority.loc1']:
        raise ValueError('orbit authority hash mismatch')
    obs=m.read_observations(projection/'observations.tsv')
    support=finite_json(projection/'support.json')
    parsed=m.read_tracks(tracks,obs)
    graph=graph_authority(obs,support,receipt,meta)
    output.mkdir(parents=True,exist_ok=False)
    (output/'graph.tsv').write_text(graph)
    result=subprocess.run([str(binary.resolve()),str((projection/'observations.tsv').resolve()),
        str((output/'graph.tsv').resolve()),str((authority/'authority.loc1').resolve()),
        str((output/'tracks.loc1').resolve()),'--tracks',str(tracks.resolve())]+(['--exclusive-candidates'] if exclusive else []),
        capture_output=True,text=True,check=True,timeout=60)
    (output/'native.stdout').write_text(result.stdout)
    (output/'native.stderr').write_text(result.stderr)
    audit=overlap_audit(parsed);write_json(output/'overlap.json',audit)
    selected_count=int(result.stdout.split()[0].split('=')[1])
    if exclusive:
        rows=(output/'tracks.loc1.members.tsv').read_text().splitlines()[1:]
        cids=[row.split('\t')[1] for row in rows]
        if len(set(cids))!=len(cids):raise ValueError('selected candidate memberships are not exclusive')
    report={'status':'complete','input_track_count':len(parsed.values),'track_count':selected_count,'capture_digest':receipt['capture_digest'],
        'start_utc_ns':meta['start_utc_ns'],'tle_digest':meta['tle_digest'],'native_binary_sha256':digest(binary),
        'source_track_sha256':digest(tracks),'location_input_sha256':digest(output/'tracks.loc1'),
        'input_reused_candidate_count':audit['reused_candidate_count'],'independent_evidence_claimed':False,
        'selection_policy':'exclusive-candidates-longest-v1' if exclusive else 'preserve-hypotheses'}
    write_json(output/'receipt.json',report)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('projection','tracks','authority','binary','output'):p.add_argument('--'+name,required=True,type=Path)
    p.add_argument('--exclusive-candidates',action='store_true')
    args=p.parse_args()
    print(json.dumps(build(args.projection,args.tracks,args.authority,args.binary,args.output,args.exclusive_candidates)))
