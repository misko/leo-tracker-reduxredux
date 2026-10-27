"""Audit sealed coherent acquisition/graph handoffs before regional geography."""
import collections
import importlib.util
import json
from pathlib import Path
import sys
import time

HERE=Path(__file__).resolve().parent
BROADER=HERE.parent/'broader'
R01=Path('/srv/bulk/leo/research/ds24-missed-visit-r01')
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
RUNTIME=Path('/opt/leo-shared-scans/native-scope64-v2-3460060352b364a9/worker/src')
sys.path[:0]=[str(RUNTIME),str(R01/'validation')]
from baseline_scope import metadata_inventory
from audit_nomination import read,write,sha


def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m


def main():
    began=time.monotonic();nom=read(HERE/'nomination_audit.json');assert nom['all_passed']
    assert nom['nominations_sha256']==sha(BROADER/'nominations.json')
    p=read(BROADER/'raw/protocol.json');gp=read(BROADER/'graph_protocol_v2.json')
    for path,h in dict(p['files'],**gp['files']).items():assert sha(path)==h,path
    panel=read(BROADER/'panel.json');raw=read(BROADER/'predictions.json');packet=read(BROADER/'prediction_packets_v2.json')
    rawbyid={r['header']['prediction_id']:r for r in raw['rows']};packbyid={r['header']['prediction_id']:r for r in packet['rows']}
    predictor=module('independent_frozen_R01_predictor',R01/'prediction/predictor.py')
    forecast_checks=0
    for slot in panel['slots']:
        for cell in slot['cells']:
            h=cell['header'];forecast=rawbyid[h['prediction_id']]['forecast']
            assert predictor.predict(h,cell['history'])==forecast
            assert predictor.predict(dict(h,target_candidates=[{'secret':1e99}]),cell['history'])==forecast
            forecast_checks+=1
    assert forecast_checks==1850
    common=module('sealed_R01_native_ledger_audit',R01/'validation/coherent_application/integrate.py')
    common.TIMING=BROADER/'raw';math=module('frozen_R01_metadata_geometry',R01/'timing/timing_search.py')
    adapter=module('frozen_R01_metadata_adapter',R01/'timing/adapter.py')
    cases=read(HERE/'protocol_v2.json')['held_cases'];case_nom={r['case']:r for r in nom['cases']};summary=[];candidates=[]
    for case in cases:
        folder=BROADER/'graphs'/case;terminal=read(folder/'terminal_seal.json');assert terminal['all_passed']
        for path,h in terminal['files'].items():assert sha(path)==h,path
        audit=read(folder/'audit.json');assert audit['status']=='complete' and audit['no_sparse_union'] and audit['no_recovered_donors']
        assert audit['method']=='exact_R01_coherent_only' and not audit['geographic_inputs'] and not audit['forced_satellite_identity']
        tracking,inventory,original=metadata_inventory(case);rows=read(folder/'observations.json');tracks=read(folder/'tracks.json')
        assert rows[:len(original)]==original and len({r['observation_id'] for r in rows})==len(rows)
        native={n['observation_id']:n for n in inventory};originalids={r['observation_id'] for r in original}
        new={r['observation_id'] for r in rows}-originalids
        for row in rows:
            n=native[row['observation_id']];assert all(row[k]==n[k] for k in ('receiver','native_receiver_id','channel','time_s','actual_rf_hz'))
        graphids=[oid for t in tracks for oid in t['observation_ids']];assert len(graphids)==len(set(graphids)) and set(graphids)<={r['observation_id'] for r in rows}
        ledger=read(audit['ledger_path']);assert sha(audit['ledger_path'])==audit['ledger_sha256'] and ledger['observations']==rows
        assert set(audit['new_native_ids'])==new and len(new)==audit['new_native_owners']
        assert audit['no_eligible_lane']==(not case_nom[case]['eligible'])
        if audit['no_eligible_lane']:
            assert not new and rows==original and tracks==read(SOURCE/case/'tracks.json')
            assert audit['baseline_equivalent_inputs']
        else:
            document=read(audit['raw_outcome_path']);assert sha(audit['raw_outcome_path'])==audit['raw_outcome_sha256']
            fresh=common.integrate_case(case,document,panel['slots'],packbyid,math,adapter)
            assert fresh['observations']==ledger['observations'] and fresh['staged']==ledger['staged']
            assert fresh['counts']==ledger['counts'] and fresh['packet_reconstructions']==2*case_nom[case]['paired_windows']
            assert audit['bank_support']['reuse_allowed'] and audit['bank_support']['complete_causal_catalogue']
        for addition in ledger['staged']:
            assert addition['target_observation_id'] in new and addition['native']==native[addition['target_observation_id']]
            assert len({d['native_observation_id'] for d in addition['donors']})==addition['donor_count']
            candidates.append({k:addition[k] for k in ('case','prediction_id','target_observation_id','channel','native_receiver_id','donor_count','zero_fft_bin','innovation_hz','width_exceeds_wrong_pilot_control')})
        summary.append(dict(case=case,eligible_lane=case_nom[case]['eligible'],baseline_equivalent=audit['baseline_equivalent_inputs'],
            original_GLRT_count=len(original),total_GLRT_count=len(rows),added_native=len(new),new_in_graph=audit['new_in_graph'],new_curved_graph=audit['new_in_curved_graph'],
            new_outside_graph=audit['new_outside_graph'],observations_sha256=sha(folder/'observations.json'),tracks_sha256=sha(folder/'tracks.json'),
            graph_terminal_sha256=sha(folder/'terminal_seal.json'),raw_status='complete' if case_nom[case]['eligible'] else 'no_eligible_lane',
            added_native_ids=sorted(new)))
    totals={k:sum(r[k] for r in summary) for k in ('original_GLRT_count','total_GLRT_count','added_native','new_in_graph','new_curved_graph','new_outside_graph')}
    mechanism=dict(new_native=len(candidates),zero_fft_bins=sum(r['zero_fft_bin'] for r in candidates),
        donor_count_distribution=dict(collections.Counter(str(r['donor_count']) for r in candidates)),
        width_exceeds_wrong_pilot_control=sum(r['width_exceeds_wrong_pilot_control'] for r in candidates),
        nonzero_innovations=sum(not r['zero_fft_bin'] for r in candidates))
    write(HERE/'coherent_candidate_pre_geography_audit.json',dict(all_passed=True,cases=summary,totals=totals,mechanism=mechanism,
        exact1850_forecast_replays=forecast_checks,response_redaction_checks=forecast_checks,
        intended_held_scans=12,eligible_held_scans=sum(r['eligible_lane'] for r in summary),
        native_source_original_donor_admission_selection_support_and_graph_inputs_verified=True,
        no_sparse_R02_or_coherent_union=True,IQ_calls=0,new_position_fit_calls=0,geographic_errors_opened=False,
        raw_protocol_sha256=sha(BROADER/'raw/protocol.json'),graph_protocol_sha256=sha(BROADER/'graph_protocol_v2.json'),
        nomination_audit_sha256=sha(HERE/'nomination_audit.json'),seconds=time.monotonic()-began))
    write(HERE/'held_new_native_mechanism.json',dict(rows=candidates,summary=mechanism,scope='All newly admitted coherent native owners before position selection',
        independent_precision_or_satellite_identity_claim=False))
    print(dict(all_passed=True,totals=totals,mechanism=mechanism),flush=True)


if __name__=='__main__':main()
