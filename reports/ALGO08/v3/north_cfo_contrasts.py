"""Isolate signed CFO edits and additional support on one fixed North offer."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from time import perf_counter, process_time
from types import SimpleNamespace


HERE = Path(__file__).resolve().parent
PREVIOUS = Path('/dev/shm/leo-v3-north-cfo-final-03')
SOURCE_PIN = '22ea2a60534ebdd2e193c0577f9dc48cad26b882d2eda4c089b8f1b0d00f7ad1'
PACKET = 'sha256:83d1c79b8acb8dc1d8720999af9791264558b2ac43505b6312e535fe832b91d0'
ORDER = ('unrefined-full','refined-named-lanes')
PROTOCOL = HERE/'north-cfo-contrasts-protocol.md'


def named_lane_packet(parent, named):
    from leo.contracts.digests import canonical_digest
    from north_factor_swap import rebound

    a, b = parent['source'], named['source']
    for key in ('raw_recording_authority_digest','input_manifest_sha256','session_id'):
        if a[key] != b[key]:
            raise ValueError('Expected the same authenticated source for the named support diagnostic')
    rows, retained, removed = [], 0, 0
    for current, reference in zip(a['probes'],b['probes'],strict=True):
        if dict(current,candidates=[]) != dict(reference,candidates=[]):
            raise ValueError('Named support must join exact original stereo opportunities')
        if reference['candidates'] and not current['candidates']:
            raise ValueError('Expected the named support to be a subset of refined positive lanes')
        if reference['candidates']:
            rows.append(current)
            retained += len(current['candidates'])
        else:
            rows.append(dict(current,candidates=[]))
            removed += len(current['candidates'])
    identity = dict(schema_version=1,kind='offline_named_positive_lane_mask',deployable=False,
                    output_measurements='unchanged retained refined factors',
                    parent_native_sha256=canonical_digest(parent),
                    parent_detector_sha256=parent['provenance']['detector_sha256'],
                    named_support_native_sha256=canonical_digest(named))
    return rebound(parent,rows,identity), identity, dict(retained=retained,removed=removed)


def launch(root):
    from aperture_trial import RELEASE,read,write
    from dense_geographic_trial import host
    from empty_bootstrap import bind_native,checked
    from full_short_physical import environment
    from full_short_run import RECIPE_SHA
    from leo.contracts.digests import canonical_digest
    from leo.storage.fast_scan import immutable_json
    from north_interlaced_raw import RECEIVER_SHA
    from raw_cfo_north_score import MIXED_PIN,MIXED_ROOT
    from raw_cfo_north_trial import STOCK_PACKET,STOCK_ROOT,native_file,verified_packet
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(['findmnt','-no','FSTYPE','-T',root.parent],text=True).strip() != 'tmpfs':
        raise ValueError('Require fresh private tmpfs results')
    request = read(PREVIOUS/'binding.json')
    _,refined,receipt = verified_packet(PREVIOUS/'containing',request)
    if receipt['native_sha256'] != PACKET:
        raise ValueError('Expected the sealed refined full-roster transfer')
    mixed_data = checked(native_file(MIXED_ROOT),MIXED_PIN)
    mixed = json.loads(mixed_data)
    named = json.loads(checked(native_file(STOCK_ROOT/'stock'),STOCK_PACKET[7:]))
    for source,detector,pin in ((mixed,RECIPE_SHA,'sha256:'+MIXED_PIN),(named,RECEIVER_SHA,STOCK_PACKET)):
        bind_native(source,request['session'],request['inventory'],detector,expected=pin)
        if (source['source']['raw_recording_authority_digest'] != request['authority']
                or source['clock_anchor']['before']['realtime_ns'] != request['cutoff_utc_ns']):
            raise ValueError('The two same-site contrasts must use the identical recording and cutoff')
    projected, identity, counts = named_lane_packet(refined,named)
    if counts != dict(retained=456,removed=622):
        raise ValueError('The offline support ceiling must retain the original 456 named-positive factors')
    offer = PREVIOUS/'inside-offer.json'
    checked(offer,request['inside_offer_sha256'])
    for name,pin in request['library_sha256'].items():
        checked(Path(request['libraries'][name]),pin)
    root.mkdir()
    (root/'tmp').mkdir()
    (root/'fonts').mkdir()
    for font in (PREVIOUS/'fonts').glob('fontlist-*.json'):
        (root/'fonts'/font.name).write_bytes(font.read_bytes())
    ordinary = root/'unrefined-input.json'
    ordinary.write_bytes(mixed_data)
    restriction = root/'restricted-input.json'
    immutable_json(restriction,projected)
    jobs = {ORDER[0]:dict(packet=str(ordinary),native_sha256='sha256:'+MIXED_PIN,detector_sha256='sha256:'+RECIPE_SHA),
            ORDER[1]:dict(packet=str(restriction),native_sha256=canonical_digest(projected),
                          detector_sha256=projected['provenance']['detector_sha256'],synthetic=identity)}
    write(root/'binding.json',dict(request=request,offer=str(offer),mode_inputs=jobs,support_counts=counts,order=ORDER,
          reference_result_sha256=SOURCE_PIN,source_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
          protocol_sha256=sha256(PROTOCOL.read_bytes()).hexdigest(),machine=machine))
    env = environment(root)
    env.update(TMPDIR=str(root/'tmp'),XDG_CACHE_HOME=str(root/'tmp'))
    for mode in ORDER:
        command = ['/usr/bin/timeout','--kill-after=2s','90s',RELEASE/'venv/bin/python','-IB',__file__,'worker',root,mode]
        clock = measure(command,env,root/mode)
        write(root/f'{mode}-clock.json',dict(timing=clock,command=list(map(str,command))))


def worker(root,mode):
    import empty_bootstrap as staged
    import unified_short_bootstrap as entry
    from aperture_trial import read,write

    started = process_time(),perf_counter()
    _,spec,sources,publication,pins = staged.load_runtime()
    from cumulative_grid_projection import saved_inventory_port
    from leo.analysis.glrt_frequency_input import frequency_evidence
    from leo.contracts.algo08_region import Algo08Region
    from leo.contracts.digests import canonical_digest
    from raw_cfo_north_trial import PUBLICATION_FLAGS,native_file
    from short_graph_guard import prove

    job = read(root/'binding.json')
    request,source = job['request'],job['mode_inputs'][mode]
    native = json.loads(staged.checked(Path(source['packet']),source['native_sha256'][7:]))
    detector = source['detector_sha256'][7:]
    if (mode == ORDER[1] and canonical_digest(source['synthetic']) != source['detector_sha256']
            or native['source']['raw_recording_authority_digest'] != request['authority']
            or native['clock_anchor']['before']['realtime_ns'] != request['cutoff_utc_ns']):
        raise ValueError('The saved handoff changed epoch, synthetic identity or original authority')
    staged.bind_native(native,request['session'],request['inventory'],detector,expected=source['native_sha256'])
    offer = Path(job['offer'])
    staged.checked(offer,request['inside_offer_sha256'])
    target = root/mode
    libraries = {name:Path(path) for name,path in request['libraries'].items()
                 if name not in ('short_binary','cfo_refinement_library')}
    args = SimpleNamespace(recording=Path(request['recording']),archive=Path(request['archive']['root']),
          region=offer,output=target,**libraries,**{flag[2:].replace('-','_'):True for flag in PUBLICATION_FLAGS})
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
    if not ready or handoff.calls != 1 or native_file(target).read_bytes() != Path(source['packet']).read_bytes():
        raise ValueError('Expected one byte-identical saved handoff and no waveform access')
    write(target/'north-cfo-contrast.json',dict(input=source,receipt=receipt,layout=layout,graph=graph,png=png,graph_proof=proof,
         waveform_calls=0,handoffs=handoff.calls,pins=pins,solve=detail.get('solve'),named_finish=detail.get('named_survivor_finish'),
         complete_saved=dict(cpu_s=process_time()-started[0],elapsed_s=perf_counter()-started[1])))


if __name__ == '__main__':
    sys.path.insert(0,str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('launch','worker'))
    parser.add_argument('root',type=Path)
    parser.add_argument('mode',choices=ORDER,nargs='?')
    args = parser.parse_args()
    if args.operation == 'launch':
        launch(args.root)
    else:
        worker(args.root,args.mode)
