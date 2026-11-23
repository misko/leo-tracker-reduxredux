"""Bind the held-anchor CFO route to the original staged South mirror pair."""

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from types import SimpleNamespace


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
INITIAL = Path('/dev/shm/leo-v3-south-cfo-route-eligibility01.json')
INITIAL_PIN = '80f4608196976f27f4e1ec0382ada800197b62a91747ec62f8dd18e1f57be24f'
MAX_MISSING = 128
CFO = 'fractional_tracking_cfo_hz'
FAILED = Path('/dev/shm/leo-v3-south-cfo-route-01')
FAILED_CLOCK = '072ef854cf38346335e7a93a224bed550251e6df5eb23bcbe33ab85f5a423cae'
FAILED_CACHE = '298c2c93bd0b4b4b3891b715fbabd5e25eb115957586f7e9bff9e4d744665742'
SMOKE = Path('/dev/shm/leo-v3-south-cfo-route-selector-smoke02.json')
SMOKE_PIN = '2df4f8a75ce4c5c21d792c4dab91d577f8c48dc6c75882eb7157d4f3a4888e00'


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


def admissible(cache, maximum_missing=0):
    rows = cache['payload'],cache['indexes']
    complete = all(not row['unavailable'] and row['members'] == row['observed_members'] == 19
                   and 0 < row['observed_file_pages'] and 0 <= row['cached_pages'] <= row['observed_file_pages']
                   for row in rows)
    return complete and sum(row['observed_file_pages']-row['cached_pages'] for row in rows) <= maximum_missing


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


def audit_selected(unfiltered, history, observed, chosen):
    from anchor_exposure import enroll
    from leo.contracts.digests import canonical_digest

    if chosen['route'] not in ('history','unfiltered'):
        raise ValueError('Unexpected held-cycle route')
    original, historical, output = (packet['source']['probes'] for packet in (unfiltered,history,observed))
    expected = historical if chosen['route'] == 'history' else original
    changed = []
    for before,after,entry in zip(expected,output,enroll(unfiltered),strict=True):
        if (dict(before,candidates=[]) != dict(after,candidates=[])
                or len(before['candidates']) != len(after['candidates'])):
            raise ValueError('The combined receiver changed a signed opportunity or the chosen support')
        for first,current in zip(before['candidates'],after['candidates'],strict=True):
            if dict(first,**{CFO:current[CFO]}) != current:
                raise ValueError('The selected receiver may change only fixed-epoch CFO')
            if first[CFO] != current[CFO]:
                if entry[4] != 'short':
                    raise ValueError('Never change the original full anchor CFO')
                changed.append([after['visit_index'],after['receiver_id'],first[CFO],current[CFO]])
    return dict(original_probe_sha256=canonical_digest(original), retained_probe_sha256=canonical_digest(output),
                changed=changed, selected=sum(len(row['candidates']) for row in output),
                measured=sum(len(row['candidates']) for row in original))


def verified_packet(root,request):
    from anchor_cycle_route import select_route
    from aperture_trial import read
    from empty_bootstrap import bind_native,checked
    from leo.contracts.digests import canonical_digest
    from raw_cfo_north_trial import native_file

    target = root/MODES[0]
    raw = read(target/'unified-short-bootstrap.json')
    route = raw['held_anchor_route']
    decision = root/'containing-held-cycle-refined.json'
    if read(decision) != route:
        raise ValueError('The held route must bind the actual sealed raw publication')
    packet = native_file(target)
    observed = json.loads(checked(packet,raw['native_sha256'][7:]))
    unfiltered,history = (json.loads(checked(Path(request['packets'][name]['file']),request['packets'][name]['native_sha256'][7:]))
                          for name in ('unfiltered','history'))
    if canonical_digest(select_route(unfiltered)) != canonical_digest(route['choice']):
        raise ValueError('The combined receiver must decide from the authenticated unrefined original')
    comparison = audit_selected(unfiltered,history,observed,route['choice'])
    selected_pin = raw['detector_recipe_sha256']
    if (route['pre_refinement_probes_sha256'] != comparison['original_probe_sha256']
            or route['selected_native_sha256'] != raw['native_sha256'] or route['selected_recipe_sha256'] != selected_pin
            or canonical_digest(raw['receiver_recipe']) != selected_pin or route['policy'] != raw['receiver_recipe']['held_cycle_before_cfo']
            or route['selected'] != comparison['selected'] or route['measured'] != comparison['measured']
            or raw['causal_cutoff_utc_ns'] != CUTOFF or raw['verified_handoffs'] != 1 or raw['raw_acquisitions'] != 1
            or observed['source']['raw_recording_authority_digest'] != AUTHORITY):
        raise ValueError('The paid raw receiver did not preserve its pre-refinement authority and exact selected support')
    bind_native(observed,request['session'],request['inventory'],selected_pin[7:],expected=raw['native_sha256'])
    return packet,observed,raw,comparison


def saved_worker(root):
    import empty_bootstrap as staged
    import unified_short_bootstrap as entry

    began = process_time(),perf_counter()
    _,spec,sources,publication,pins = staged.load_runtime()
    from aperture_trial import read,write
    from cumulative_grid_projection import saved_inventory_port
    from leo.analysis.glrt_frequency_input import frequency_evidence
    from leo.contracts.algo08_region import Algo08Region
    from raw_cfo_north_trial import PUBLICATION_FLAGS,native_file
    from short_graph_guard import prove

    request = read(root/'binding.json')
    seal = read(root/'raw-packet-seal.json')
    raw = json.loads(staged.checked(root/MODES[0]/'unified-short-bootstrap.json',seal['bootstrap_sha256']))
    packet = Path(seal['packet'])
    native = json.loads(staged.checked(packet,seal['native_sha256'][7:]))
    detector = seal['detector_sha256'][7:]
    staged.bind_native(native,request['session'],request['inventory'],detector,expected=raw['native_sha256'])
    target,offer = root/MODES[1],Path(request['offers'][MODES[1]])
    staged.checked(offer,request['offer_sha256'][MODES[1]])
    libraries = {name:Path(path) for name,path in request['libraries'].items()
                 if name not in ('short_binary','cfo_refinement_library')}
    args = SimpleNamespace(recording=RECORDING,archive=Path(ARCHIVE['root']),region=offer,output=target,
                           **libraries,**{flag[2:].replace('-','_'):True for flag in PUBLICATION_FLAGS})
    handoff = entry.Handoff(request['session'],request['inventory'],detector,native)
    layout,graph,png = {},{},{}
    assets = staged.RELEASE/'assets'
    with saved_inventory_port(request) as ready:
        reason = staged.empty_reason(native,frequency_evidence)
        proof = None if reason else prove(native,assets,use_time_support=True,use_curvature_extent=True)
        if reason is None and proof['proven']:
            reason = 'no_active_curvature'
        if reason:
            staged.check_inert_solver_assets(assets)
            receipt = entry.withhold(staged.staged_scanner(sources),args,Algo08Region.parse(read(offer)),assets,handoff,
                                     reason,graph_proof=proof)
            detail = {}
        else:
            receipt,detail = entry.publish_active(args,publication,spec,handoff,layout,graph_audit=graph,png_read_audit=png,
                         no_active_curvature_sha256=proof.get('curvature_extent',{}).get('native_sha256'))
    if not ready or handoff.calls != 1 or native_file(target).read_bytes() != packet.read_bytes():
        raise ValueError('Expected one identical selected refined packet and no waveform access')
    write(target/'saved-south-cfo-route.json',dict(receipt=receipt,layout=layout,graph=graph,png=png,graph_proof=proof,
        native_sha256=seal['native_sha256'],detector_recipe_sha256=seal['detector_sha256'],handoffs=handoff.calls,
        staged_inventory=True,waveform_calls=0,pins=pins,solve=detail.get('solve'),named_survivor_finish=detail.get('named_survivor_finish'),
        complete_saved=dict(cpu_s=process_time()-began[0],elapsed_s=perf_counter()-began[1])))


def recover(root):
    from aperture_trial import RELEASE,write
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from raw_cfo_north_trial import CURVATURE_FLAGS,PUBLICATION_FLAGS,checked_libraries
    from short_raw_diagnostic import measure

    machine = host()
    initial = json.loads(checked(INITIAL,INITIAL_PIN))
    failed = json.loads(checked(FAILED/'containing-clock.json',FAILED_CLOCK))['timing']
    warmed = json.loads(checked(FAILED/'cache-after.json',FAILED_CACHE))
    smoke = json.loads(checked(SMOKE,SMOKE_PIN))
    if (failed['exit_code'] != 1 or 'the first argument must be callable' not in failed['stderr_tail']
            or not admissible(warmed) or not smoke['verified'] or smoke['waveform_calls']
            or not smoke['synthetic_one_cfo_change'] or smoke['detail']['choice']['route'] != 'history'):
        raise ValueError('Expected the one paid import failure and the reviewed saved wrapper fix')
    request,chunks = assigned()
    for path in (str(root.parent),str(RECORDING),ARCHIVE['root'],request['saved_inventory']):
        if subprocess.check_output(['findmnt','-no','FSTYPE','-T',path],text=True).strip() != 'tmpfs':
            raise ValueError('Use only the originally staged tmpfs simulation')
    libraries,pins = checked_libraries()
    if os.sysconf('SC_PAGE_SIZE') * MAX_MISSING > 524288 or initial['request'] != request:
        raise ValueError('Staged fixture or prospective paging budget changed')
    root.mkdir()
    for name in ('tmp','fonts'):
        (root/name).mkdir()
    for font in (STAGING/'fonts').glob('fontlist-*.json'):
        (root/'fonts'/font.name).write_bytes(font.read_bytes())
    sources = ('south_cfo_route.py','held_cycle_refined.py','short_cfo_raw.py','unified_short_bootstrap.py',
               'held_anchor_route_publication.py','short_graph_guard.py','named_survivor_fit.py',PROTOCOL.name)
    request.update(libraries=libraries,library_sha256=pins,initial_eligibility_sha256=INITIAL_PIN,
          machine=machine,paging_limit_pages=0,paid_failed_clock_sha256=FAILED_CLOCK,paid_failed_clock=failed,
          saved_partial_class_smoke_sha256=SMOKE_PIN,source_sha256={n:sha256((HERE/n).read_bytes()).hexdigest() for n in sources})
    write(root/'binding.json',request)
    env = environment(root)
    env.update(TMPDIR=str(root/'tmp'),XDG_CACHE_HOME=str(root/'tmp'))
    python = RELEASE/'venv/bin/python'
    bootstrap = [python,'-IB',HERE/'short_cfo_raw.py','--cfo-refinement-library',libraries['cfo_refinement_library']]
    help_run = subprocess.run([*bootstrap,'--help'],env=env,capture_output=True,timeout=15,check=True)
    if b'--select-before-cfo' not in help_run.stdout:
        raise ValueError('The actual refinement CLI must expose the two-packet selector')
    target = root/MODES[0]
    flags = [part for name,path in libraries.items() if name != 'cfo_refinement_library'
             for part in ('--'+name.replace('_','-'),path)]
    command = ['/usr/bin/timeout','--kill-after=2s','90s',*bootstrap,'--recording',RECORDING,'--archive',ARCHIVE['root'],
               '--region',request['offers'][MODES[0]],'--output',target,*flags,*CURVATURE_FLAGS,*PUBLICATION_FLAGS,'--select-before-cfo']
    observed = residency(chunks)
    write(root/'cache-before.json',observed)
    if not admissible(observed):
        raise ValueError('The one corrected launch requires already fully resident South staging')
    clock = measure(command,env,target)
    write(root/'containing-clock.json',dict(timing=clock,command=list(map(str,command))))
    write(root/'cache-after.json',residency(chunks))
    if clock['exit_code']:
        raise RuntimeError(clock['stderr_tail'])
    packet,_,raw,comparison = verified_packet(root,request)
    write(root/'raw-packet-seal.json',dict(packet=str(packet),native_sha256=raw['native_sha256'],
          detector_sha256=raw['detector_recipe_sha256'],comparison=comparison,
          bootstrap_sha256=sha256((target/'unified-short-bootstrap.json').read_bytes()).hexdigest()))
    command = ['/usr/bin/timeout','--kill-after=2s','90s',python,'-IB',__file__,'saved',root]
    clock = measure(command,env,root/MODES[1])
    write(root/'mirror-clock.json',dict(timing=clock,command=list(map(str,command))))
    if clock['exit_code']:
        raise RuntimeError(clock['stderr_tail'])


if __name__ == '__main__':
    sys.path.insert(0,str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('eligibility','recover','saved'))
    parser.add_argument('output',type=Path)
    args = parser.parse_args()
    {'eligibility':eligibility,'recover':recover,'saved':saved_worker}[args.operation](args.output)
