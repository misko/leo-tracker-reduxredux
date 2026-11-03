import json
import numpy as np
import pytest
import zstandard as zstd
from leo.contracts.digests import canonical_digest, canonical_json_bytes, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.native_adaptive_read import NativeAdaptiveReader


def fixture(tmp_path, mutate=None):
    chunks, events, total = [], [], 0
    arrays = []
    for k, visit in enumerate((0, 2)):
        values=(np.arange(32,dtype='<i2')+k*50).reshape(8,2,2)
        raw=values.tobytes();compressed=zstd.ZstdCompressor().compress(raw);name=f'chunk-{k}.zst'
        (tmp_path/name).write_bytes(compressed)
        chunks.append(dict(schema_version=12,chunk_index=k,first_visit_index=k,visit_count=1,sample_start=total,
            sample_count=8,relative_path=name,compressed_bytes=len(compressed),uncompressed_bytes=len(raw),
            compressed_sha256=sha256_digest(compressed),uncompressed_sha256=sha256_digest(raw)))
        events.append(dict(visit_index=visit,valid_start_counter=1000+visit*100,valid_end_counter_exclusive=1008+visit*100,
            target=dict(channel=1,edge='lower'),actual_lo_frequency_hz=959687500))
        total+=8;arrays.append(values)
    document=dict(schema_version=14,kind='starlink_adaptive_hop_iq',sample_format='ci16_le',sample_layout='sample_receiver_iq',
        session_id='unit-capture',total_sample_count=total,chunks=chunks,
        receipt=dict(plan=dict(geometry=dict(receiver_ids=[0,1],sample_rate_hz=2500000,lnb_lo_hz=9750000000)),
            events=events,retained_visit_indices=[0,2]))
    if mutate:mutate(document)
    payload=canonical_json_bytes(dict(manifest=document,sha256=canonical_digest(document)))
    p=tmp_path/'manifest.json';p.write_bytes(payload)
    return p,sha256_digest(payload),arrays


def test_verified_read_keeps_device_counter_gaps_and_retained_payload_coordinates(tmp_path):
    path,digest,arrays=fixture(tmp_path)
    reader=NativeAdaptiveReader(path,expected_file_sha256=digest)
    a,b=reader.read_visit(0),reader.read_visit(2)
    np.testing.assert_array_equal(a.samples,arrays[0]);np.testing.assert_array_equal(b.samples,arrays[1])
    assert b.valid_start_counter==1200 and b.payload_start_sample==8
    assert b.actual_rf_hz==10709687500 and reader.chunks_read==2
    assert not b.samples.flags.writeable
    with pytest.raises(KeyError):reader.read_visit(1)


def test_changed_manifest_chunk_or_decode_budget_fails_closed(tmp_path):
    path,digest,_=fixture(tmp_path)
    with pytest.raises(BundleCorruptionError):NativeAdaptiveReader(path,expected_file_sha256='sha256:'+'0'*64)
    reader=NativeAdaptiveReader(path,expected_file_sha256=digest,max_decoded_bytes=64)
    reader.read_visit(0)
    with pytest.raises(BundleCorruptionError,match='budget'):reader.read_visit(2)
    (tmp_path/'chunk-0.zst').write_bytes(b'changed')
    with pytest.raises(BundleCorruptionError,match='digest'):NativeAdaptiveReader(path,expected_file_sha256=digest).read_visit(0)


@pytest.mark.parametrize('mutation',[
    lambda d:d['chunks'][0].update(relative_path='../escape.zst'),
    lambda d:d['chunks'][0].update(visit_count=2),
    lambda d:d['receipt']['events'][0].update(valid_end_counter_exclusive=1009),
    lambda d:d['chunks'][1].update(sample_start=9),
    lambda d:d['chunks'][1].update(first_visit_index=2),
    lambda d:d.update(schema_version=15),
])
def test_unsupported_versions_escapes_and_inconsistent_authorities_are_rejected(tmp_path,mutation):
    path,digest,_=fixture(tmp_path,mutation)
    with pytest.raises(BundleCorruptionError):NativeAdaptiveReader(path,expected_file_sha256=digest)


def test_inner_manifest_digest_is_checked_even_if_outer_file_hash_matches(tmp_path):
    path,_,_=fixture(tmp_path)
    data=json.loads(path.read_text());data['manifest']['session_id']='tampered'
    payload=canonical_json_bytes(data);path.write_bytes(payload)
    with pytest.raises(BundleCorruptionError,match='envelope'):NativeAdaptiveReader(path,expected_file_sha256=sha256_digest(payload))
