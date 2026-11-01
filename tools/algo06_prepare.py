"""Adapt a verified ALGO05 export into the evaluated numerical input contract."""
import copy
from pathlib import Path
from algo03_shadow_worker import read, write
from algo06_cache import relocate, digest
from algo06_science.rank import fragment_rows
from leo.contracts.fast_graph_position_v4 import incumbent_proof
from leo.contracts.fast_graph_position_v5 import owners, ARMS

def prepare(output):
    output = Path(output)
    export = output/'source-export'
    descriptor = read(export/'descriptor.json')
    if descriptor['root'] != str(export):
        raise ValueError('Wrong private export root')
    for name, expected in descriptor['files'].items():
        path = Path(name)
        if path.is_absolute() or '..' in path.parts or digest(export/path) != expected.removeprefix('sha256:'):
            raise ValueError('Export member changed')
    local = output/'current'
    relocation = relocate(export/'recovery', local, descriptor['source_recovery_root'],
        {k.removeprefix('recovery/'):v for k,v in descriptor['files'].items() if k.startswith('recovery/')})
    write(output/'relocation.json', relocation)
    terminal = descriptor['incumbent']
    old = terminal['incumbent']; proof = incumbent_proof(old)
    current = local/'current'
    paths = list((current/'all-large-track-recovery').glob('*/inventory.json'))
    if len(paths) != 1:
        raise ValueError('Exactly one native inventory required')
    invpath = paths[0]; inv = read(invpath)
    native = Path(inv['job']['root'])/inv['job']['case']
    if not native.resolve().is_relative_to(output.resolve()):
        raise ValueError('Native input escaped private export')
    obs, tracks = read(native/'observations.json'), read(native/'tracks.json')
    baseline_owners = owners(terminal)
    arms = proof['selected']['arms'] if proof.get('selected') else proof['baseline']['arms']
    selected = copy.deepcopy(proof.get('selected'))
    if selected:
        candidates = [read(p).get('selected') for p in (current/'decision.json',current/'cache/decision.json') if p.exists()]
        matches = [v for v in candidates if v and v['kind']==selected['kind'] and
                   all(v['arms'][a]['endpoint_east_north_km']==arms[a]['endpoint_east_north_km'] for a in ARMS)]
        if not matches:
            raise ValueError('Published selected proof differs from relocated decision')
        selected = matches[0]
    gap = None
    if terminal['candidate']:
        gap = read(local/'decision.json')['selected']
        arms = read(Path(gap['path'])/'target_0.json')['arms']
        if any(arms[a]['proposed_owners'] != baseline_owners[a] for a in ARMS):
            raise ValueError('Relocated gap ownership differs')
    fragments, summary = fragment_rows('SCAN', tracks, obs, baseline_owners['fitted_c'],inv['job']['identities'])
    occupied = set(baseline_owners['c0']) | set(baseline_owners['fitted_c'])
    eligible = [r for r in fragments if r['points']>=20 and r['duration_s']>=15 and not set(r['observation_ids'])&occupied]
    eligible.sort(key=lambda r:(-r['duration_s'],-r['points'],r['fragment_id']))
    z = dict(case='SCAN',inventory_path=str(invpath),recovery_path=str(current),native_path=str(native),
        scan_receipt=read(native/'receipt.json'),selected=selected,gap_selected=gap,baseline_arms=arms,
        baseline_owners=baseline_owners,baseline_source=str(export/'incumbent-terminal.json'),
        baseline_sha256=digest(export/'incumbent-terminal.json'),targets=eligible[:3],eligible_targets=len(eligible))
    write(output/'inputs/SCAN.json',z)
    write(output/'residual-inventory.json',dict(fragments=fragments,summary=summary))
    return z

def export_catalogue(output, cutoff, *, reader):
    from sgp4.exporter import export_tle
    from leo.operations.causal_tle_catalogue import causal_catalogue
    catalogue = causal_catalogue(reader, cutoff, maximum_age_s=72*3600)
    packet = dict(case='SCAN',cutoff_utc_ns=cutoff,snapshot_count=catalogue.snapshot_count,
        elements={str(n):dict(p,lines=list(export_tle(s))) for n,s,p in
                  zip(catalogue.catalogue.satellite_numbers,catalogue.catalogue.satellites,catalogue.provenance)})
    for row in packet['elements'].values():
        if any(not 0<=cutoff-row[k]<=72*3600*1e9 for k in ('element_epoch_utc_ns','collected_utc_ns')):
            raise ValueError('Noncausal catalogue member')
    write(Path(output)/'catalogues/SCAN.json',packet)
    return packet

def compact(output, policy):
    root=Path(output); z=read(root/'inputs/SCAN.json')
    result=read(root/'position/SCAN/result.json'); decision=result['decisions'][policy]
    if decision['status']!='qualified':
        return None
    trial=result['trials'][decision['trial']]
    screen=read(root/'screen/SCAN/result.json')
    target=next(t for t in screen['targets'] if t['source']['fragment_id']==decision['source'])
    summary=next(s for s in target['summaries'] if s['policy']==policy)
    ids=target['source']['observation_ids']; norad=decision['norad']
    catalogue=read(root/'catalogues/SCAN.json')
    return dict(norad=norad,target_ids=ids,target_times_s=target['times_s'] if 'times_s' in target else
                next(t['times_s'] for t in read(root/'preflight/SCAN.json')['targets'] if t['source']['fragment_id']==decision['source']),
        observation_ids=[o['observation_id'] for o in read(Path(z['native_path'])/'observations.json')],
        element=catalogue['elements'][str(norad)],cutoff_utc_ns=z['scan_receipt']['cutoff_utc_ns'],
        screen=summary,replay_checks=read(root/'preflight/SCAN.json')['checks'],
        trial=trial,control=result['control'],
        published_owners={a:dict(z['baseline_owners'][a],**dict.fromkeys(ids,norad)) for a in ARMS})
