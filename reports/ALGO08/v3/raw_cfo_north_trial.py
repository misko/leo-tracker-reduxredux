"""Run one authenticated North waveform acquisition and one saved mirror offer."""

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
INVENTORY = 'sha256:985dfe1e0423b1106f5e205b9ccf1aec7f9d1e156d9262da19852521dd703d4b'
CUTOFF = 1794638359996253000
AUTHORITY = 'sha256:da1704254f8f5aa7ab83f5ff34a945075cb5144d367f720a264ecf81ea62703c'
STOCK_PACKET = 'sha256:1e35f931202a67e122526aaf394192582f46989e3fd89cf9690cb84a4b9b5c17'
MEMBERS, COMPRESSED_BYTES = 19, 1579423424
STOCK_ROOT = Path('/dev/shm/leo-v3-lane-raw-north-01')
PROTOCOL = HERE/'raw-cfo-north-protocol.md'
ORDER = ('containing','north-mirror-outside')
CURVATURE_FLAGS = ('--prove-empty-graph','--prove-graph-time-support','--prove-no-active-curvature')
PUBLICATION_FLAGS = ('--named-survivor-finish','--exact-graph-reuse','--reuse-verified-png-reads',
                     '--one-pass-web-png','--direct-residual-figures','--direct-orbit-figures')


def native_file(root):
    path, = root.glob('fast-scan-automatic-work/*/detections.json')
    return path


def checked_libraries():
    from combined_frontier_run import BLOCK_SHA
    from empty_bootstrap import checked
    from full_short_run import GEOGRAPHIC_SHA, SHORT_SHA, TRACK_SCORES_SHA
    from grid_feature_projection import LIBRARY_SHA
    from raw_0016_best_trial import PROJECTION, SHORT, STAGED
    from raw_cfo_0016_trial import FREEZE, LIBRARY
    from short_cfo_raw import EXTENSION_SHA256, FREEZE_SHA256, LIBRARY_SHA256, POLICY_SHA256, STEP

    pins = {'short_binary': (SHORT,SHORT_SHA), 'geographic_library': (STAGED/'geographic_library.so',GEOGRAPHIC_SHA),
            'regional_track_library': (STAGED/'regional_track_library.so',TRACK_SCORES_SHA),
            'frontier_block_library': (STAGED/'frontier_block_library.so',BLOCK_SHA),
            'grid_feature_projection_library': (PROJECTION,LIBRARY_SHA), 'cfo_refinement_library': (LIBRARY,LIBRARY_SHA256)}
    freeze = json.loads(checked(FREEZE,FREEZE_SHA256))
    if (freeze['driver_sha256'], freeze['extension_sha256'], freeze['step']) != (POLICY_SHA256,EXTENSION_SHA256,STEP):
        raise ValueError('Refinement must use the unchanged frozen waveform policy')
    for path, pin in pins.values():
        checked(path,pin)
    return {name:str(path) for name,(path,_) in pins.items()}, {name:pin for name,(_,pin) in pins.items()}


def workload(root):
    from empty_bootstrap import bind_native, checked
    from leo.storage.fast_scan import FastScanStore
    from north_combined import assignments
    from north_interlaced_raw import MANIFEST_SHA, OFFER_SHA, RECEIVER_SHA

    pair, omissions = assignments()
    recording = Path(pair['recording'])
    manifest = recording/'manifest.json'
    info = json.loads(checked(manifest,MANIFEST_SHA))
    chunks = info['chunks']
    if len(chunks) != MEMBERS or sum(chunk['compressed_bytes'] for chunk in chunks) != COMPRESSED_BYTES:
        raise ValueError('Expected exactly the existing 19 staged North members')
    session, inventory, index = FastScanStore(root).inventory(recording,verify_windows=False)
    pins = [(Path(row['path'])/'manifest.json',row['manifest_digest']) for row in index['segments']]
    if inventory != INVENTORY or index['window_count'] != 1200 or pins != [(manifest,'sha256:'+MANIFEST_SHA)]:
        raise ValueError('The exact North signed inventory changed')
    named_inventory = STOCK_ROOT/'stock/fast-scan-inputs'/(session+'.json')
    checked(named_inventory, INVENTORY[7:])
    named = json.loads(checked(native_file(STOCK_ROOT/'stock'),STOCK_PACKET[7:]))
    bind_native(named,session,inventory,RECEIVER_SHA,expected=STOCK_PACKET)
    if (pair['runs']['candidate']['raw_authority'] != AUTHORITY
            or named['source']['raw_recording_authority_digest'] != AUTHORITY
            or named['clock_anchor']['before']['realtime_ns'] != CUTOFF
            or omissions['native_sha256'] != STOCK_PACKET):
        raise ValueError('The two original v3 outputs must be on the assigned causal North packet')
    return dict(recording=str(recording),session=session,inventory=inventory,issued=1200, authority=AUTHORITY,
                archive=pair['archive'],cutoff_utc_ns=CUTOFF,saved_inventory=str(named_inventory),
                compressed_bytes=COMPRESSED_BYTES,decoded_bytes=sum(chunk['uncompressed_bytes'] for chunk in chunks),
                manifests=[dict(path=str(path),digest=pin) for path,pin in pins],
                inside_offer=str(pair['region']),inside_offer_sha256=OFFER_SHA,
                mirror_offer=omissions['results'][ORDER[1]]['offer']), pins


def verified_packet(raw, request):
    from empty_bootstrap import bind_native, checked
    from full_short_run import RECIPE_SHA, checked_recipe
    from leo.contracts.digests import canonical_digest
    from short_cfo_raw import recipe

    receipt = json.loads((raw/'unified-short-bootstrap.json').read_bytes())
    expected = recipe(checked_recipe(),RECIPE_SHA)
    detector = canonical_digest(expected)
    packet = native_file(raw)
    native = json.loads(checked(packet, receipt['native_sha256'][7:]))
    bind_native(native,request['session'],request['inventory'],detector[7:],expected=receipt['native_sha256'])
    if (receipt['receiver_recipe'] != expected or receipt['detector_recipe_sha256'] != detector
            or receipt['raw_acquisitions'] != 1 or receipt['verified_handoffs'] != 1
            or receipt['causal_cutoff_utc_ns'] != request['cutoff_utc_ns']
            or native['source']['raw_recording_authority_digest'] != request['authority']):
        raise ValueError('The signed refinement must bind the genuine raw handoff and exact tested policy')
    return packet, native, receipt


def saved_worker(root):
    import empty_bootstrap as staged
    import unified_short_bootstrap as entry
    from time import process_time

    started = process_time(), perf_counter()
    _, specification, sources, publication, pins = staged.load_runtime()
    from aperture_trial import read, write
    from cumulative_grid_projection import saved_inventory_port
    from leo.analysis.glrt_frequency_input import frequency_evidence
    from leo.contracts.algo08_region import Algo08Region
    from short_graph_guard import prove

    request = read(root/'binding.json')
    packet, native, raw = verified_packet(root/ORDER[0], request)
    sealed = read(root/'raw-packet-seal.json')
    if sealed['packet'] != str(packet) or sealed['native_sha256'] != raw['native_sha256']:
        raise ValueError('Changed raw packet at the saved mirror handoff')
    target = root/ORDER[1]
    offer = root/'mirror-offer.json'
    staged.checked(offer,request['offer_sha256'][ORDER[1]])
    libraries = {name:Path(path) for name,path in request['libraries'].items()
                 if name not in ('short_binary','cfo_refinement_library')}
    args = SimpleNamespace(recording=Path(request['recording']),archive=Path(request['archive']['root']),
                           region=offer,output=target,**libraries,**{flag[2:].replace('-','_'):True for flag in PUBLICATION_FLAGS})
    layout, graph, png = {}, {}, {}
    handoff = entry.Handoff(request['session'], request['inventory'], raw['detector_recipe_sha256'][7:], native)
    assets = staged.RELEASE/'assets'
    with saved_inventory_port(request) as inventory_staged:
        reason = staged.empty_reason(native,frequency_evidence)
        proof = None if reason is not None else prove(native,assets,use_time_support=True,use_curvature_extent=True)
        if reason is None and proof['proven']:
            reason = 'no_active_curvature'
        if reason is not None:
            staged.check_inert_solver_assets(assets)
            scan = staged.staged_scanner(sources)
            receipt = entry.withhold(scan,args,Algo08Region.parse(read(offer)),assets,handoff,reason,graph_proof=proof)
            detail = {}
        else:
            receipt, detail = entry.publish_active(args,publication,specification,handoff,layout,graph_audit=graph,png_read_audit=png,
                 no_active_curvature_sha256=proof.get('curvature_extent',{}).get('native_sha256'))
    if not inventory_staged or handoff.calls != 1 or native_file(target).read_bytes() != packet.read_bytes():
        raise ValueError('The mirror must reuse the exactly authenticated acquisition once')
    write(target/'saved-refined-north.json',dict(receipt=receipt,graph=graph,png=png,layout=layout,graph_proof=proof,
          native_sha256=raw['native_sha256'],detector_recipe_sha256=raw['detector_recipe_sha256'],
          staged_inventory=True,waveform_calls=0,handoffs=handoff.calls,pins=pins,solve=detail.get('solve'),
          named_survivor_finish=detail.get('named_survivor_finish'),
          complete_saved_s=dict(cpu_s=process_time()-started[0],elapsed_s=perf_counter()-started[1])))


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import CACHE_LIB, CACHE_SHA, environment
    from leo.storage.fast_scan import FastScanStore
    from short_raw_diagnostic import measure, require_warm
    from tools.pipeline_eval.qualification.cache_residency import bound_snapshot, load_query

    machine = host()
    request, manifests = workload(root)
    libraries, pins = checked_libraries()
    tmpfs = (root.parent,request['recording'],request['archive']['root'],request['saved_inventory'])
    if any(subprocess.check_output(['findmnt','-no','FSTYPE','-T',p],text=True).strip() != 'tmpfs' for p in tmpfs):
        raise ValueError('The original synthetic site or output is outside the staged tmpfs')
    checked(CACHE_LIB, CACHE_SHA)
    query = load_query(CACHE_LIB)
    store, recording = FastScanStore(root), Path(request['recording'])

    def cache():
        result = bound_snapshot(store,recording,manifests,os.sysconf('SC_PAGE_SIZE'),query)
        if result['members'] != MEMBERS:
            raise ValueError('Expected exactly 19 original staged compressed members')
        require_warm(result)
        return result

    root.mkdir()
    for name in ('tmp','fonts'):
        (root/name).mkdir()
    inside, mirror = root/'inside-offer.json', root/'mirror-offer.json'
    inside.write_bytes(checked(Path(request['inside_offer']),request['inside_offer_sha256']))
    write(mirror,request['mirror_offer'])
    source_names = ('raw_cfo_north_trial.py','short_cfo_raw.py','unified_short_bootstrap.py','short_graph_guard.py',
                    'named_survivor_fit.py','isolated_salvage.py','cumulative_grid_projection.py',PROTOCOL.name)
    request.update(libraries=libraries,library_sha256=pins,order=ORDER,machine=machine,
         offer_sha256={name:sha256(path.read_bytes()).hexdigest() for name,path in zip(ORDER,(inside,mirror),strict=True)},
         source_sha256={name:sha256((HERE/name).read_bytes()).hexdigest() for name in source_names})
    write(root/'binding.json',request)
    env = environment(root)
    env.update(TMPDIR=str(root/'tmp'),XDG_CACHE_HOME=str(root/'tmp'))
    python = RELEASE/'venv/bin/python'
    subprocess.run([python,'-Bc',"from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env,check=True,timeout=25)
    bootstrap = [python,'-IB',HERE/'short_cfo_raw.py','--cfo-refinement-library',libraries['cfo_refinement_library']]
    help_run = subprocess.run([*bootstrap,'--help'],env=env,capture_output=True,timeout=15,check=True)
    if b'--prove-no-active-curvature' not in help_run.stdout or b'--named-survivor-finish' not in help_run.stdout:
        raise ValueError('The genuine raw bootstrap does not expose the enrolled options')
    target = root/ORDER[0]
    flags = [part for name,path in libraries.items() if name != 'cfo_refinement_library'
             for part in ('--'+name.replace('_','-'),path)]
    command = ['/usr/bin/timeout','--kill-after=2s','90s',*bootstrap,'--recording',recording,'--region',inside,
               '--archive',request['archive']['root'],'--output',target,*flags,*CURVATURE_FLAGS,*PUBLICATION_FLAGS]
    write(root/'cache-before.json',cache())
    clock = measure(command,env,target)
    write(root/'containing-clock.json',dict(timing=clock,command=list(map(str,command))))
    write(root/'cache-after.json',cache())
    if clock['exit_code']:
        raise RuntimeError(clock['stderr_tail'])
    packet, _, raw = verified_packet(target,request)
    write(root/'raw-packet-seal.json',dict(packet=str(packet),native_sha256=raw['native_sha256'],
          bootstrap_sha256=sha256((target/'unified-short-bootstrap.json').read_bytes()).hexdigest()))
    command = ['/usr/bin/timeout','--kill-after=2s','90s',python,'-IB',__file__,'saved',root]
    clock = measure(command,env,root/ORDER[1])
    write(root/'mirror-clock.json',dict(timing=clock,command=list(map(str,command))))
    if clock['exit_code']:
        raise RuntimeError(clock['stderr_tail'])


if __name__ == '__main__':
    sys.path.insert(0,str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('launch','saved'))
    parser.add_argument('root',type=Path)
    args = parser.parse_args()
    {'launch':launch,'saved':saved_worker}[args.operation](args.root)
