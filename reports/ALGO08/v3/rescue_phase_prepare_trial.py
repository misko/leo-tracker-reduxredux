"""Measure current-solver fine-salvage reuse on one positive saved rescue."""

import argparse
from hashlib import sha256
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


HERE = Path(__file__).resolve().parent
CONTROLS = {
    'DS30-0402': (Path('/dev/shm/leo-v3-named-survivor-fit-0402-01/fixed'),
                  'f8db8fada16d4061de4f5e6c8ecf1394ea9a397b74e5ccbf68108caf16682a22'),
    'DS30-0374': (Path('/dev/shm/leo-v3-0374-final-fit-result02/combined'),
                  '46080930eec33cf3586d8dc226c86d56324b734ef18349445b502bd31556d4e9'),
    'DS30-0008': (Path('/dev/shm/leo-v3-mixed-final-0008-01/candidate'),
                  'dfbe0c40ae78187d583198ab97517c204708a5c7d899d0efe9f76f646a82205a'),
}
FILES = ('unified_short_bootstrap.py','joint_publication.py','certified_salvage.py','isolated_salvage.py',
         'endpoint_track_repair.py','named_survivor_fit.py','blind_joint_finish.py','blind_joint_signed.py',
         'blind_joint_repair.py','cold_finalist_race.py','direct_orbit_entry.py','direct_residual_entry.py')


def census(receipt):
    d = receipt['route_details']
    provisional = d.get('provisional_salvage',{})
    endpoint = provisional.get('endpoint_trim',d.get('endpoint_trim',{}))
    cold = d.get('cold',{})
    timer = lambda source,name: source.get(name,{}).get('cpu_s',0.)
    return dict(solve_cpu_s=receipt['solve']['cpu_s'],cold_cpu_s=timer(d,'cold_clocks'),
         finalist_cpu_s=sum(row['cpu_ns'] for field in ('prefix','completed') for row in cold.get(field,[]))/1e9,
         cold_route=cold.get('routing'),cold_escalated=len(cold.get('completed',[])),
         salvage_cpu_s=timer(d,'salvage_clocks'),certified=d.get('certified_salvage',{}),
         isolated_calls=provisional.get('fit_calls',0),isolated_status=provisional.get('status'),
         isolated_cpu_s=timer(provisional,'isolation_clocks'),
         isolated_predictive_and_pair_cpu_s=timer(provisional,'predictive_and_pair_clocks'),
         ordinary_finish_cpu_s=timer(d,'finish_clocks'),endpoint_calls=endpoint.get('refit_calls',0),
         endpoint_cpu_s=endpoint.get('cpu_s',0.),ordinary_repair_cpu_s=timer(d,'repair_fit_clocks'),
         signed_refit_cpu_s=timer(d,'signed_refit_clocks'),standard_evidence_cpu_s=timer(d,'standard_evidence_clocks'))


def worker(root):
    import unified_short_bootstrap as entry
    from aperture_trial import read,write
    from owner_loss_0402 import STAGED,request
    from prospective_0402_solver import SETTINGS,worker as publish_worker
    from rescue_phase_prepare import binding

    job,_ = request()
    bind = read(root/'binding.json')
    parent = entry.publish_active
    audit = []

    def active(args,*values,**options):
        from leo.storage.short_window import ShortWindowReader
        from named_constrained_research import deny_waveform

        args.named_survivor_finish = True
        args.direct_residual_figures = args.direct_orbit_figures = True
        with binding(audit), patch.object(ShortWindowReader,'__init__',deny_waveform):
            return parent(args,*values,**options)

    with patch.object(entry,'publish_active',active):
        publish_worker(job,'cumulative',root/'candidate',source_pins={k:bind['sources'][k] for k in FILES},
                       inventory_file=STAGED/'inventory.json',**SETTINGS)
    if not audit:
        raise ValueError('The current combined fast solver never called the certified fine stage')
    write(root/'fine-shadow.json',audit)


def launch(root):
    from aperture_trial import RELEASE,write
    from dense_geographic_trial import host
    from empty_bootstrap import checked
    from full_short_physical import environment
    from owner_loss_0402 import REQUEST_SHA,STAGED,request
    from short_raw_diagnostic import measure

    machine = host()
    job,assignment = request()
    if subprocess.check_output(['findmnt','-no','FSTYPE','-T',root.parent],text=True).strip() != 'tmpfs':
        raise ValueError('Use the existing signed staging and a new private tmpfs output')
    archived = {case:census(json.loads(checked(folder/'joint-research-receipt.json',pin)))
                for case,(folder,pin) in CONTROLS.items()}
    if archived['DS30-0402']['isolated_status'] != 'adopted' or archived['DS30-0402']['endpoint_calls'] != 1:
        raise ValueError('This test must reach the original positive supported rescue')
    root.mkdir()
    (root/'tmp').mkdir()
    sources = (*FILES,'rescue_phase_prepare.py','rescue_phase_prepare_trial.py','rescue-phase-prepare-protocol.md')
    write(root/'binding.json',dict(request_sha256=REQUEST_SHA,input=assignment,request_path=str(job),machine=machine,
        sources={name:sha256((HERE/name).read_bytes()).hexdigest() for name in sources},archived_census=archived,
        archive_control_sha256={case:pin for case,(_,pin) in CONTROLS.items()}))
    env = environment(STAGED)
    env['TMPDIR'] = str(root/'tmp')
    target = root/'candidate'
    command = ['/usr/bin/timeout','--kill-after=2s','90s',RELEASE/'venv/bin/python','-IB',__file__,'worker',root]
    timing = measure(command,env,target)
    write(root/'clock.json',dict(timing=timing,command=list(map(str,command))))
    if timing['exit_code']:
        raise RuntimeError(timing['stderr_tail'])


if __name__ == '__main__':
    sys.path.insert(0,str(HERE))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('operation',choices=('launch','worker'))
    parser.add_argument('root',type=Path)
    args = parser.parse_args()
    {'launch':launch,'worker':worker}[args.operation](args.root)
