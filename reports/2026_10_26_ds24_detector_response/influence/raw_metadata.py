"""Read only public source/manifest/index metadata. NEVER iterate IQ windows."""
import hashlib
import json
from pathlib import Path
import sys

from leo.contracts.multirate_window_recording import ShortWindowIndexV2
from leo.contracts.short_window_recording import ShortWindowIndexV1
from leo.storage.fast_scan import FastSegmentSource
from leo.storage.uri import confined_path


def sha(p):return 'sha256:'+hashlib.sha256(Path(p).read_bytes()).hexdigest()


def one(request):
    source=Path(request['source_input']['path'])
    if sha(source)!=request['source_input']['sha256']:raise ValueError('source input hash mismatch')
    data=json.loads(source.read_text());visit=request['probe']['visit_index'];prefix=0;chosen=None
    for entry in data['segments']:
        if prefix<=visit<prefix+entry['windows']:
            chosen=entry;local=visit-prefix;break
        prefix+=entry['windows']
    if chosen is None:raise ValueError('visit absent from explicit source segment inventory')
    port=FastSegmentSource(chosen,start_sequence=local,stop_sequence=local+1)
    reader=port.reader;manifest=reader.manifest
    chunk=next(c for c in manifest.chunks if c.first_sequence<=local<c.first_sequence+c.window_count)
    # This member reference comes from the verified public persisted contract.
    index_path=confined_path(reader.path,reader.path/chunk.index_relative_path,must_exist=True)
    payload=index_path.read_bytes()
    if len(payload)!=chunk.index_bytes or 'sha256:'+hashlib.sha256(payload).hexdigest()!=chunk.index_sha256:
        raise ValueError('declared index hash/size mismatch')
    typ=ShortWindowIndexV2 if manifest.schema_version==2 else ShortWindowIndexV1
    rows=[typ.model_validate_json(line) for line in payload.splitlines()]
    if len(rows)!=chunk.window_count:raise ValueError('index count mismatch')
    row=next(q for q in rows if q.sequence==local);a=row.acquisition;p=request['probe']
    if a['sample_start']!=p['window_start_counter'] or a['sample_end']-a['sample_start']!=p['duration_samples']:
        raise ValueError('native sample support mismatch')
    if a['global_visit']!=visit or row.sample_count!=p['duration_samples'] or p['receiver_id'] not in manifest.receiver_ids:
        raise ValueError('native visit/receiver mismatch')
    target=port.targets[row.target_id]
    if target['channel']!=p['channel'] or target['rf_center_hz']!=p['actual_rf_hz']:
        raise ValueError('raw RF target mismatch')
    return dict(status='metadata_ready_IQ_and_detector_parity_unverified',source_input=request['source_input'],
        segment=chosen,segment_manifest_sha256=reader.manifest_sha256,index_path=str(index_path),index_sha256=chunk.index_sha256,
        local_sequence=local,global_visit=visit,first_sequence_in_segment=prefix,index=row.model_dump(mode='json'),target=target,
        sample_rate_hz=manifest.sample_rate_hz,receiver_ids=list(manifest.receiver_ids),
        payload_reference=chunk.model_dump(mode='json'),payload_read=False,IQ_hash_newly_verified=False,
        public_read_command=f"FastSegmentSource(segment, start_sequence={local}, stop_sequence={local+1}).windows(); exhaust the iterator",
        binding_warning='The reader will verify the whole containing chunk during a later authorized IQ read, not just this selected window.')


def main():
    requests=json.load(sys.stdin);out=[]
    for r in requests:
        try:out.append(dict(request_id=r['request_id'],raw_authority=one(r)))
        except Exception as exc:out.append(dict(request_id=r['request_id'],raw_authority=dict(status='unavailable',error=repr(exc))))
    json.dump(out,sys.stdout)


if __name__=='__main__':main()
