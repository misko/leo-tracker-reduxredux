"""Export an explicit compact capsule, pinning large local numerical products."""
import hashlib,json,shutil
from pathlib import Path
from datetime import datetime,UTC

SOURCE=Path(__file__).parent
TARGET=Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022/reports/2026_10_23_ds24_fast10m')
def digest_bytes(b):return 'sha256:'+hashlib.sha256(b).hexdigest()
def pin(p):return dict(path=str(p),bytes=p.stat().st_size,sha256=digest_bytes(p.read_bytes()))
def write(p,d):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(d,indent=2,allow_nan=False)+'\n')
def gates(rows):
    return dict(total=len(rows),compatible=sum(r.get('compatible') is True for r in rows),
                failed=[{k:v for k,v in r.items() if k!='observation_ids'} for r in rows if r.get('compatible') is not True])
def arm(a):
    keys=('endpoint_east_north_km','endpoint_latlon','negative_twice_elbo','curved_negative_twice_elbo','RMS_hz','active_points','predictive_points','linear_calibration_max_difference','final_phase_change_s','temporal_contrast_objective','position_frozen','objective_used_for_optimization')
    d={k:a[k] for k in keys if k in a}
    d['curved_gates']=gates(a.get('gates',{}).get('tracks',[]))
    d['linear_gates']=gates(a.get('linear_gates',[]))
    return d
def coverage(c):
    d={k:v for k,v in c.items() if isinstance(v,(str,int,float,bool)) or v is None}
    ids=c.get('accepted_observation_ids',[])
    d['accepted_observation_ids_count']=len(ids)
    d['accepted_observation_ids_sha256']=digest_bytes(json.dumps(sorted(ids),separators=(',',':')).encode())
    return d
def compact(d):
    out={k:v for k,v in d.items() if k!='methods'};out['methods']={}
    for name,m in d.get('methods',{}).items():
        r={k:v for k,v in m.items() if not isinstance(v,(dict,list))}
        for key in ('arms','candidate_arms'):r[key]={k:arm(a) for k,a in m.get(key,{}).items()}
        for key in ('coverage','candidate_coverage'):r[key]={k:coverage(c) for k,c in m.get(key,{}).items()}
        out['methods'][name]=r
    return out

def main():
    TARGET.mkdir(parents=True,exist_ok=True)
    names=['README.md','RESULTS.md','manifest.json','manifest.sha256','sample.json','seal.json','discovery_preliminary.json','acquisition_start_audit.json','evaluation_reference.json','readiness_audit.json','study_protocol.json','summary.json','baseline_execution.json','variants_execution.json','output_audit.json','first_native_covariance_audit.json','first_inference_read_audit.json','engine_completion.json','prepared_input_audit.json','physical_id_audit.json','legacy_supervisor_guard.json']
    names += [p.name for p in SOURCE.glob('study_amendment_*.json')]
    names += [p.name for p in SOURCE.glob('*.py') if p.name not in ('inspect_failed_native.py',)]
    names += [str(p.relative_to(SOURCE)) for sub in ('engine','contrast','reporting','tables','figures') for p in (SOURCE/sub).glob('*') if p.is_file() and p.suffix in ('.py','.json','.csv','.png','.svg','.pdf')]
    for name in sorted(set(names)):
        src=SOURCE/name
        if src.exists():
            dst=TARGET/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
    members=json.loads((SOURCE/'sample.json').read_text())['selected'];raw=[]
    for m in members:
        case=m['dataset_label'];p=SOURCE/'results'/f'{case}.json'
        if p.exists():
            d=json.loads(p.read_bytes());write(TARGET/'compact_results'/f'{case}.json',compact(d));raw.append(pin(p))
        else:
            receipt=SOURCE/case/'input_receipt.json'
            d=json.loads(receipt.read_bytes()) if receipt.exists() else dict(status='result_not_present_at_export')
            write(TARGET/'compact_results'/f'{case}.json',dict(case=case,result_available=False,input_receipt=d))
        for name in ('input_receipt.json','preparation_receipt.json'):
            src=SOURCE/case/name
            if src.exists():dst=TARGET/'case_receipts'/case/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
        for name in ('result.json','algo02_result.json','graph.json','observations.json','tracking.json'):
            src=SOURCE/case/name
            if src.exists():raw.append(pin(src))
    for p in (SOURCE/'attempts').glob('*.json'):
        write(TARGET/'compact_attempts'/p.name,compact(json.loads(p.read_bytes())));raw.append(pin(p))
    write(TARGET/'publication_receipt.json',dict(created_utc=datetime.now(UTC).isoformat(),dataset_id='DS24',full_result_artifacts_copied=False,
          retained_bulk_artifacts=raw,compact_result_members=len(members),raw_bulk_root=str(SOURCE),
          compact_omissions=['state vectors','optimizer histories','covariance arrays','per-observation repeated identifiers; sorted accepted-ID hashes retained'],
          published_files=[dict(path=str(p.relative_to(TARGET)),**{k:v for k,v in pin(p).items() if k!='path'}) for p in sorted(TARGET.rglob('*')) if p.is_file() and p.name!='publication_receipt.json']))
    print('exported',len(members),'compact members;',len(raw),'pinned bulk products')
if __name__=='__main__':main()
