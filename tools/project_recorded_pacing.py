"""Project a fresh complete recorded-IQ checkpoint with explicit run provenance."""
import argparse
import json
from pathlib import Path

from leo.contracts.digests import canonical_digest
from leo.native_pipeline.paced_projection import project_paced,analysis_identity
from leo.native_pipeline.membership import OBSERVATION_HEADER,SOURCE_HEADER,read_observations,read_sources
from leo.native_pipeline.runner import digest,finite_json,write_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--capture',type=Path,required=True);p.add_argument('--report',type=Path,required=True)
    p.add_argument('--capture-digest',required=True)
    p.add_argument('output',type=Path);args=p.parse_args()
    capture=finite_json(args.capture);protocol=finite_json(args.report/'protocol.json')
    execution=finite_json(args.report/'execution.json')
    if execution['exit_code']!=0 or execution['output_sha256']!=digest(args.report/'output.jsonl'):
        raise ValueError('failed or altered execution checkpoint')
    if execution['protocol_sha256']!=digest(args.report/'protocol.json'):
        raise ValueError('execution protocol changed')
    rows=[json.loads(l) for l in (args.report/'output.jsonl').read_text().splitlines()]
    capture_digest=canonical_digest(capture)
    if capture_digest!=args.capture_digest:raise ValueError('capture digest differs')
    manifest=(args.report/'manifest.tsv').read_text().splitlines()
    events=capture['receipt']['events']
    if digest(args.report/'manifest.tsv')!=protocol['manifest_sha256'] or len(manifest)!=len(events):
        raise ValueError('replay manifest changed or incomplete')
    origin=events[0]['valid_end_counter_exclusive']
    for i,(line,event) in enumerate(zip(manifest,events)):
        fields=line.split('\t')
        if int(fields[0])!=i or int(fields[1])!=(event['valid_end_counter_exclusive']-origin)*400:
            raise ValueError('replay arrivals differ from capture')
    analysis_digest=analysis_identity(protocol['binary_sha256'])
    result=project_paced(capture,rows,capture_digest,analysis_digest)
    args.output.mkdir(parents=True,exist_ok=False)
    for name,header,attribute in [('observations.tsv',OBSERVATION_HEADER,'observation'),
                                   ('candidate-map.tsv',SOURCE_HEADER,'source')]:
        lines=['\t'.join(header)]+['\t'.join(map(str,getattr(r,attribute))) for r in result]
        (args.output/name).write_text('\n'.join(lines)+'\n')
    events=capture['receipt']['events'];support=[]
    for r in result:
        start=events[r.source[2]]['valid_start_counter']
        support.append({'candidate_id':r.observation[0],'source_start_counter':start+r.support.start,
            'source_end_counter':start+r.support.end,'factorial_support_moments_s':r.support.moments})
    write_json(args.output/'support.json',support)
    obs=read_observations(args.output/'observations.tsv');read_sources(args.output/'candidate-map.tsv',obs)
    receipt={'status':'complete','observations':len(result),'capture_digest':capture_digest,
             'analysis_digest':analysis_digest,'observation_sha256':digest(args.output/'observations.tsv'),
             'analysis_identity_method':'recorded-integer-glrt-config-v1',
             'execution_protocol_sha256':execution['protocol_sha256'],
             'execution_output_sha256':execution['output_sha256'],
             'source_map_sha256':digest(args.output/'candidate-map.tsv'),
             'support_sha256':digest(args.output/'support.json'),
             'scope':'Configuration-scoped identities with separate execution provenance; compare by source coordinates'}
    write_json(args.output/'receipt.json',receipt);print(json.dumps(receipt))


if __name__=='__main__':main()
