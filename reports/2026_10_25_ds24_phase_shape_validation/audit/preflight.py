"""Independent metadata/saved-array preflight; no orbit or estimator imports."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
import numpy as np
from audit_math import observation_interaction

HERE=Path(__file__).resolve().parent
S=HERE.parent/'synthetic'
OLD=Path('/srv/bulk/leo/research/ds24-fast-identifiability-r01/synthetic')
PREV=Path('/srv/bulk/leo/research/ds24-identity-components-r01/synthetic')


def read(path):return json.loads(Path(path).read_text())
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def canonical(x):
    if isinstance(x,dict):return {str(k):canonical(v) for k,v in x.items()}
    if isinstance(x,(list,tuple,np.ndarray)):return [canonical(v) for v in x]
    if isinstance(x,np.generic):return x.item()
    return x
def fingerprint(x):return hashlib.sha256(json.dumps(canonical(x),sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def digest(ids,values):
    h=hashlib.sha256()
    for oid,value in sorted(zip(ids,values,strict=True)):
        h.update(str(oid).encode());h.update(b'\0');h.update(np.asarray(value,dtype='<f8').tobytes())
    return h.hexdigest()


def main():
    began=time.monotonic(); p=read(S/'protocol.json'); prep=read(S/'preparation.json')
    checks=[]; details=[]
    def check(name,ok,**data):
        checks.append(dict(test=name,passed=bool(ok),**data))
    check('protocol freeze',sha(S/'protocol.json')==read(S/'protocol_seal.json')['protocol_sha256'])
    for group in ('source_sha256','reused_original_bindings'):
        for path,expected in p[group].items():check('frozen binding',sha(path)==expected,path=path)
    for name in ('preparation','scientific_start'):
        check('top-level binding',sha(S/(name+'.json'))==p[name+'_sha256'],binding_name=name)
    old=read(OLD/'protocol.json')
    for group in ('input_sha256','source_sha256'):
        for path,expected in old[group].items():check('original source/input binding',sha(path)==expected,path=path)
    for item in prep['instances']:
        for key in ('truth_path','observations_npz_path'):
            check('new instance binding',sha(item[key])==item[key.replace('_path','_sha256')],path=item[key])
        truth=read(item['truth_path']); common=read(OLD/'fits'/item['case']/f"site{item['site']}"/item['variant']/'c0/generation.json')
        edges=np.r_[0,np.cumsum(common['coordinate_widths'])]; expected=np.asarray(common['selected_coefficients']).copy()
        if item['intervention']=='phase_at_causal_mean':
            phase=common['original_phase_locations_s']
        else:
            phase=common['true_phases_s'];expected[edges[3]:edges[4]]=0.
        check('exact generating intervention',np.array_equal(truth['true_phases_s'],phase) and
              np.array_equal(truth['selected_coefficients'],expected),case=item['case'],intervention=item['intervention'])
        check('geometry reference equals actual generating phase',np.array_equal(truth['phase_geometry_reference_s'],phase))
        for key in ('actual_noise_by_ID','noise_sigma_by_ID','noise_precision_by_track','seed_children',
                    'predictive_fragment_bias_hz','inference_model','inference_powers','curved_aliases','predictive_aliases'):
            if key in common:check('preserved common draw/input',fingerprint(truth[key])==fingerprint(common[key]),key=key)
        check('both c arms get same observations',truth['c_arm_input_fingerprints']['c0']==truth['c_arm_input_fingerprints']['fitted_c'])
        for arm,closure in truth['forward_closures'].items():
            check('saved forward closure',closure['maximum_known_forward_mean_identity_error_hz']<=1e-7,arm=arm,
                  error_hz=closure['maximum_known_forward_mean_identity_error_hz'])
        with np.load(item['observations_npz_path'],allow_pickle=False) as a:
            check('native observation hash',digest(a['observation_ids'],a['values_hz'])==truth['observations_sha256'])
    for row in prep['observation_factorials']:
        check('factorial array binding',sha(row['path'])==row['sha256'])
        with np.load(row['path'],allow_pickle=False) as a:
            vectors={cell:a['values_'+cell+'_hz'] for cell in ('11','10','01','00')}
            interaction=observation_interaction(*(vectors[c] for c in ('11','10','01','00')))
            check('native four-cell interaction exact',np.array_equal(interaction,a['interaction_hz']))
            check('shape and phase difference closure',np.array_equal(a['shape_effect_phase_on_hz'],vectors['11']-vectors['10']) and
                  np.array_equal(a['shape_effect_phase_off_hz'],vectors['01']-vectors['00']) and
                  np.array_equal(a['phase_effect_shape_on_hz'],vectors['11']-vectors['01']) and
                  np.array_equal(a['phase_effect_shape_off_hz'],vectors['10']-vectors['00']))
            common=read(OLD/'fits'/row['case']/f"site{row['site']}"/row['variant']/'c0/generation.json')
            check('full control observation digest',digest(a['observation_ids'],vectors['11'])==common['observations_sha256'])
            base=PREV/'instances'/row['case']/f"site{row['site']}"/row['variant']/'no_orbital_deviations/observations.npz'
            with np.load(base,allow_pickle=False) as b:
                check('old both-removed native vector exact',np.array_equal(a['observation_ids'],b['observation_ids']) and
                      np.array_equal(vectors['00'],b['values_hz']))
                use=b['used_by_position_likelihood']
            for cell,name in [('01','phase_at_causal_mean'),('10','shape_zero')]:
                new=S/'instances'/row['case']/f"site{row['site']}"/row['variant']/name/'observations.npz'
                with np.load(new,allow_pickle=False) as b:
                    check('new cell exact native vector',np.array_equal(a['observation_ids'],b['observation_ids']) and
                          np.array_equal(vectors[cell],b['values_hz']))
                with np.load(base,allow_pickle=False) as b,np.load(new,allow_pickle=False) as n:
                    check('unchanged IDs/times/labels/mask/aliases/roles',all(np.array_equal(b[k],n[k]) for k in b.files if k!='values_hz'))
            details.append(dict(case=row['case'],site=row['site'],variant=row['variant'],native_rows=len(interaction),
                likelihood_rows=int(use.sum()),all_row_interaction_RMS_hz=float(np.sqrt(np.mean(interaction**2))),
                likelihood_row_interaction_RMS_hz=float(np.sqrt(np.mean(interaction[use]**2))),
                maximum_interaction_hz=float(np.max(abs(interaction)))))
    env=dict(os.environ,PYTHONPATH='/tmp/algo03-feasible-deps:src:tools:/srv/bulk/leo/research/ds24-movement-policy-r01/recovery',
             OPENBLAS_NUM_THREADS='1',OMP_NUM_THREADS='1',MKL_NUM_THREADS='1')
    command=['.venv/bin/python','-B','-m','unittest','discover','-s',str(S),'-p','test_factorial.py','-v']
    tested=subprocess.run(command,cwd='/home/mouse9911/gits/leo-tracker-reduxredux',env=env,text=True,capture_output=True,timeout=30)
    check('six producer tests independently rerun',tested.returncode==0,output=tested.stdout+tested.stderr)
    check('explicit frozen task budget',p['maximum_position_fits']==32 and p['workers']==2 and p['BLAS_threads']==1 and
          p['per_fit_seconds']==180 and p['global_seconds_including_preparation']==600)
    # Source review: generation constructs make_event_problem at true phase then
    # recomputes geometry/features, whereas one_fit always starts references at0.
    check('reviewed generator/inference separation',True,source_sha256=sha(S/'factorial.py'),
          finding='shape coefficients preserved for phase removal; B and nonlinear Doppler recomputed at true phase; inference starts reference0 and uses unchanged control.build')
    receipt=dict(all_passed=all(c['passed'] for c in checks),protocol_sha256=sha(S/'protocol.json'),checks=checks,
                 observation_interaction_details=details,audit_source_sha256=sha(Path(__file__)),
                 seconds=time.monotonic()-began,position_fits=0,orbit_propagations=0,real_GPS_used=False)
    with (HERE/'synthetic_preflight.json').open('x') as f:json.dump(receipt,f,indent=2);f.write('\n')
    print(json.dumps(dict(all_passed=receipt['all_passed'],checks=len(checks),seconds=receipt['seconds'],
                         protocol_sha256=receipt['protocol_sha256'],details=details),indent=2))
    if not receipt['all_passed']:raise SystemExit(1)


if __name__=='__main__':main()
