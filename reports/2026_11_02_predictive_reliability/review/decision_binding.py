"""Bind sealed RF decisions to frozen sources, inputs and replayed cell rows."""
import hashlib,json
from pathlib import Path

ROOT=Path(__file__).resolve().parent;BASE=ROOT.parent
def read(p):return json.loads(Path(p).read_text())
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def main():
    protocol=read(BASE/'protocol.json');decisions=read(BASE/'decisions.json');audit=read(ROOT/'final_audit.json')
    results=read(BASE/'predictive/results.json');plan=read(BASE/'predictive/plan.json');issues=[]
    def check(ok,label):
        if not ok:issues.append(label)
    check(sha(BASE/'decisions.json')==(BASE/'decisions.sha256').read_text().split()[0],'decision seal')
    check(decisions['protocol_sha256']==sha(BASE/'protocol.json')==audit['protocol_sha256'],'protocol binding')
    check(decisions['results_sha256']==sha(BASE/'predictive/results.json')==audit['results_sha256'],'results binding')
    check(decisions['reducer_sha256']==sha(BASE/'decision.py')==protocol['source_sha256'][str((BASE/'decision.py').resolve())],'frozen reducer binding')
    check(decisions['geography_read'] is False,'geography-free RF seal')
    check(audit['status']=='passed' and audit['completed_endpoint_replays']==68,'complete fixed-endpoint audit')
    roster={r['case']:r for r in protocol['cases']};plans={r['case']:r for r in plan['cases']}
    for item in audit['decisions']:
        value=dict(item);case=value.pop('case')
        check(value==decisions['cases'][case],'frozen reducer exact replay: '+case)
    for case,record in roster.items():
        for key in ('family','seed','input_path','input_sha256'):
            check(record[key]==plans[case][key],'plan/roster '+key+': '+case)
        check(sha(record['input_path'])==record['input_sha256'],'native input: '+case)
        check(sha(record['previous_RF_receipt'])==record['previous_RF_receipt_sha256'],'conditioning RF receipt: '+case)
    for row in results['rows']:
        p=next(p for p in plans[row['case']]['partitions'] if p['name']==row['split'])
        check(row['kind']==p['kind'] and row['target_family']==roster[row['case']]['family'],'cell identity/split metadata')
    for path,digest in protocol['source_sha256'].items():check(sha(path)==digest,'frozen source: '+path)
    out=dict(status='passed' if not issues else 'failed',issues=issues,scope='Seal/source/record binding; no numerical fitting or geography computation',
        decisions_sha256=sha(BASE/'decisions.json'),protocol_sha256=sha(BASE/'protocol.json'),
        final_endpoint_audit_sha256=sha(ROOT/'final_audit.json'),held_leakage_audit_sha256=sha(ROOT/'leakage_audit.json'),
        review_source_sha256=sha(Path(__file__)),verdicts={c:v['verdict'] for c,v in decisions['cases'].items()},
        qualified_partitions={c:v['qualified_partitions'] for c,v in decisions['cases'].items()},
        numeric_workers_joined=results['all_workers_joined'],all_frozen_sources_and_inputs_unchanged=not issues)
    (ROOT/'decision_binding.json').write_text(json.dumps(out,indent=2)+'\n')
    print(json.dumps(out))

if __name__=='__main__':main()
