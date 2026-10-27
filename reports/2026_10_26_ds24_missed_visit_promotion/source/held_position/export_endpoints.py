"""Post-seal replay and endpoint export; no geographic reference or scoring."""
import argparse
from pathlib import Path
import sys
from position import HERE,REPO,read,write,sha

RECOVERY=Path('/srv/bulk/leo/research/ds24-movement-policy-r01/recovery')
sys.path[:0]=[str(RECOVERY),str(REPO/'src'),str(REPO/'tools'),'/tmp/algo03-feasible-deps']
import recovery
from leo.analysis.research.retained_track_likelihood import PERIOD

def mapping(d,arm):
    p=recovery.build(d,arm,d['arms'][arm]['phase_reference'])
    observations={o['observation_id']:o for o in d['observations']};out={}
    for row,index,sl,alias in zip(p.rows,p.members,p.slices,p.alias,strict=True):
        track=p.scan.tracks[index]
        for oid,value,active in zip(track['observation_ids'],track['values'],p.keep[sl],strict=True):
            if not active:continue
            assert oid not in out
            out[oid]=dict(role='curved',norad=int(p.scan.norads[row['candidate_index']]),alias_lift=round((float(value)-observations[oid]['measured_cfo_hz'])/PERIOD)+int(alias))
    for entry in d['entries']:
        for oid in entry['observation_ids']:
            assert oid not in out
            out[oid]=dict(role='predictive',norad=int(p.scan.norads[entry['candidate_index']]),alias_lift=int(entry.get('alias',0)))
    return out

def audit_job(job):
    root=Path(job['root']);case=job['case'];row=dict(job)
    receipts=[read(p) for p in (root/'read_receipts').glob('*.json')]
    denied=[p for r in receipts for p in r['denied_paths']]
    reads=sorted({p for r in receipts for p in r['read_paths']})
    assert not denied
    assert not any('gps' in Path(p).name.lower() or 'oracle' in Path(p).name.lower() for p in reads)
    qnap=[p for p in reads if Path(p).is_relative_to('/mnt/qnap01')]
    assert not qnap
    row.update(read_receipt_count=len(receipts),denied_paths=denied,qnap_read_paths=qnap,native_IQ_not_requested=True,read_paths=reads)
    if row['status']!='complete':
        row.update(endpoint_available=False,read_audit_complete=False if not receipts else None)
        return row
    assert len(receipts)>=3
    recovery.SOURCE=root;d=recovery.context(case)
    maps={a:mapping(d,a) for a in ('c0','fitted_c')};assert maps['c0']==maps['fitted_c']
    members={a:recovery.membership(d,a,d['arms'][a]) for a in ('c0','fitted_c')}
    for key in ('curved_observation_ids','predictive_observation_ids'):assert members['c0'][key]==members['fitted_c'][key]
    added=set(read(root/case/'research_input_receipt.json')['added_native_observation_ids'])
    row['arms']={}
    for arm,m in members.items():
        saved=d['arms'][arm]
        row['arms'][arm]=dict(endpoint_latlon=saved['endpoint_latlon'],endpoint_east_north_km=saved['endpoint_east_north_km'],RMS_hz=saved['RMS_hz'],negative_twice_elbo=saved['negative_twice_elbo'],objective_replay_difference=m['objective_replay_difference'],likelihood_points=m['likelihood_points'],curved_points=m['curved_points'],predictive_points=m['predictive_points'],accepted_GLRT_count=m['associated'],total_GLRT_count=m['total_GLRT'],accepted_fraction=m['associated']/m['total_GLRT'],native_added_count=len(added),added_curved_ids=sorted(added&set(m['curved_observation_ids'])),added_predictive_ids=sorted(added&set(m['predictive_observation_ids'])),added_accepted_ids=sorted(added&set(m['accepted_observation_ids'])),accepted_observation_ids=m['accepted_observation_ids'],postfit_only_observation_ids=m['postfit_only_observation_ids'],active_curved_norads=m['active_curved_norads'])
    row.update(endpoint_available=True,read_audit_complete=True,matched_c_likelihood_IDs_candidate_labels_aliases=True,likelihood_native_identity=maps['c0'])
    return row

def main(manifest_path):
    manifest=read(manifest_path)
    # This manifest must be created only after every declared attempt is terminal.
    assert manifest['all_attempts_terminal'] and manifest['coherent_handoff_sealed']
    for path,h in manifest['protected_hashes'].items():assert sha(path)==h,path
    seals=[read(p) for p in manifest['terminal_seals']]
    assert all(s['all_terminal'] for s in seals)
    for s in seals:
        assert not s.get('denied_paths',s.get('denied_reads',[]))
        for path,h in s.get('output_sha256',s.get('terminal_output_hashes',{})).items():assert sha(path)==h,path
    write(HERE/'endpoint_export_protocol.json',dict(manifest_sha256=sha(manifest_path),source_sha256=sha(__file__),no_GPS_reference_or_scoring=True,terminal_seals={str(p):sha(p) for p in manifest['terminal_seals']}))
    rows=[audit_job(job) for job in manifest['jobs']]
    write(HERE/'endpoint_packet.json',dict(schema='DS24-frozen-coherent-endpoint-packet/v1',export_protocol_sha256=sha(HERE/'endpoint_export_protocol.json'),all_attempts_terminal=True,geographic_evaluation_performed=False,frequency_fit_and_position_accuracy_separate=True,rows=rows,comparison_aliases=manifest.get('comparison_aliases',[])))
    print(dict(rows=len(rows),complete=sum(r['status']=='complete' for r in rows),geographic_evaluation_performed=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--manifest',type=Path,required=True);a=p.parse_args();main(a.manifest)
