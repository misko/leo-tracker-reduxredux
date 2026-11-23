"""Reenter one authenticated saved route and cut at its signed finalist pair."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
ORIGINAL = Path('/dev/shm/leo-v3-mixed-final-0008-01')
BINDING_PIN = '71bb3459952cf21760764690f54e6536c154151257ba2cf854b1fa11b29870a5'
RESEARCH_PIN = 'dfbe0c40ae78187d583198ab97517c204708a5c7d899d0efe9f76f646a82205a'


class SignedPairComplete(BaseException):
    pass


def owner_rows(support):
    return sorted([identifier, row['norad'], role]
                  for source, role in (('curved', 'conditional'), ('predictive', 'predictive'))
                  for row in support[source].values() for identifier in row['ids'])


def worker(job, output):
    import cumulative_grid_projection as saved
    import named_survivor_fit as named
    from aperture_trial import write
    from named_phase_reuse import isolated_pair

    def stop(candidate, means, _audit, _witness):
        from blind_joint_finish import readout
        from blind_joint_signed import describe
        from leo.analysis.localization_v3.history_policy import pair_passes

        began = named.now()
        records, measured = isolated_pair(candidate, means)
        fit = named.clock(began)
        gate = pair_passes(records, include_linear=True, half_width_km=candidate['scan'].search_region.half_width_km)
        captured = describe(dict(candidate, arms=records, means=means))
        write(output.parent / 'pair.json', dict(clocks=fit, arms=measured, owner_rows=owner_rows(captured),
              signed_means_s=captured['means_s'], model=captured['model'], accepted=gate,
              readout={arm: readout({**record, 'history': [dict(step, movement_km=None) for step in record['history']]})
                       for arm, record in records.items()}))
        raise SignedPairComplete

    try:
        with patch.object(named, 'fit_pair', stop):
            saved.worker(job, 'combined', output, named_survivor_finish=True)
    except SignedPairComplete:
        if list(output.glob('**/terminal.json')) or list(output.glob('**/*.png')):
            raise ValueError('A signed-only replay unexpectedly reached standard publication')
        return
    raise ValueError('The pinned signed-pair hook was not reached')


def launch(root):
    from aperture_trial import RELEASE, write
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from mixed_named_finish_0008 import assigned
    from short_raw_diagnostic import measure

    machine = host()
    if subprocess.check_output(['findmnt', '-no', 'FSTYPE', '-T', root.parent], text=True).strip() != 'tmpfs':
        raise ValueError('Use a fresh private tmpfs root')
    request = assigned()
    historical = json.loads(checked(ORIGINAL / 'binding.json', BINDING_PIN))
    if ({k: v for k, v in request.items() if k != 'pins'} !=
            {k: v for k, v in historical.items() if k not in ('pins','machine')}):
        raise ValueError('The signed replay requires the original input and numerical libraries')
    root.mkdir()
    (root / 'tmp').mkdir()
    job = root / 'binding.json'
    pins = {name: sha256((HERE/name).read_bytes()).hexdigest() for name in (
        'named-phase-reuse-protocol.md', 'named_phase_reuse_trial.py', 'named_phase_reuse.py',
        'named_survivor_fit.py', 'grid_phase_state_reuse.py', 'cumulative_grid_projection.py',
    )}
    write(job, dict(request, machine=machine, replay_source_sha256=pins, reference_binding_sha256=BINDING_PIN))
    env = environment(root)
    env['TMPDIR'] = str(root / 'tmp')
    output = root / 'signed-cut'
    command = ['/usr/bin/timeout', '--kill-after=2s', '90s', RELEASE / 'venv/bin/python', '-IB',
               __file__, 'worker', root]
    timing = measure(command, env, output)
    write(root / 'clock.json', dict(timing=timing, command=list(map(str, command))))
    if timing['exit_code']:
        raise RuntimeError(f"Signed replay exited {timing['exit_code']}: {timing['stderr_tail']}")


def score(root):
    from aperture_trial import read, write
    from empty_bootstrap import checked
    from leo.contracts.digests import canonical_digest

    clock, request, pair = (read(root/name) for name in ('clock.json','binding.json','pair.json'))
    if clock['timing']['exit_code'] or not pair['accepted']:
        raise ValueError('Only a completed, originally eligible signed pair can be compared')
    original = json.loads(checked(ORIGINAL / 'candidate/joint-research-receipt.json', RESEARCH_PIN))
    source = original['route_details']
    arms = tuple(pair['arms'])
    exact = {arm: dict(readout=pair['readout'][arm] == source['signed']['finish'][arm],
                         owners=pair['owner_rows'] == sorted(original['selected_rows'][arm])) for arm in arms}
    if set(arms) != {'c0','fitted_c'} or not all(all(row.values()) for row in exact.values()):
        raise ValueError(f'The new pair altered original signed outputs: {exact}')
    measured = dict(pair, owner_rows=canonical_digest(pair['owner_rows']), owner_count=len(pair['owner_rows']))
    write(root/'result.json', dict(verified=True, request=request, clock=clock, pair=measured, exact=exact,
          original=dict(research_sha256=RESEARCH_PIN, signed_cpu_s=source['signed_refit_clocks']['cpu_s'],
                        witness=source['named_survivor_fit'], optimizer_status=source['signed']['status'])))


if __name__ == '__main__':
    sys.path.insert(0, str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation', choices=('launch','worker','score'))
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    {'launch': launch, 'worker': lambda root: worker(root/'binding.json', root/'signed-cut'),
     'score': score}[args.operation](args.root)
