"""Read-only, bounded access to native schema-14 adaptive-hop recordings."""

from __future__ import annotations

import json
import os
import stat
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import zstandard as zstd

from leo.contracts.digests import canonical_digest, sha256_digest
from leo.storage.errors import BundleCorruptionError
from leo.storage.uri import confined_path


@dataclass(frozen=True)
class NativeAdaptiveVisit:
    visit_index: int
    receiver_ids: tuple[int, ...]
    sample_rate_hz: int
    valid_start_counter: int
    valid_end_counter_exclusive: int
    payload_start_sample: int
    channel: int
    edge: str
    actual_rf_hz: int
    samples: np.ndarray
    chunk_uncompressed_sha256: str


def _read(path: Path, maximum: int) -> bytes:
    descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_size > maximum:
            raise BundleCorruptionError('native recording member exceeds its regular-file bound')
        with os.fdopen(descriptor, 'rb', closefd=False) as stream:
            return stream.read(maximum+1)
    finally:
        os.close(descriptor)


class NativeAdaptiveReader:
    """Only read retained visits through their authenticated manifest entries.

    Supports the single-visit schema-12 chunks used by schema-14 DS23 captures.
    Other layouts fail explicitly. There are no publication or mutation methods.
    """

    def __init__(self, manifest_path: Path, *, expected_file_sha256: str,
                 max_chunk_bytes: int = 64*1024**2, max_decoded_bytes: int = 8*1024**3):
        if max_chunk_bytes < 1 or max_decoded_bytes < 1:
            raise ValueError('positive explicit read budgets required')
        self.root = manifest_path.parent.resolve(strict=True)
        path = confined_path(self.root, manifest_path, must_exist=True)
        payload = _read(path, 16*1024**2)
        if sha256_digest(payload) != expected_file_sha256:
            raise BundleCorruptionError('native manifest file digest differs from supplied authority')
        try:
            envelope = json.loads(payload)
            document = envelope['manifest']
            if canonical_digest(document) != envelope['sha256']:
                raise ValueError('canonical envelope digest mismatch')
            if (document['schema_version'] != 14 or document['kind'] != 'starlink_adaptive_hop_iq'
                    or document['sample_format'] != 'ci16_le' or document['sample_layout'] != 'sample_receiver_iq'):
                raise ValueError('unsupported native adaptive recording version or layout')
            receipt = document['receipt']
            geometry = receipt['plan']['geometry']
            self.receiver_ids = tuple(geometry['receiver_ids'])
            self.sample_rate_hz = geometry['sample_rate_hz']
            self.lnb_lo_hz = geometry['lnb_lo_hz']
            self.session_id = document['session_id']
            if not self.receiver_ids or len(set(self.receiver_ids)) != len(self.receiver_ids) or self.sample_rate_hz <= 0:
                raise ValueError('invalid receiver/rate geometry')
            events = {e['visit_index']:e for e in receipt['events']}
            if len(events) != len(receipt['events']):
                raise ValueError('duplicate native visit event')
            retained = receipt['retained_visit_indices']
            if retained != sorted(set(retained)) or not set(retained) <= events.keys():
                raise ValueError('retained visit identities are not unique ordered events')
            self.chunks = {}
            total = 0
            last_counter = -1
            for number, chunk in enumerate(document['chunks']):
                # Chunk indices address the retained payload stream; the
                # receipt maps that ordinal back to the original device visit.
                ordinal = chunk['first_visit_index']
                if (chunk['schema_version'] != 12 or chunk['visit_count'] != 1 or chunk['chunk_index'] != number
                        or ordinal != number or number >= len(retained) or chunk['sample_start'] != total):
                    raise ValueError('requires consecutive single-visit schema-12 chunks')
                visit = retained[ordinal]
                event = events[visit]
                start, end = event['valid_start_counter'], event['valid_end_counter_exclusive']
                if (not isinstance(start, int) or not isinstance(end, int) or end <= start or start < last_counter
                        or end-start != chunk['sample_count']):
                    raise ValueError('visit counters differ from declared sample geometry')
                if chunk['uncompressed_bytes'] != chunk['sample_count']*len(self.receiver_ids)*4:
                    raise ValueError('native CI16 byte geometry differs from manifest')
                name = Path(chunk['relative_path'])
                if name.is_absolute() or '..' in name.parts:
                    raise ValueError('native chunk must be confined to its recording')
                if not 0 < chunk['uncompressed_bytes'] <= max_chunk_bytes or not 0 < chunk['compressed_bytes'] <= max_chunk_bytes:
                    raise ValueError('native chunk exceeds explicit per-chunk budget')
                self.chunks[visit] = (chunk, event)
                total += chunk['sample_count']
                last_counter = end
            if list(self.chunks) != retained or total != document['total_sample_count']:
                raise ValueError('native retained payload coverage differs from authenticated manifest')
        except (KeyError, TypeError, ValueError) as error:
            raise BundleCorruptionError(f'invalid native adaptive recording: {error}') from error
        self.manifest_sha256 = envelope['sha256']
        self.file_sha256 = expected_file_sha256
        self.max_chunk_bytes = max_chunk_bytes
        self.max_decoded_bytes = max_decoded_bytes
        self.decoded_bytes = 0
        self.chunks_read = 0

    def read_visit(self, visit_index: int) -> NativeAdaptiveVisit:
        if visit_index not in self.chunks:
            raise KeyError(f'visit {visit_index} was not retained')
        chunk, event = self.chunks[visit_index]
        if self.decoded_bytes+chunk['uncompressed_bytes'] > self.max_decoded_bytes:
            raise BundleCorruptionError('native adaptive total decode budget exceeded')
        path = confined_path(self.root, self.root/chunk['relative_path'], must_exist=True)
        compressed = _read(path, chunk['compressed_bytes'])
        if len(compressed) != chunk['compressed_bytes'] or sha256_digest(compressed) != chunk['compressed_sha256']:
            raise BundleCorruptionError('native adaptive compressed chunk size/digest changed')
        try:
            with zstd.ZstdDecompressor().stream_reader(compressed) as stream:
                raw = stream.read(chunk['uncompressed_bytes']+1)
        except zstd.ZstdError as error:
            raise BundleCorruptionError('invalid native adaptive compressed payload') from error
        if len(raw) != chunk['uncompressed_bytes'] or sha256_digest(raw) != chunk['uncompressed_sha256']:
            raise BundleCorruptionError('native adaptive decoded chunk size/digest changed')
        self.decoded_bytes += len(raw)
        self.chunks_read += 1
        samples = np.frombuffer(raw, dtype='<i2').reshape(chunk['sample_count'], len(self.receiver_ids), 2)
        samples.setflags(write=False)
        return NativeAdaptiveVisit(visit_index, self.receiver_ids, self.sample_rate_hz,
            event['valid_start_counter'], event['valid_end_counter_exclusive'], chunk['sample_start'],
            event['target']['channel'], event['target']['edge'], self.lnb_lo_hz+event['actual_lo_frequency_hz'],
            samples, chunk['uncompressed_sha256'])
