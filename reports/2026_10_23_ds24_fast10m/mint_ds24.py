"""Bounded metadata-only DS24 snapshot; never reads IQ payload bytes."""
import sys, json, hashlib, os
from pathlib import Path
from datetime import datetime, UTC
from collections import defaultdict

REPO = Path('/home/mouse9911/gits/leo-tracker-reduxredux')
OUT = Path('/srv/bulk/leo/research/ds24-20261023')
sys.path.insert(0, str(REPO / 'reports/2026_10_14_ds22_post_ds21'))
sys.path.insert(0, str(REPO / 'tools'))
import raw_inventory as inv
from freeze_ds23_dataset import compact_member
from mint import counts

def sha(path): return inv.digest(path.read_bytes())
def write(name, doc):
    (OUT / name).write_text(json.dumps(doc, indent=2, allow_nan=False) + '\n')

start = int(datetime(2026,10,21,23,42,37,tzinfo=UTC).timestamp()) * 10**9
end = int(datetime(2026,10,23,23,42,37,tzinfo=UTC).timestamp()) * 10**9
parent = json.loads((REPO / 'reports/2026_10_18_ds23_post_ds22/manifest.json').read_text())
roots = set(parent['discovery_roots'])
for base in (Path('/srv/bulk/leo'), Path('/srv/postgres-nvme')):
    roots.update(str(p) for p in base.iterdir() if p.is_dir() and p.name.startswith(('fast8-', 'fast-scan-recordings')))
groups = defaultdict(list)
errors = []
checked = 0
for root in sorted(roots):
    p = Path(root)
    if not p.exists(): continue
    next(p.iterdir(), None)
    for path in sorted(p.rglob('manifest.json')):
        if any(part.startswith('.') for part in path.relative_to(p).parts): continue
        checked += 1
        try:
            payload = path.read_bytes()
            d = json.loads(payload)
            if d.get('kind') == 'short_window_iq_recording':
                groups[path.parent.parent].append((path,d,inv.digest(payload)))
        except (OSError, ValueError) as e: errors.append(dict(path=str(path),error=str(e)))
selected_roots=[]; excluded=[]
for root, segments in groups.items():
    t = min(d.get('created_utc_ns',2**63-1) for _,d,_ in segments)
    rates = sorted({d.get('sample_rate_hz', d.get('configuration',{}).get('sample_rate_hz')) for _,d,_ in segments},key=str)
    reason = 'outside_acquisition_start_window' if not start <= t < end else ('sample_rate_not_uniform_10MSps' if rates != [10000000] else None)
    evidence=dict(recording_id=root.name, root=str(root), captured_utc_ns=t, sample_rates_hz=rates,
                  segment_manifests=[dict(path=str(p),sha256=s) for p,_,s in segments])
    if reason: excluded.append(dict(evidence, reason=reason))
    else: selected_roots.append(root)
write('discovery_preliminary.json',dict(checked_manifest_count=checked, eligible_roots=list(map(str,selected_roots)),excluded=excluded,errors=errors))
print('eligible roots',len(selected_roots),'checked manifests',checked,flush=True)
result=inv.inventory(selected_roots,Path('/srv/bulk/leo'),2**63-1,start_ns=start,dataset_id='DS24',required_channels=None)
members=[]
for raw in result['members']:
    m=compact_member(raw)
    m['sample_rate_hz']=10000000
    m['recording_metadata'] = []
    run = Path(m['raw_recording']['root']) / 'run.json'
    if run.exists():
        d=json.loads(run.read_bytes())
        m['recording_metadata'].append(dict(path=str(run),sha256=sha(run),state=d.get('state'),fault=d.get('fault')))
        if d.get('state') not in ('stopped','complete') or d.get('fault'):
            m['recording_state']='incomplete'
    m['raw_manifest_digest']=inv.digest(json.dumps([(Path(s['path']).parent.name,s['sha256']) for s in m['raw_recording']['segments']],separators=(',',':')).encode())
    m['raw_authority_digest'] = m.get('raw_authority_digest') or m['raw_manifest_digest']
    m['analysis_availability']='existing_tracking_contract' if m['tracking_inputs'] else 'existing_tracking_contract_unavailable'
    m['dataset_label']=f'DS24-{len(members)+1:04d}'
    members.append(m)
manifest=dict(schema='ds24-recording-membership/v1',dataset_id='DS24',created_utc=datetime.now(UTC).isoformat(),start_utc_ns=start,cutoff_utc_ns=end,
              selection='All discovered fast recordings with actual uniform 10MS/s metadata and acquisition start in [2026-10-21T23:42:37Z,2026-10-23T23:42:37Z)',
              analysis_readiness_required=False,complete_recording_required=False,scientific_outcomes_used_for_membership=False,
              discovery_roots=sorted(roots),counts=counts(members),members=members,discovery_errors=errors+result['discovery_errors'],
              metadata_snapshot_is_atomic=False,payloads_copied_or_rehashed=False,source_sha256=sha(Path(__file__)))
write('manifest.json',manifest)
(OUT/'manifest.sha256').write_text(sha(OUT/'manifest.json')+'  manifest.json\n')
write('sample.json',dict(dataset_id='DS24',manifest_sha256=sha(OUT/'manifest.json'),sampling='all frozen members; no quality selection or substitutions',sampled_before_position_or_association_results=True,selected=members))
write('seal.json',dict(files={n:sha(OUT/n) for n in ('manifest.json','sample.json','mint_ds24.py','discovery_preliminary.json')}))
for p in OUT.iterdir():
    if p.is_file(): os.chown(p,1000,1000)
print(json.dumps(manifest['counts']),flush=True)
