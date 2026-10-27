"""Replay original RF-only lane/block rule for all24; no IQ/geography."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
R01=Path('/srv/bulk/leo/research/ds24-missed-visit-r01')
BROADER=HERE.parent/'broader'
HELD=Path('/srv/bulk/leo/research/ds24-missed-visit-r02/validation/held_graph')
SOURCE=Path('/srv/bulk/leo/research/ds25-20261024')
sys.path.insert(0,str(R01/'validation'))
from baseline_scope import metadata_inventory


def read(path):
    with (gzip.open(path,'rt') if str(path).endswith('.gz') else Path(path).open()) as f:return json.load(f)
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')


def main():
    spec=importlib.util.spec_from_file_location('original_coherent_selection',R01/'expansion/prediction/selection.py')
    selection=importlib.util.module_from_spec(spec);spec.loader.exec_module(selection)
    split=read(R01/'split.json');nominations=read(BROADER/'nominations.json');actual_pairs=read(BROADER/'nominated_pairs.json')
    actual_cases={c['case']:c for c in nominations['cases']};assert set(actual_cases)==set(split['development']+split['validation'])
    for path,h in nominations['source_inputs'].items():assert sha(path)==h,path
    expected_blocks=[];expected_pairs=[];rows=[]
    for case,actual in actual_cases.items():
        tracking,inventory,original=metadata_inventory(case)
        if case in split['development']:
            ledger=read(R01/'validation'/(case+'_additions.json'))
            graphpath=R01/'validation'/(case+'-additions-r01')/'graph_audit.json'
            curved=set(read(graphpath)['graph']['curved_observation_ids']) if ledger['staged'] else set()
        else:
            job=read(HELD/'jobs/r01_search'/(case+'.json'));audit=read(HELD/'graphs/r01_search'/case/'audit.json')
            ledger=dict(case=case,staged=[dict(status='new_native_exploratory_addition',existing_owner=False,
                target_observation_id=c['native']['observation_id'],channel=c['native']['channel'],native_receiver_id=c['native']['native_receiver_id'],native=c['native']) for c in job['candidates']])
            curved=set(audit['new_curved_ids'])
        ranked=selection.lanes(ledger,curved);assert ranked==actual['ranked_lanes'],case
        blocks=[selection.nominate(lane,tracking['source']['probes'],tracking['source']['sample_rate_hz']) for lane in ranked[:2]]
        pairs=selection.deduplicate(blocks);assert len(pairs)==actual['paired_windows']
        assert len(ranked)==actual['eligible_lanes'] and len(blocks)==actual['selected_lanes']
        expected_blocks.extend(blocks);expected_pairs.extend(pairs)
        rows.append(dict(case=case,cohort='held' if case in split['validation'] else 'development',eligible=bool(ranked),
            selected_lanes=len(blocks),paired_windows=len(pairs),status=actual['status']))
    assert expected_blocks==nominations['blocks']
    key=lambda p:(p['case'],p['probe']['visit_index'])
    assert {key(p):p for p in expected_pairs}=={key(p):p for p in actual_pairs}
    assert len(actual_pairs)==nominations['paired_windows']==925 and nominations['receiver_cells']==1850
    oldblocks=read(R01/'expansion/prediction/blocks.json')['blocks']
    assert [b for b in expected_blocks if b['case'] in ('DS24-0011','DS24-0097')]==oldblocks
    forecast_protocol=read(BROADER/'forecast_protocol.json')
    for path,h in forecast_protocol['files'].items():assert sha(path)==h,path
    assert forecast_protocol['metadata_handoff_version']==2 and forecast_protocol['no_recovered_donor_feedback']
    current=read(BROADER/'prediction_packets_v2.json');old=read(R01/'expansion/prediction/prediction_packets_v2.json')
    by_owner=lambda r:(r['header']['case'],r['header']['receiver_id'],r['header']['start_counter'])
    current_rows={by_owner(r):r for r in current['rows']}
    for row in old['rows']:assert current_rows[by_owner(row)]==row
    reused=read(BROADER/'reuse_audit.json');assert reused['all_passed']
    for record in reused['cases']:
        assert sha(record['outcome_path'])==record['outcome_sha256']
        assert sha(record['upstream_protocol_path'])==record['upstream_protocol_sha256']
        assert record['exact_panel_and_serialized_forecast_equality'] and record['native_IQ_hashes_and_full_reader_exhaustion_verified']
    held_rows=[r for r in rows if r['cohort']=='held']
    write(HERE/'nomination_audit.json',dict(all_passed=True,cases=rows,
        original_lane_ranking_seed_window_cap_and_pair_dedup_exact=True,
        cases_total=len(rows),eligible_cases=sum(r['eligible'] for r in rows),
        intended_held=len(held_rows),held_eligible=[r['case'] for r in held_rows if r['eligible']],
        held_baseline_no_eligible=[r['case'] for r in held_rows if not r['eligible']],
        held_paired_windows=sum(r['paired_windows'] for r in held_rows),all_paired_windows=len(actual_pairs),
        old526_forecast_rows_exact=True,old_four_blocks_exact=True,metadata_handoff_v2=True,no_recovered_donor_feedback=True,
        IQ_calls=0,new_position_fit_calls=0,geographic_errors_opened=False,
        nominations_sha256=sha(BROADER/'nominations.json'),forecast_protocol_sha256=sha(BROADER/'forecast_protocol.json'),
        reuse_audit_sha256=sha(BROADER/'reuse_audit.json'),evaluation_protocol_sha256=sha(HERE/'protocol_v2.json')))
    print(dict(all_passed=True,eligible_cases=sum(r['eligible'] for r in rows),held_eligible=[r['case'] for r in held_rows if r['eligible']],
        held_baseline_no_eligible=[r['case'] for r in held_rows if not r['eligible']],old526_forecast_rows_exact=True),flush=True)


if __name__=='__main__':main()
