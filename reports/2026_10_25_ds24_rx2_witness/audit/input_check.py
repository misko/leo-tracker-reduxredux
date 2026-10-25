"""Independent complete-pool reconstruction using whitelisted metadata only."""
import hashlib
import json
import time
from pathlib import Path

OLD=Path('/srv/bulk/leo/research/ds24-identity-support-r01/witness')
def read(p):return json.loads(Path(p).read_bytes())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def check_inputs():
    protocol=read(OLD/'protocol02.json');bindings=protocol['input_bindings'];checks=[]
    def check(name,passed,**detail):checks.append(dict(name=name,passed=bool(passed),**detail))
    check('original metadata-authority inputs immutable',
          all(sha(item['path'])==item['sha256'] for item in bindings.values()))
    tracks=read(bindings['tracks']['path'])
    # Project metadata before comparing; no values, graph labels or aliases are
    # consulted in this independent selection reconstruction.
    metadata=[{k:row[k] for k in ('key','receiver','channel','rf_hz','times','observation_ids')} for row in tracks]
    parent=read(bindings['parent']['path'])
    node=parent['selected']['node'] if parent['accepted'] else parent['baseline_node']
    curved={row['component'] for row in node['seed']['rows'] if row['active_curvature']}
    ownership=read(bindings['ownership']['path'])
    accepted={a:set(ownership['coverage'][a]['accepted_observation_ids']) for a in ('c0','fitted_c')}
    historical=next(row for row in read(bindings['old_reference_inventory']['path'])['rows'] if row['case']=='DS24-0013')
    references=[historical['target']]+historical['other_same_family_raw_sources']
    old_ids={oid for row in references for oid in row['observation_ids']}
    selected=[]
    for row in sorted(metadata,key=lambda r:(min(r['times']),r['channel'],r['key'])):
        ids=set(row['observation_ids'])
        if row['receiver']==2 and row['key'] in curved and not ids&old_ids and not any(ids&v for v in accepted.values()):
            selected.append(row)
    frozen=read(OLD/'whole_scan_inventory.json')['selected']
    check('all eligible RX2 owners selected without replacement',
          [r['key'] for r in selected]==[r['component'] for r in frozen] and len(selected)==3)
    for row,old in zip(selected,frozen,strict=True):
        check('complete native source order/time/RF unchanged',
              row['observation_ids']==old['observation_ids'] and row['times']==old['times_s'] and
              row['rf_hz']==old['rf_hz'] and row['channel']==old['channel'],component=row['key'])
    ids=[oid for row in selected for oid in row['observation_ids']]
    check('all124 native IDs mutually disjoint and outside both parent/historical ledgers',
          len(ids)==len(set(ids))==124 and not set(ids)&old_ids and
          not any(set(ids)&v for v in accepted.values()))
    source=Path(bindings['tracks']['path']).parent
    native={row['observation_id']:{k:row[k] for k in ('receiver','channel','actual_rf_hz','time_s')}
            for row in read(source/'observations.json')}
    check('native observation metadata agrees point-for-point',all(
          native[oid]==dict(receiver=row['receiver'],channel=row['channel'],actual_rf_hz=row['rf_hz'],time_s=stamp)
          for row in selected for oid,stamp in zip(row['observation_ids'],row['times'],strict=True)))
    receipt=read(source/'receipt.json');elements=read(source/'nominal_elements.json')
    check('all1487 catalogue elements are causal',len(elements)==1487 and all(
          max(row['provenance']['element_epoch_utc_ns'],row['provenance']['collected_utc_ns'])<=receipt['cutoff_utc_ns']
          for row in elements.values()))
    return checks


if __name__=='__main__':
    here=Path(__file__).resolve().parent;output=here/'input_check.json'
    if output.exists():raise FileExistsError('preserve input audit receipt')
    started=time.monotonic();checks=check_inputs();elapsed=time.monotonic()-started
    receipt=dict(all_passed=all(row['passed'] for row in checks),checks=checks,
        source_sha256=sha(__file__),seconds=elapsed,propagation_calls=0,
        CFO_scores_computed=0,position_fits=0,geographic_truth_read=False,
        observation_access='metadata keys only after JSON parsing; no frequency-value comparison')
    output.write_text(json.dumps(receipt,indent=2,allow_nan=False)+'\n')
    print(json.dumps(dict(path=str(output),all_passed=receipt['all_passed'],seconds=elapsed)))
