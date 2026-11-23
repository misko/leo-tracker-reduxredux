"""One saved dense mixed-detector run with the portable original final fit."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys


HERE = Path(__file__).resolve().parent
STAGED = Path('/dev/shm/leo-held-anchor-selected-dense-01')
PREVIOUS = Path('/dev/shm/leo-cumulative-grid-projection-01')
REQUEST_PIN = '8abec0e2f60def947cd03883662611c3fcfdbd5f255eb0ba60e8306085abf502'
PRIOR_PIN = '1ac1eacb47a49aa4fccdcd50e65df4f5a66f3a78c599010b8fabb4cb63181993'
PRIOR_ROWS_PIN = 'f378b41ceaf7a874aeb2b7cb02636647fa01b32c0ddc70efb65fd566a724182f'
ORIGINAL_V3_PIN = '51521b26848532823922cc43a198b7f91d59d3f1d81e155e5862b04b53193f38'
PROTOCOL = HERE / 'mixed-named-finish-0008-protocol.md'


def assigned():
    from aperture_trial import archive_identity
    from combined_frontier_run import BLOCK_SHA
    from empty_bootstrap import checked
    from full_short_raw import RECIPE_SHA
    from full_short_run import GEOGRAPHIC_SHA, TRACK_SCORES_SHA
    from grid_feature_projection import LIBRARY_SHA
    from named_constrained_research import inventory_binding
    from unified_short_bootstrap import LAYOUT_SHA256

    def checked_path(path, pin):
        checked(path, pin)
        return path

    source = json.loads(checked(STAGED / 'request.json', REQUEST_PIN))
    selected = json.loads(checked(STAGED / 'route-decision.json', source['selection_sha256']))
    native = source['original']['native_sha256']
    packet = checked_path(Path(source['original']['file']), native[7:])
    if (selected['choice']['route'] != 'unfiltered' or source['selected']['native_sha256'] != native
            or source['original']['detector'] != RECIPE_SHA):
        raise ValueError('Expected the original unfiltered mixed receiver packet')
    inventory_path = STAGED / 'selected/fast-scan-inputs' / (source['session'] + '.json')
    inventory = inventory_binding(Path(source['recording']), checked_path(inventory_path, source['inventory'][7:]),
                                  source['session'], source['inventory'])
    if inventory(None, Path(source['recording']), verify_windows=False)[2]['window_count'] != 6772:
        raise ValueError('Unexpected signed visit count')
    archive = source['archive']
    observed = archive_identity(Path(archive['root']))
    if observed != {key: archive[key] for key in observed}:
        raise ValueError('The original causal archive changed')
    region = checked_path(Path(source['offer']), source['offer_sha256'])
    pins = dict(frontier_block_library=BLOCK_SHA, geographic_library=GEOGRAPHIC_SHA,
                regional_track_library=TRACK_SCORES_SHA)
    libraries = {key: str(checked_path(Path(source['libraries'][key]), pin)) for key, pin in pins.items()}
    projection = checked_path(PREVIOUS / 'projection.so', LIBRARY_SHA)
    checked(HERE / 'one_pass_web_png.py', LAYOUT_SHA256)
    return dict(recording=source['recording'], region=str(region), offer_sha256=source['offer_sha256'],
                authority=source['authority'], session=source['session'], inventory=source['inventory'],
                archive=archive, issued=6772, native=native, packet=str(packet), cutoff_utc_ns=source['cutoff_utc_ns'],
                libraries=libraries, projection=str(projection), saved_inventory=str(inventory_path),
                pins=dict(libraries=pins, projection=LIBRARY_SHA, layout=LAYOUT_SHA256, staging=REQUEST_PIN,
                          route=source['selection_sha256'], protocol=sha256(PROTOCOL.read_bytes()).hexdigest(),
                          sources={name: sha256((HERE / name).read_bytes()).hexdigest() for name in (
                              'mixed_named_finish_0008.py', 'cumulative_grid_projection.py', 'named_survivor_fit.py',
                              'unified_short_bootstrap.py', 'isolated_salvage.py', 'endpoint_track_repair.py',
                          )}))


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from full_short_physical import environment
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(['findmnt', '-no', 'FSTYPE', '-T', root.parent], text=True).strip() != 'tmpfs':
        raise ValueError('Use a fresh private tmpfs root')
    request = assigned()
    root.mkdir()
    (root / 'tmp').mkdir()
    job = root / 'binding.json'
    write(job, dict(request, machine=machine))
    env = environment(root)
    env['TMPDIR'] = str(root / 'tmp')
    python = RELEASE / 'venv/bin/python'
    subprocess.run([python, '-Bc', "from matplotlib import font_manager; font_manager.findfont('DejaVu Sans')"],
                   env=env, check=True, timeout=30)
    target = root / 'candidate'
    command = ['/usr/bin/timeout', '--kill-after=2s', '90s', python, '-IB', HERE / 'cumulative_grid_projection.py',
               'worker', job, 'combined', target, '--named-survivor-finish']
    clock = measure(command, env, target)
    write(root / 'clock.json', dict(timing=clock, command=list(map(str, command))))
    if clock['exit_code']:
        raise RuntimeError(f"Saved publication exited {clock['exit_code']}: {clock['stderr_tail']}")


if __name__ == '__main__':
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['launch'])
    parser.add_argument('root', type=Path)
    launch(parser.parse_args().root)
