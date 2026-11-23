"""Bind the held-anchor CFO route to the original staged South mirror pair."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
RECORDING = Path('/tmp/leo-regional-qZJKBw4W/public/6bd1f26bfa0bedfcf3f100f8')
ARCHIVE = dict(root='/tmp/leo-regional-qZJKBw4W/public/tle',
    snapshots_sha256='sha256:7aa06cab0502bcac70645a41a219bb6d53f1077f329e6f7ed79eb59a8794feec')
STAGING = Path('/dev/shm/leo-isolated-south-run01')
MANIFEST = 'd0ae1fee11210fff03da39c2f8ea2bbd1715cfa2bf78622d70e5977127b3eee2'
UNFILTERED = (Path('/dev/shm/leo-past-anchor-held-south'), 'a10693d167757124a036cfcd63e90966760e52b755f4bb834605ccaf74426d2e')
HISTORY = (Path('/var/tmp/leo-causal-weak-south-nov23/south-inside'), 'c25b319f17ea5553d63d02d85510117b39f528d9822fc93232159245a45ad904')
NAMED = (Path('/dev/shm/leo-v3-named-south-transfer-01/containing'), '26e4ce9c24e81761e4d92cf05e29474e4ced9ba4effdffff89b817c0ea9f9ce3')
INVENTORY = 'sha256:d5faad1ea8ba6a2df7dea75db1f9df27efb374f4671b5ae3df200e595d84fa4c'
CUTOFF = 1794638719996253000
AUTHORITY = 'sha256:60af66f445d50ba72764d7a1069dd90bbb6741b805c65541e300cf1040a4adc5'
COMPRESSED, DECODED = 1574298988, 1920000000
MODES = ('containing','near-omitted')
OFFER_PINS = {'containing':'ffac3462e68593ee675261f423e9e8c4543e734f6feff891144bb4c645c1a6d2',
              'near-omitted':'0c89bd52594b706b2772fbcf6ea627065eeb3d94eb6266f35de09ebb6b7a5d2a'}
PROTOCOL = HERE/'south-cfo-route-protocol.md'


def assigned():
    from aperture_trial import archive_identity
    from empty_bootstrap import bind_native, checked
    from full_short_run import RECIPE_SHA
    from isolated_salvage_south import DETECTOR, NEAR_SHA, ARCHIVED_NEAR, ORIGINAL, PAIR_SHA
    from leo.contracts.algo08_region import Algo08Region
    from leo.storage.fast_scan import FastScanStore
    from raw_cfo_north_trial import native_file

    named_pair = json.loads(checked(ORIGINAL/'pair.json',PAIR_SHA))
    named_mirror = json.loads(checked(ARCHIVED_NEAR,NEAR_SHA))
    expected = named_pair['runs']['candidate']
    if (named_pair['recording'] != str(RECORDING) or archive_identity(Path(ARCHIVE['root'])) != ARCHIVE
            or named_pair['archive'] != ARCHIVE or named_mirror['archive'] != ARCHIVE
            or named_mirror['pair_sha256'] != PAIR_SHA or named_mirror['native_sha256'] != 'sha256:'+NAMED[1]
            or expected['raw_authority'] != AUTHORITY):
        raise ValueError('The original South named comparators must share input, archive and receiver')
    offers = {mode:STAGING/f'{mode}-offer.json' for mode in MODES}
    docs = {mode:Algo08Region.parse(json.loads(checked(path,OFFER_PINS[mode]))).document() for mode,path in offers.items()}
    if docs['containing'] != expected['receipt']['region'] or docs['near-omitted'] != named_mirror['results']['south-mirror-outside']['offer']:
        raise ValueError('Expected exactly the original South offered squares')
    manifest_path = RECORDING/'manifest.json'
    manifest = json.loads(checked(manifest_path,MANIFEST))
    chunks = manifest['chunks']
    if (len(chunks) != 19 or manifest['window_count'] != 1200 or sum(c['compressed_bytes'] for c in chunks) != COMPRESSED
            or sum(c['uncompressed_bytes'] for c in chunks) != DECODED):
        raise ValueError('The 19 original signed staged items or visits changed')
    session, inventory, original = FastScanStore(Path('/dev/shm')).inventory(RECORDING,verify_windows=False)
    pin = (manifest_path,'sha256:'+MANIFEST)
    if (inventory != INVENTORY or original['window_count'] != 1200 or
            tuple((Path(row['path'])/'manifest.json',row['manifest_digest']) for row in original['segments']) != (pin,)):
        raise ValueError('Original signed South inventory changed')
    saved_inventory = NAMED[0]/'fast-scan-inputs'/(session+'.json')
    checked(saved_inventory,INVENTORY[7:])
    packets = {}
    for label,(root,digest),detector in (('named',NAMED,DETECTOR),('unfiltered',UNFILTERED,RECIPE_SHA),('history',HISTORY,None)):
        path = native_file(root)
        native = json.loads(checked(path,digest))
        detector = detector or native['provenance']['detector_sha256'][7:]
        bind_native(native,session,inventory,detector,expected='sha256:'+digest)
        if (native['source']['raw_recording_authority_digest'] != AUTHORITY
                or native['clock_anchor']['before']['realtime_ns'] != CUTOFF or native['provenance']['processed_windows'] != 1200):
            raise ValueError('South reference acquisition or cutoff changed')
        packets[label] = dict(file=str(path),native_sha256='sha256:'+digest,detector_sha256='sha256:'+detector)
    return dict(recording=str(RECORDING),archive=ARCHIVE,authority=AUTHORITY,cutoff_utc_ns=CUTOFF,session=session,
         inventory=INVENTORY,saved_inventory=str(saved_inventory),offers={m:str(p) for m,p in offers.items()},
         offer_sha256=OFFER_PINS,named_pin=PAIR_SHA,near_pin=NEAR_SHA,packets=packets,compressed_bytes=COMPRESSED,
         decoded_bytes=DECODED,issued=1200,manifest_sha256=MANIFEST), chunks


def residency(chunks):
    from empty_bootstrap import checked
    from full_short_physical import CACHE_LIB, CACHE_SHA
    from leo.storage.fast_scan import FastScanStore
    from tools.pipeline_eval.qualification.cache_residency import bound_snapshot, cache_snapshot, load_query

    checked(CACHE_LIB,CACHE_SHA)
    query = load_query(CACHE_LIB)
    size = os.sysconf('SC_PAGE_SIZE')
    pins = ((RECORDING/'manifest.json','sha256:'+MANIFEST),)
    payload = bound_snapshot(FastScanStore(Path('/dev/shm')),RECORDING,pins,size,query)
    index = cache_snapshot([(RECORDING,c['index_relative_path'],c['index_bytes']) for c in chunks],size,query)
    return dict(payload=payload,indexes=index)


def admissible(cache):
    return all(not row['unavailable'] and row['members'] == row['observed_members'] == 19
               and row['observed_file_pages'] and row['cached_pages'] == row['observed_file_pages']
               for row in (cache['payload'],cache['indexes']))


def eligibility(output):
    from aperture_trial import write
    from dense_geographic_trial import host

    machine = host()
    request,chunks = assigned()
    filesystems = {path:subprocess.check_output(['findmnt','-no','FSTYPE','-T',path],text=True).strip()
                   for path in (str(output.parent),str(RECORDING),ARCHIVE['root'],request['saved_inventory'])}
    cache = residency(chunks)
    record = dict(request=request,cache=cache,eligible=admissible(cache) and set(filesystems.values()) == {'tmpfs'},
                  filesystems=filesystems,owner=os.geteuid(),machine=machine,
                  protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest(),adapter_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    write(output,record)
    return record


if __name__ == '__main__':
    sys.path.insert(0,str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output',type=Path)
    eligibility(parser.parse_args().output)
