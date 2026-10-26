"""Compact publication tables and local hash seal; no scientific reruns."""
import csv
import hashlib
import json
from pathlib import Path
import time

HERE=Path(__file__).resolve().parent
def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,allow_nan=False);f.write('\n')
def table(path,rows):
    with Path(path).open('x') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)


def main():
    audit=read(HERE/'interval_audit_v2.json')
    by_index={r['index']:r for r in audit['rows'] if r['source']=='synthetic'}
    rows=[]
    for i,r in enumerate(read(HERE/'synthetic.json')['rows']):
        e=r['evaluation'];p=r['estimate']['primary'];q=p['proposed'];a=by_index[i]
        rows.append(dict(index=i,edge=r['edge'],db=r['db'],true_rate_hz_s=r['true_rate_hz_s'],
            donor_error_hz=r['donor_error_hz'],forecast=r['forecast'],repetition=r['repetition'],
            target_sha256=r['target_sha256'],truth_cfo_hz=r['truth_cfo_hz'],
            predicted_cfo_hz=p['predicted_cfo_hz'],gate_margin=p['gate_statistic'],gate=p['passed_gate'],
            proposal_cfo_hz=q['cfo_hz'],proposal_modes=len(q['modes']),
            **{m+'_error_hz':e['errors_hz'][m] for m in ['unchanged','carry','proposal']},
            **{m+'_accurate':e['accurate'][m] for m in ['unchanged','carry','proposal']},
            original_interval_low_offset_hz=a['original_interval_offsets_hz'][0],
            original_interval_high_offset_hz=a['original_interval_offsets_hz'][1],
            bin_density_interval_low_offset_hz=a['quantiles_offsets_hz']['bin_density'][0],
            bin_density_interval_high_offset_hz=a['quantiles_offsets_hz']['bin_density'][2],
            **{'coverage_'+k:v for k,v in a['coverage'].items()},
            actual_complex_residual_variance=p['statistics']['mean_symbol_residual_complex_variance'],
            uncertainty_weights_qualified=False))
    table(HERE/'synthetic_trials.csv',rows)
    rows=[]
    for r in read(HERE/'null.json')['rows']:
        hypotheses=r['estimate']['hypotheses']
        rows.append(dict(edge=r['edge'],trial=r['trial'],proposal_count=r['proposal_count'],
            later_sha256=r['later_sha256'],false_confirmation=r['false_confirmation'],
            gate_margins=json.dumps([h['gate_statistic'] for h in hypotheses]),
            proposed_cfo_hz=json.dumps([h['proposed']['cfo_hz'] for h in hypotheses]),
            conditional_sds_hz=json.dumps([h['proposed']['conditional_sd_hz'] for h in hypotheses]),
            uncertainty_weights_qualified=False))
    table(HERE/'null_trials.csv',rows)
    write(HERE/'execution.json',dict(schema='frequency-execution-receipt/v1',
        successful_numerical_jobs=read(HERE/'summary.json')['seconds'],
        numerical_worker_limit_seconds=580,maximum_simultaneous_workers=2,BLAS_threads=1,
        retained_failures=[dict(stage='initial prepare',error='PermissionError reading restricted inherited source input',
            resolution='Authorized sudo -n readonly access; no IQ/outcome read before freeze'),
            dict(stage='first offline report',error='ModuleNotFoundError: scipy',
                resolution='Report uses exact binomial bound/bisection; no installation or scientific change; test receipt preserved'),
            dict(stage='first findings/package patch',error='apply_patch rejected duplicate delete/add operations on STATUS.md',
                resolution='Patch rejected before mutation; split valid apply_patch operations')],
        scientific_failed_slots=0,natural_failed_prerequisite=True,
        no_new_RF=True,no_production_edits=True,no_git_mutations=True,
        frozen_estimator_and_scoring_sources_unchanged=True))
    omit={'synthetic.json','null.json','publication_manifest.json','RF_seal.json'}
    names=sorted(p.name for p in HERE.iterdir() if p.is_file() and p.name not in omit)
    names+=['publication_allowlist.json','RF_seal.json','publication_manifest.json']
    names=sorted(set(names))
    write(HERE/'publication_allowlist.json',dict(schema='frequency-lean-publication/v1',files=names,
        omit_full_local_grids=['synthetic.json','null.json'],raw_IQ_included=False,
        full_local_grid_hashes={n:sha(HERE/n) for n in ['synthetic.json','null.json']}))
    local=sorted(p for p in HERE.iterdir() if p.is_file() and p.name not in ['RF_seal.json','publication_manifest.json'])
    write(HERE/'RF_seal.json',dict(schema='frequency-local-artifact-seal/v1',sealed_utc_ns=time.time_ns(),
        files={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in local},
        decision='RF_NOT_QUALIFIED',raw_IQ_included=False,independent_added_Doppler_points=0,
        uncertainty_weights_qualified=False,position_calls=0,
        historical_inputs_bound_by='protocol.json',
        natural_inputs_bound_by='natural_protocol.json and natural_packets.json',
        interval_correction_bound_by='interval_audit_v2_protocol.json'))
    publish=[HERE/n for n in names if n!='publication_manifest.json']
    write(HERE/'publication_manifest.json',dict(schema='frequency-publication-manifest/v1',
        files={p.name:dict(sha256=sha(p),bytes=p.stat().st_size) for p in publish},
        total_bytes=sum(p.stat().st_size for p in publish),
        full_local_artifact_seal_sha256=sha(HERE/'RF_seal.json'),
        no_raw_IQ=True,immutable_full_local_outcomes_retained=True))
    print('sealed',sha(HERE/'RF_seal.json'),'published bytes',sum(p.stat().st_size for p in publish),flush=True)


if __name__=='__main__':main()
