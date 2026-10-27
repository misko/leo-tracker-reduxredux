"""Audit the fully terminal endpoint packet first, then report-only geography."""
import argparse
import collections
import math
from pathlib import Path
import sys
import time
import numpy as np

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from audit_implementation import read,write,sha
from replay_endpoints import context_from_saved,mapping,recovery
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')


def distance_m(point,reference):
    a,b,c,d=map(math.radians,(*point,*reference));v=math.sin((c-a)/2)**2+math.cos(a)*math.cos(c)*math.sin((d-b)/2)**2
    return 2*6371008.8*math.asin(min(1.,math.sqrt(v)))


def audit_export(packet_path,manifest_path):
    packet_path=Path(packet_path);manifest_path=Path(manifest_path);manifest=read(manifest_path)
    assert manifest['all_attempts_terminal'] and manifest['coherent_handoff_sealed']
    for path,h in manifest['protected_hashes'].items():assert sha(path)==h,path
    for path in manifest['terminal_seals']:
        terminal=read(path);assert terminal['all_terminal']
        assert not terminal.get('denied_paths',terminal.get('denied_reads',[]))
        for file,h in terminal.get('output_sha256',terminal.get('terminal_output_hashes',{})).items():assert sha(file)==h,file
    export_protocol=read(packet_path.parent/'endpoint_export_protocol.json')
    assert export_protocol['manifest_sha256']==sha(manifest_path)
    packet=read(packet_path);assert packet['all_attempts_terminal'] and not packet['geographic_evaluation_performed']
    assert packet['export_protocol_sha256']==sha(packet_path.parent/'endpoint_export_protocol.json')
    bykey={};audited=[];endpoints={};identities={};alias_coordinate_differences=[]
    for job in packet['rows']:
        key=job['case'],job['variant'];assert key not in bykey;bykey[key]=job
        root=Path(job['root']);case=job['case'];variant=job['variant'];receipts=[read(p) for p in (root/'read_receipts').glob('*.json')]
        assert not any(r['denied_paths'] for r in receipts)
        status=job['status'];valid=status=='complete' and bool(job['endpoint_available']) and job['read_audit_complete'] is True
        original=read(SOURCE/case/'observations.json');observations=read(root/case/'observations.json')
        assert observations[:len(original)]==original and len({r['observation_id'] for r in observations})==len(observations)
        added=set(read(root/case/'research_input_receipt.json')['added_native_observation_ids'])
        row=dict(case=case,variant=variant,root=str(root),status=status,valid=valid,
            seconds=job['seconds'],read_audit_complete=valid and len(receipts)>=3,
            original_GLRT_count=len(original),total_GLRT_count=len(observations),added_native_count=len(added),
            unavailable_reason=None if valid else 'retained '+status+' or incomplete read audit',arms={})
        if valid:
            assert len(receipts)>=3 and not any('gps' in Path(x).name.lower() or 'oracle' in Path(x).name.lower() for r in receipts for x in r['read_paths'])
            d=context_from_saved(root,case);maps={};members={};problems={}
            for arm in ('c0','fitted_c'):
                members[arm]=recovery.membership(d,arm,d['arms'][arm]);maps[arm],problems[arm]=mapping(d,arm)
                m=members[arm];exported=job['arms'][arm]
                assert exported['endpoint_latlon']==d['arms'][arm]['endpoint_latlon']
                assert exported['RMS_hz']==d['arms'][arm]['RMS_hz']
                assert exported['accepted_GLRT_count']==m['associated'] and exported['total_GLRT_count']==m['total_GLRT']
                assert set(exported['accepted_observation_ids'])==set(m['accepted_observation_ids'])
                assert set(exported['added_curved_ids'])==added&set(m['curved_observation_ids'])
                assert set(exported['added_predictive_ids'])==added&set(m['predictive_observation_ids'])
                endpoints[case,variant,arm]=exported['endpoint_latlon']
                row['arms'][arm]=dict(frequency_RMS_hz=exported['RMS_hz'],associated_GLRT=m['associated'],
                    association_fraction=m['associated']/m['total_GLRT'],likelihood_points=m['likelihood_points'],
                    curved_likelihood_points=m['curved_points'],predictive_likelihood_points=m['predictive_points'],
                    added_curved_IDs=exported['added_curved_ids'],added_predictive_IDs=exported['added_predictive_ids'],
                    added_accepted_IDs=exported['added_accepted_ids'],objective_replay_difference=m['objective_replay_difference'])
            a,b=problems['c0'],problems['fitted_c']
            assert maps['c0']==maps['fitted_c'] and np.array_equal(a.keep,b.keep) and np.array_equal(a.alias,b.alias)
            assert a.labels==b.labels and np.array_equal(a.point_noise,b.point_noise) and np.array_equal(a.scan.norads,b.scan.norads)
            # Exporter's predictive alias is entry-relative; compare physical IDs
            # and labels, then retain our normalized total-native coordinate.
            exported_map=job['likelihood_native_identity'];assert set(exported_map)==set(maps['c0'])
            for oid,value in maps['c0'].items():
                assert value['role']==exported_map[oid]['role'] and value['norad']==exported_map[oid]['norad']
                if value['native_alias']!=exported_map[oid]['alias_lift']:
                    assert value['role']=='predictive';alias_coordinate_differences.append(dict(case=case,variant=variant,observation_id=oid))
            identities[case,variant]=maps['c0']
        audited.append(row)
    expected=read(HERE/'candidate_protocol_pre_geography_audit.json');aliases=packet.get('comparison_aliases',manifest.get('comparison_aliases',[]))
    expected_alias={(r['case'],v) for r in expected['cases'] if r['treatment_source']=='baseline_equivalent' for v in ('additions_bin_floor','additions_proxy')}
    assert {(r['case'],r['variant']) for r in aliases}==expected_alias
    audit=dict(all_attempts_terminal=True,all_protected_hashes_verified=True,
        all_results_classified_and_valid_results_audited=True,physical_jobs=audited,
        packet_path=str(packet_path),packet_sha256=sha(packet_path),manifest_path=str(manifest_path),manifest_sha256=sha(manifest_path),
        aliases=aliases,predictive_alias_coordinate_normalizations=len(alias_coordinate_differences),
        no_new_position_or_prior_fit=True,IQ_calls=0,geographic_error_evaluation_performed=False,
        valid_physical_jobs=sum(r['valid'] for r in audited),incomplete_physical_jobs=sum(not r['valid'] for r in audited),
        implementation_audit_sha256=sha(HERE/'candidate_protocol_pre_geography_audit.json'),evaluation_protocol_sha256=sha(HERE/'protocol_v2.json'))
    write(HERE/'pre_geography_terminal_audit.json',audit)
    return audit,endpoints,identities


def main(packet_path,manifest_path):
    began=time.monotonic();audit,endpoints,identities=audit_export(packet_path,manifest_path)
    # Reporting-only coordinate enters after the independent terminal audit write.
    reference=[37.849061591561885,-122.48574968092912]
    nom={r['case']:r for r in read(HERE/'nomination_audit.json')['cases']};cases=list(nom)
    physical={(r['case'],r['variant']):r for r in audit['physical_jobs']};aliases={(r['case'],r['variant']):r for r in audit['aliases']}
    assert set(physical)|set(aliases)=={(c,v) for c in cases for v in ('baseline','additions_bin_floor','additions_proxy')}
    records=[];attribution=[]
    for case in cases:
        for variant in ('baseline','additions_bin_floor','additions_proxy'):
            equivalent=(case,variant) in aliases;source_variant='baseline' if equivalent else variant;row=physical[case,source_variant]
            for arm in ('c0','fitted_c'):
                record={k:row[k] for k in ('case','status','valid','seconds','read_audit_complete','original_GLRT_count','total_GLRT_count','added_native_count')}
                record.update(variant=variant,cohort=nom[case]['cohort'],eligible_lane=nom[case]['eligible'],baseline_equivalent=equivalent,
                    unavailable_reason=row['unavailable_reason'],error_m=distance_m(endpoints[case,source_variant,arm],reference) if row['valid'] else None,arm=arm)
                record.update(row['arms'].get(arm,dict(frequency_RMS_hz=None,associated_GLRT=None,association_fraction=None,
                    likelihood_points=None,curved_likelihood_points=None,predictive_likelihood_points=None,added_curved_IDs=[],added_predictive_IDs=[],added_accepted_IDs=[])))
                records.append(record)
            if variant=='baseline' or equivalent or not row['valid'] or not physical[case,'baseline']['valid']:continue
            base=identities[case,'baseline'];current=identities[case,variant];oldfamilies={v['norad'] for v in base.values()}
            added=set(read(Path(row['root'])/case/'research_input_receipt.json')['added_native_observation_ids'])
            attribution.append(dict(case=case,variant=variant,cohort=nom[case]['cohort'],
                new_likelihood_native_ids=sorted(set(current)&added),
                newly_accepted_likelihood_families=sorted({v['norad'] for v in current.values()}-oldfamilies),
                new_owner_family_classification={oid:'incumbent_family_extension' if current[oid]['norad'] in oldfamilies else 'new_family' for oid in sorted(set(current)&added)},
                lost_old_likelihood_ids=sorted(set(base)-set(current)),gained_old_likelihood_ids=sorted((set(current)-set(base))-added),
                reassigned_old_likelihood_ids=[oid for oid in set(base)&set(current) if base[oid]!=current[oid]]))
    write(HERE/'analysis_records.json',dict(all_attempts_terminal=True,all_results_classified_and_valid_results_audited=True,
        all_protected_hashes_verified=True,reference_used_only_after_audit_seal=True,records=records,attribution=attribution,
        reference_latlon=reference,pre_geography_audit_sha256=sha(HERE/'pre_geography_terminal_audit.json'),
        terminal_release=dict(packet_sha256=audit['packet_sha256'],manifest_sha256=audit['manifest_sha256']),
        no_new_IQ_or_position_fits=True,seconds=time.monotonic()-began))
    print(dict(physical_jobs=len(audit['physical_jobs']),logical_c_arm_rows=len(records),valid_physical_jobs=audit['valid_physical_jobs'],seconds=time.monotonic()-began),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--packet',required=True);p.add_argument('--manifest',required=True);a=p.parse_args();main(a.packet,a.manifest)
