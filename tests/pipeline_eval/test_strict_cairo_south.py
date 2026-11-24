from pathlib import Path

import pytest

from reports.ALGO08.v3.strict_cairo_south import FLAGS, LIBRARIES, REPLACEMENTS, candidate_command, verify_map


def test_preserve_physical_flags_and_binaries_with_new_signed_assignment():
    supplied = ['timeout', '--kill-after=2s', '75s', 'python', '-IB', '/old/exact_named_raw.py']
    supplied.extend(FLAGS)
    for flag in REPLACEMENTS + LIBRARIES:
        supplied.extend((flag, 'prior-'+flag))
    request = dict(recording='/new/raw', archive=dict(root='/new/archive', snapshots_sha256='sha256:new'),
                   offers={'containing': '/new/offer', 'near-omitted': '/new/omit'})
    packed = dict(map='/new/map', map_sha256='sha256:map', codec='/new/codec')
    actual = candidate_command(supplied, request, packed, Path('/new/out'))
    assert all(flag in actual for flag in FLAGS)
    assert all(actual[actual.index(flag)+1] == 'prior-'+flag for flag in LIBRARIES)
    assert '/new/offer' in actual and '/new/omit' not in actual and '/new/out' in actual
    assert 'sha256:new' in actual and 'sha256:map' in actual
    with pytest.raises(ValueError, match='qualified physical'):
        candidate_command(supplied + ['--portable-orbit-index', '/unexpected'], request, packed, '/new/out')


def test_every_derivative_member_must_point_to_original_complete_readback():
    chunk = dict(chunk_index=0, window_count=5, uncompressed_bytes=20)
    row = dict(original=chunk.copy(), binding=dict(manifest_sha256='sha256:source', chunk_index=0,
               directory='member-0', seek_sha256='sha256:seek'), checked_derivative=dict(decoded_bytes=20, full_checks=5))
    entries = {('sha256:source', 0): ('member-0', 'sha256:seek')}
    verify_map(entries, [row], [chunk], 'source')
    with pytest.raises(ValueError, match='exactly'):
        verify_map({}, [row], [chunk], 'source')
    row['checked_derivative']['full_checks'] = 4
    with pytest.raises(ValueError, match='full readback'):
        verify_map(entries, [row], [chunk], 'source')
