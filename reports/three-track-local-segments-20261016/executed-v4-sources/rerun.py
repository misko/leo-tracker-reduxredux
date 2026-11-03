"""Bounded fresh cold replay using automatic short carrier bootstrap segments."""
import argparse
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'three-track-recovery-replay-20261016'))
from replay import verify_capsule
from rerun_cold import prepare
from local_segments import extract
from fast_bootstrap import bootstrap_position as batched_bootstrap
from leo.cli import shared_fast_position as pipeline
from leo.application import channel_group_discovery as discovery
from leo.application import shared_fast_position as application
from leo.contracts.digests import canonical_digest
from leo.operations.tle_archive import TleArchiveReader

RESEARCH_POLICY='research-cold24-local20-two-segments-batched-sample6-v1'


def replace_tracks(prepared, extracted):
    full=prepared['all'].observations
    ids=[tuple(full.window_ids[i] for i in segment['rows']) for segment in extracted['selected']]
    updated={};proof=[]
    for view,item in prepared.items():
        lookup={key:i for i,key in enumerate(item.observations.window_ids)}
        groups=tuple(tuple(lookup[key] for key in group) for group in ids if all(key in lookup for key in group))
        if {int(item.observations.receiver[g[0]]) for g in groups}!={0,1}:
            raise ValueError('Automatic bootstrap must retain support on both receivers')
        configuration=canonical_digest(extracted['configuration'])
        evidence=canonical_digest(dict(parent_evidence=item.evidence_sha256,
            policy='orbit-blind-local-quadratic-stratified-v1',configuration=configuration,
            bootstrap_tracks=groups))
        updated[view]=replace(item,bootstrap_tracks=groups,evidence_sha256=evidence,
                              trajectory_configuration_sha256=configuration)
        assert updated[view].observations is item.observations
        proof.append(dict(view=view,original_tracks=len(item.bootstrap_tracks),
            modified_tracks=len(groups),observations=len(item.observations.window_ids),
            unchanged_observation_object=True,parent_evidence_sha256=item.evidence_sha256,
            new_evidence_sha256=evidence,configuration_sha256=configuration,tracks=groups))
    return updated,proof


def run(args):
    verify_capsule()
    args.run=True
    snapshot,receipt=prepare(args)
    receipt.update(source_generation_policy=RESEARCH_POLICY,samples_per_track=6,
        source_sha256={name:hashlib.sha256((HERE/name).read_bytes()).hexdigest()
                       for name in ['local_segments.py','fast_bootstrap.py','rerun.py']})
    (args.output/'preparation-receipt.json').write_text(json.dumps(receipt,indent=2)+'\n')
    original_prepare=pipeline.prepare_views
    original_archive=pipeline.TleArchiveReader
    original_discovery_bootstrap=discovery.bootstrap_position
    original_source_bootstrap=application.bootstrap_position
    original_policy=application.POLICY
    original_cli_policy=pipeline.POLICY
    original_source_policy=application.SOURCE_POLICY
    def automatic_prepare(source):
        prepared,nodes=original_prepare(source)
        extracted=extract(prepared['all'].observations)
        updated,proof=replace_tracks(prepared,extracted)
        (args.output/'automatic-segments.json').write_text(json.dumps(extracted,indent=2)+'\n')
        (args.output/'bootstrap-replacement-receipt.json').write_text(json.dumps(proof,indent=2)+'\n')
        print(json.dumps(dict(event='automatic-bootstrap',views=[{k:v for k,v in row.items() if k!='tracks'} for row in proof])),flush=True)
        return updated,nodes

    class PinnedArchive(TleArchiveReader):
        def select_latest_before(self,cutoff_utc_ns,provider=None):
            if snapshot.collected_utc_ns>=cutoff_utc_ns or (provider is not None and provider!=snapshot.provider):
                raise ValueError('Pinned archived TLE must remain causal and match provider')
            return snapshot

    pipeline.prepare_views=automatic_prepare
    pipeline.TleArchiveReader=PinnedArchive
    def sparse_bootstrap(*bootstrap_args,**kwargs):
        return batched_bootstrap(*bootstrap_args,**dict(kwargs,samples_per_track=6))
    discovery.bootstrap_position=sparse_bootstrap
    application.bootstrap_position=sparse_bootstrap
    application.POLICY=dict(original_policy,source_generation_policy=RESEARCH_POLICY,
                            research_bootstrap_samples_per_track=6)
    pipeline.POLICY=application.POLICY
    application.SOURCE_POLICY=RESEARCH_POLICY
    try:
        result=pipeline.run(args.output/'training-input.json',args.output/'output',
                            maximum_seconds=480,tle_root=args.tle_root)
    finally:
        pipeline.prepare_views=original_prepare
        pipeline.TleArchiveReader=original_archive
        discovery.bootstrap_position=original_discovery_bootstrap
        application.bootstrap_position=original_source_bootstrap
        application.POLICY=original_policy
        pipeline.POLICY=original_cli_policy
        application.SOURCE_POLICY=original_source_policy
    print(json.dumps({key:result.get(key) for key in ['state','reason','elapsed_seconds','selection']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True);p.add_argument('--tle-root',type=Path,required=True)
    p.add_argument('--fold',choices=['early_to_late','late_to_early'],required=True)
    p.add_argument('--output',type=Path,required=True);run(p.parse_args())
