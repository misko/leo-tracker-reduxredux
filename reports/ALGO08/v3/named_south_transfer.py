"""One saved comparison of the portable named finish on the two South offers."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
PREVIOUS = Path('/dev/shm/leo-isolated-south-run01')
REQUESTS = {
    'containing': '975c8b3bf5c6c30a358eb974772cd00e917a9e98fc998bfe9a8fcfad22d48f91',
    'near-omitted': '5920a50abc8aec8956eb2c96b16b21702e2b689000f4d1d4bb2919817c7b6b3d',
}
WARM_SHA = '00a335f886c6139ab4951cf69b4fd4d829ba2eb9ab181ee07bfae2d48b422c4b'
FONT_SHA = '07189bbdc3694211155db6c4c6f677b7de06867976a2c4e2d8a57c228cb7688b'
PROTOCOL = HERE / 'named-south-transfer-protocol.md'


def bindings():
    from aperture_trial import archive_identity
    from empty_bootstrap import bind_native, checked
    from isolated_salvage_south import DETECTOR, INVENTORY_SHA, LIBRARIES, NATIVE_SHA, ORIGINAL
    from named_constrained_research import inventory_binding

    requests = {}
    for mode, pin in REQUESTS.items():
        saved = json.loads(checked(PREVIOUS / f'{mode}-request.json', pin))
        inventory = ORIGINAL / 'candidate/fast-scan-inputs' / (saved['session'] + '.json')
        checked(inventory, INVENTORY_SHA)
        indexed = inventory_binding(Path(saved['recording']), inventory, saved['session'], saved['inventory'])
        _, _, metadata = indexed(None, Path(saved['recording']), verify_windows=False)
        if metadata['window_count'] != 1200:
            raise ValueError('South is the same complete signed 1,200-visit workload')
        native = json.loads(checked(Path(saved['native_file']), NATIVE_SHA))
        bind_native(native, saved['session'], saved['inventory'], DETECTOR, expected='sha256:'+NATIVE_SHA)
        if (native['source']['raw_recording_authority_digest'] != saved['raw_authority']
                or native['clock_anchor']['before']['realtime_ns'] != saved['causal_cutoff_utc_ns']
                or native['provenance']['processed_windows'] != 1200):
            raise ValueError('The South packet differs from its original signed acquisition')
        checked(Path(saved['offer_file']), saved['offer_sha256'])
        for name, path in saved['local_libraries'].items():
            checked(Path(path), LIBRARIES[name][1])
        requests[mode] = dict(recording=saved['recording'], region=saved['offer_file'], offer_sha256=saved['offer_sha256'],
               authority=saved['raw_authority'], session=saved['session'], inventory=saved['inventory'], issued=1200,
               archive=saved['local_archive'], cutoff_utc_ns=saved['causal_cutoff_utc_ns'], libraries=saved['local_libraries'],
               native='sha256:'+NATIVE_SHA, packet=saved['native_file'], saved_inventory=str(inventory), receiver='named-v3')
    first, second = requests.values()
    shared = first.keys() - {'region','offer_sha256'}
    if any(first[key] != second[key] for key in shared) or first['offer_sha256'] == second['offer_sha256']:
        raise ValueError('Expected exactly the two previous offers on one signed acquisition')
    if archive_identity(Path(first['archive']['root'])) != first['archive']:
        raise ValueError('The earlier South causal catalogue changed')
    return requests


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine, requests = host(), bindings()
    one = requests['containing']
    paths = (root.parent, one['packet'], one['saved_inventory'], one['archive']['root'])
    if any(subprocess.check_output(['findmnt','-no','FSTYPE','-T',path], text=True).strip() != 'tmpfs' for path in paths):
        raise ValueError('Expected a staged signed packet, archive and fresh private tmpfs root')
    root.mkdir()
    for name in ('fonts','tmp'):
        (root/name).mkdir()
    font = 'fontlist-v3.11.0.json'
    (root/'fonts'/font).write_bytes(checked(PREVIOUS/'fonts'/font, FONT_SHA))
    sources = ('named_south_transfer.py','cumulative_grid_projection.py','unified_short_bootstrap.py',
               'named_survivor_fit.py','isolated_salvage.py','endpoint_track_repair.py',PROTOCOL.name)
    write(root/'seal.json', dict(machine=machine, inputs=requests, previous_request_sha256=REQUESTS, font_sha256=FONT_SHA,
                                order=list(requests), source_sha256={name: sha256((HERE/name).read_bytes()).hexdigest() for name in sources}))
    env = environment(root)
    env['TMPDIR'] = str(root/'tmp')
    for mode, request in requests.items():
        job, target = root/f'{mode}-request.json', root/mode
        write(job, request)
        command = ['/usr/bin/timeout','--kill-after=2s','90s',RELEASE/'venv/bin/python','-IB',
                   HERE/'cumulative_grid_projection.py','worker',job,'combined',target,'--named-survivor-finish',
                   '--direct-orbit-figures','--direct-residual-figures']
        clock = measure(command, env, target)
        write(root/f'{mode}-clock.json', dict(timing=clock, command=list(map(str,command))))


if __name__ == '__main__':
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=['launch'])
    parser.add_argument('root', type=Path)
    launch(parser.parse_args().root)
