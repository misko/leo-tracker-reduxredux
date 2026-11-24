"""Select one frozen DS30 recording and passively check its signed input extents."""

import argparse
import ctypes
from decimal import Decimal
from hashlib import sha256
import json
import mmap
import os
from pathlib import Path
from stat import S_ISREG
from statistics import median


LEDGER = Path(__file__).resolve().parent/'measurements/acquisition-throughput.json'
LEDGER_PIN = 'fc46925e68437054169e2a3008388493554baf5c92f495eb3beb9434c10e620a'
EXCLUDED = frozenset(('DS30-0008', 'DS30-0016', 'DS30-0057'))
CASE = 'DS30-0138'
PANEL = Path('/tmp/ds30-v2-stage-all-6cdbac')/CASE
PAIR_PIN = '4c6bf86681d3922f55420f4a4fb546514b99837a36d5c54c6410a666c3ebc2c3'
NATIVE = 'algo08-v2-283e28335929585eea5ea391d7d51228/detections.json'
SPEC = 'sha256:6cdbac1e8496bfeaf8f3eefb90c936c65829629cc42d04b4a9bab7c6e97cf50f'
ORIGINAL_ROOT = Path('/srv/bulk/leo/fast-scan-recordings')
PAGE = os.sysconf('SC_PAGE_SIZE')
LIBC = ctypes.CDLL(None, use_errno=True)
LIBC.mincore.argtypes = (ctypes.c_void_p, ctypes.c_size_t, ctypes.POINTER(ctypes.c_ubyte))
LIBC.mincore.restype = ctypes.c_int


def plan(rows):
    complete = [row for row in rows if row['stages'][0] > 0 and row['stages'][1] > 0]
    eligible = [(row['case'], row['windows'], int(row['compressed_MB'] * 1_000_000))
                for row in complete if row['case'] not in EXCLUDED]
    ordered_ids = [row['case'] for row in rows]
    if len(ordered_ids) != len(set(ordered_ids)):
        raise ValueError('Repeated recording in decision ledger')
    visit_median = median(row[1] for row in eligible)
    byte_median = median(row[2] for row in eligible)
    chosen = min(eligible, key=lambda row: (abs(row[1]-visit_median), abs(row[2]-byte_median), row[0]))
    case, issued, compressed = chosen
    row, = [r for r in rows if r['case'] == case]
    return dict(case=case, issued=issued, compressed_bytes=compressed, members=row['members'],
                inventory=row['inventory_sha256'], eligible=len(eligible), median_issued=visit_median,
                median_compressed_bytes=byte_median, excluded=sorted(EXCLUDED), ledger_count=len(rows),
                ledger_decision_order=ordered_ids, split_known_positive_count=len(complete),
                unsplit=[row['case'] for row in rows if row not in complete])


def tagged(payload):
    return 'sha256:'+sha256(payload).hexdigest()


def verified(payload, pin):
    if tagged(payload) != 'sha256:'+pin.removeprefix('sha256:'):
        raise ValueError('Saved bytes differ from their pinned digest')
    return json.loads(payload)


def sample(fd, byte_count):
    pages = (byte_count+PAGE-1)//PAGE
    status = (ctypes.c_ubyte * pages)()
    # MAP_PRIVATE gives the C address without dereferencing the mapped bytes.
    # No page is written, faulted for computation, copied, or advised here.
    with mmap.mmap(fd, byte_count, access=mmap.ACCESS_COPY) as mapping:
        start = ctypes.c_ubyte.from_buffer(mapping)
        try:
            if LIBC.mincore(ctypes.addressof(start), byte_count, status):
                error = ctypes.get_errno()
                raise OSError(error, os.strerror(error))
        finally:
            del start
    return pages, sum(status[page] & 1 for page in range(pages))


def inspect(path, expected=None, *, saved_json=False):
    """Only explicit JSON metadata files may be opened for sequential reads."""
    try:
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
        try:
            st = os.fstat(fd)
            if not S_ISREG(st.st_mode) or not st.st_size or (expected is not None and st.st_size != expected):
                raise ValueError(f'Unexpected file extent at {path}')
            pages, cached = sample(fd, st.st_size)
            info = dict(path=str(path), bytes=st.st_size, resident_pages=cached, file_pages=pages)
            if saved_json and cached == pages:
                if path.suffix != '.json' or st.st_size > 8*1024*1024:
                    raise ValueError(f'Refuse non-JSON or oversized metadata at {path}')
                data = os.pread(fd, st.st_size, 0)
                if len(data) != st.st_size:
                    raise ValueError(f'Metadata extent changed during observation at {path}')
                return info, data
            return info, None
        finally:
            os.close(fd)
    except OSError as error:
        return dict(path=str(path), error=str(error)), None


def summarize(records):
    return dict(files=len(records), observed=sum('bytes' in row for row in records),
                bytes=sum(row.get('bytes', 0) for row in records),
                resident_pages=sum(row.get('resident_pages', 0) for row in records),
                file_pages=sum(row.get('file_pages', 0) for row in records))


def observe(assignment):
    pair_data = (PANEL/'pair.json').read_bytes()
    pair = verified(pair_data, PAIR_PIN)
    named = pair['runs']['candidate']
    receipt = named['receipt']
    session = 'fast-'+assignment['inventory'][7:39]
    inventory_path = PANEL/'candidate/fast-scan-inputs'/f'{session}.json'
    inventory = verified(inventory_path.read_bytes(), assignment['inventory'])
    apparent = [(str(Path(s['path'])/'manifest.json'), s['manifest_digest']) for s in inventory['segments']]
    original = [(m['path'], m['sha256']) for m in pair['cache_observation']['manifests']]
    if (receipt['session_id'] != session or receipt['decision'] != 'complete'
            or receipt['window_count'] != assignment['issued'] or inventory['window_count'] != assignment['issued']
            or apparent != original or pair['candidate_specification_digest'] != SPEC):
        raise ValueError('Original ledger, saved inventory, and publication disagree')
    manifests, payloads, indexes = [], [], []
    cold_stubs = []
    for segment, (path, pin) in zip(inventory['segments'], original, strict=True):
        path = Path(path)
        if not path.is_relative_to(ORIGINAL_ROOT) or path.parent.parent != Path(pair['recording']):
            raise ValueError('Unexpected recording path in saved inventory')
        info, data = inspect(path, saved_json=True)
        manifests.append(dict(**info, sha256=pin, digest_checked=data is not None))
        if data is None:
            # A known v1 filename gives a candidate first member without a directory scan.
            # It cannot supply the authenticated extent unless the manifest is resident.
            file_info, _ = inspect(path.parent/'iq-000000.ci16.zst')
            cold_stubs.append(file_info)
            continue
        manifest = verified(data, pin)
        if manifest['window_count'] != segment['windows']:
            raise ValueError('Original manifest window count changed')
        for chunk in manifest['chunks']:
            for out, field, size in ((payloads, 'payload_relative_path', 'compressed_bytes'),
                                     (indexes, 'index_relative_path', 'index_bytes')):
                leaf = chunk[field]
                if Path(leaf).name != leaf:
                    raise ValueError('Only named segment-local extents may be observed')
                file_info, _ = inspect(path.parent/leaf, expected=chunk[size])
                out.append(file_info)
    work = PANEL/'candidate/fast-scan-automatic-work'
    terminal = verified((work/receipt['run_id']/'terminal.json').read_bytes(), receipt['terminal_sha256'])
    native, data = inspect(work/NATIVE, saved_json=True)
    if data is not None:
        verified(data, terminal['native_sha256'])
    return dict(assignment=assignment, frozen='0bcfb0cea', ledger_sha256=LEDGER_PIN,
                pair_sha256=PAIR_PIN, inventory_path=str(inventory_path), raw_authority=named['raw_authority'],
                admitted_historical=receipt['counts']['processed'], original_recording=pair['recording'],
                original_archive=pair['archive'], original_region=pair['region'],
                named_native=dict(**native, sha256=terminal['native_sha256'], digest_checked=data is not None),
                terminal_sha256=receipt['terminal_sha256'], manifests=manifests,
                member_pages=dict(payload=summarize(payloads), index=summarize(indexes)),
                manifest_unavailable_first_member_stubs=cold_stubs, payloads=payloads, indexes=indexes,
                waveform_reads=0, staging_bytes=0, raw_launches=0)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('plan', 'observe'))
    args = parser.parse_args()
    body = LEDGER.read_bytes()
    if tagged(body) != 'sha256:'+LEDGER_PIN:
        raise ValueError('Frozen size ledger differs')
    assignment = plan(json.loads(body, parse_float=Decimal)['rows'])
    if assignment['case'] != CASE or assignment['ledger_count'] != 55 or assignment['split_known_positive_count'] != 52:
        raise ValueError('Reproduction changed the frozen assignment')
    if args.action == 'observe':
        if os.geteuid() != 0:
            raise RuntimeError('Query as root to avoid Linux foreign-file residency masking')
        pressure = Path('/proc/pressure/io')
        before = pressure.read_text()
        result = observe(assignment)
        result.update(io_pressure_before=before, io_pressure_after=pressure.read_text(), page_bytes=PAGE)
    else:
        result = assignment
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == '__main__':
    main()
