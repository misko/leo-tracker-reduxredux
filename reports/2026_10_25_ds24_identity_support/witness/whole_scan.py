"""Separate whole-scan metadata question: drop only the time-support restriction."""
import csv
import hashlib
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent


def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p,value):
    with Path(p).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')


def classify(row):
    reasons=[]
    if row['receiver']!='RX2':reasons.append('receiver is not RX2')
    if not row['canonical_curved']:reasons.append('not a canonical curved graph owner')
    if any(row['original_accepted_ID_overlap'].values()):reasons.append('overlaps complete original accepted IDs; no trimming')
    if row['reused_reference_IDs']:reasons.append('reuses previously tested reference IDs')
    return dict(whole_scan_eligible=not reasons,whole_scan_exclusion_reasons=reasons)


def main():
    began=time.monotonic()
    # New question explicitly frozen before its metadata projection; no CFO.
    protocol=dict(question='Unused whole-scan curved RX2 sources for later orbit-hypothesis feasibility, distinct from simultaneous calibration/witness availability',
        scope_change='drop ONLY interval-overlap/native-grid-adjacency requirement; retain receiver/curvature/complete ownership rules',
        selection='ALL eligible complete owners, sorted start/channel/component; no candidate/alias/CFO/label score use',
        previous_time_supported_primary_result_preserved=0,expected_complete_pool=3,
        source_sha256=sha(__file__),test_sha256=sha(HERE/'test_whole_scan.py'),
        input_inventory_sha256=sha(HERE/'inventory.json'),input_report_seal_sha256=sha(HERE/'report_seal.json'),
        maximum_metadata_seconds=120,geometry_computation_authorized=False,
        new_RF_scores=0,position_fits=0,GPS_used=False)
    write(HERE/'whole_scan_protocol.json',protocol)
    old=json.loads((HERE/'inventory.json').read_text())
    assert old['counts']['primary_eligible']==0
    rows=[]
    for row in sorted(old['rows'],key=lambda r:(r['start_s'],r['channel'],r['component'])):
        flags=classify(row)
        rows.append({k:row[k] for k in ('component','receiver','channel','rf_hz','points','start_s','end_s','times_s','observation_ids','canonical_curved','original_accepted_ID_overlap','reused_reference_IDs','primary_eligible','reference_time_RF_relations')}|flags)
    selected=[r for r in rows if r['whole_scan_eligible']]
    assert len(selected)==3
    ids=[i for r in selected for i in r['observation_ids']]
    assert len(ids)==len(set(ids))
    elapsed=time.monotonic()-began
    if elapsed>120:raise TimeoutError('whole-scan metadata cap')
    assert sha(HERE/'inventory.json')==protocol['input_inventory_sha256']
    output=dict(rows=rows,selected=selected,selected_count=len(selected),selected_distinct_native_IDs=len(ids),
        original_time_supported_primary_count=0,seconds=elapsed,
        protocol_sha256=sha(HERE/'whole_scan_protocol.json'),
        geometry_or_CFO_compared=False,new_RF_scores=0,position_fits=0,GPS_used=False)
    write(HERE/'whole_scan_inventory.json',output)
    with (HERE/'whole_scan_selected.csv').open('x',newline='') as f:
        keys=['component','receiver','channel','rf_hz','points','start_s','end_s']
        writer=csv.DictWriter(f,fieldnames=keys,lineterminator='\n');writer.writeheader()
        writer.writerows({k:r[k] for k in keys} for r in selected)
    write(HERE/'whole_scan_seal.json',dict(files={n:sha(HERE/n) for n in ('whole_scan.py','test_whole_scan.py','whole_scan_protocol.json','whole_scan_inventory.json','whole_scan_selected.csv')},
        prior_report_seal_sha256=sha(HERE/'report_seal.json'),new_RF_scores=0))
    print(json.dumps(dict(selected=[{k:r[k] for k in ('component','points','start_s','end_s','rf_hz')} for r in selected],
        distinct_native_IDs=len(ids),seconds=elapsed),indent=2))


if __name__=='__main__':main()
