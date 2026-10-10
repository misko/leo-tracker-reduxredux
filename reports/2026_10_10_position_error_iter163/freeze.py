"""Metadata-only binding of sealed controls for symmetric calibration starts."""
import copy
import hashlib
import json
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent/'2026_10_10_position_error_iter162'
AUTHORITY_SHA = '03fc06dd6a29cf1b26930bf298a37d3af8630323bbfb04c9594f60d414c3eb81'
INTEGRITY_SHA = '72362fc62167c08e79fc14799a574c3bb61dbce4820398bc290b77923a1e45e1'
CONTROL_DIGEST = 'sha256:03d0a25414d0da5d10469e5df8e358f44b64fd4976ff3c75a2d670cd8817c8e6'
INTERPRETER = '/opt/leo-tracker/releases/47e2705e437722daa5e6d6bb1c252d54b7a21dbc/.venv/bin/python'
POLICY = dict(members=12, hypotheses=['zero-c','fitted-c'], modes=['train0','train1'],
    arms=['zero-c','fitted-c'], starts=['zero-c','fitted-c'], maximum_fits=192,
    selected_receipts=96, new_receipts=288, workers=2, threads=1, shards=2, retries=0,
    maximum_seconds=90, maximum_iterations=600, timing_half_width_s=20,
    fixed_position=True, slope_half_width_hz_s=60, local_radius_km=25,
    local_center='hypothesis-position', seed='ordinary161-full-states-position-replaced',
    zero_c_projection='static-c-and-both-rf-time-coefficients-zero',
    stationarity_tolerance=.001, objective_tolerance=1e-6,
    selection_tolerance=1e-6, selection_order=['control','zero-c','fitted-c'],
    preference_tolerance=1e-6, physical_metadata='original-full-observations',
    prior_scaling='unchanged', references_before_all_terminal=False)
SOURCE_FILES = ('freeze.py','run.py','fit_core.py','selection.py',
                'test_freeze.py','test_run.py','test_fit_core.py','test_selection.py')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_control(receipt, claim, label, hypothesis, mode, arm):
    identity = dict(label=label,hypothesis=hypothesis,mode=mode,arm=arm,
                    protocol_sha256=CONTROL_DIGEST)
    if any(receipt.get(k)!=v or claim.get(k)!=v for k,v in identity.items()):
        raise ValueError('foreign162 control receipt/claim')
    if receipt.get('status')!='qualified' or receipt.get('audit',{}).get('qualified') is not True:
        raise ValueError('unavailable control; preserve failure, never omit member')


def prepare():
    """Return a verified plan without writing or invoking scientific code."""
    authority, integrity_path = PRIOR/'protocol.json', PRIOR/'REPORT_INTEGRITY.json'
    if sha(authority)!=AUTHORITY_SHA or sha(integrity_path)!=INTEGRITY_SHA:
        raise ValueError('published162 authority changed')
    integrity = json.loads(integrity_path.read_text())
    if integrity.get('protocol.json')!=AUTHORITY_SHA:
        raise ValueError('162 publication protocol differs')
    for name, expected in integrity.items():
        if sha(PRIOR/name)!=expected:
            raise ValueError('162 publication changed: '+name)
    previous = json.loads(authority.read_text())
    plan = {k:copy.deepcopy(previous[k]) for k in
            ('members','source_sha256','input_sha256','runtime')}
    for group in ('source_sha256','input_sha256'):
        for name,expected in plan[group].items():
            if sha(ROOT/name)!=expected:
                raise ValueError('inherited162 artifact changed: '+name)
    if plan['runtime']['interpreter']!=INTERPRETER:
        raise ValueError('immutable47e required')
    for name,expected in plan['runtime']['sha256'].items():
        if sha(name)!=expected:raise ValueError('runtime changed: '+name)
    labels=[m['label'] for m in plan['members']]
    if len(labels)!=12 or len(set(labels))!=12:
        raise ValueError('exact twelve inherited members required')
    summary=json.loads((PRIOR/'SUMMARY.json').read_text())
    if summary['protocol_sha256']!=CONTROL_DIGEST:raise ValueError('foreign162 summary')
    hashes=summary['raw_sha256']
    keys=[h+'--'+m+'--'+a for h in POLICY['hypotheses'] for m in POLICY['modes'] for a in POLICY['arms']]
    expected_names={label+'/'+name for label in labels for name in
                    ('claim.json','result.json',*[k+s for k in keys for s in ('.json','.claim.json')])}
    if set(hashes)!=expected_names:raise ValueError('162 raw inventory differs')
    with tarfile.open(PRIOR/'raw-receipts.tar.gz','r:gz') as archive:
        entries=archive.getmembers()
        if len(entries)!=len(expected_names) or {e.name for e in entries}!=expected_names:
            raise ValueError('162 archive inventory differs')
        for entry in entries:
            if not entry.isfile() or hashlib.sha256(archive.extractfile(entry).read()).hexdigest()!=hashes[entry.name]:
                raise ValueError('162 archive receipt differs: '+entry.name)
    for member in plan['members']:
        member['controls']={}
        for h in POLICY['hypotheses']:
            for m in POLICY['modes']:
                for a in POLICY['arms']:
                    key=h+'--'+m+'--'+a
                    paths=[PRIOR/'results'/member['label']/(key+s) for s in ('.json','.claim.json')]
                    for path in paths:
                        name=str(path.relative_to(PRIOR/'results'))
                        if sha(path)!=hashes[name]:raise ValueError('local control differs: '+name)
                        plan['input_sha256'][str(path.relative_to(ROOT))]=hashes[name]
                    receipt,claim=[json.loads(p.read_text()) for p in paths]
                    validate_control(receipt,claim,member['label'],h,m,a)
                    member['controls'][key]=dict(raw_path=str(paths[0].relative_to(ROOT)),sha256=sha(paths[0]),
                        claim_path=str(paths[1].relative_to(ROOT)),claim_sha256=sha(paths[1]),protocol_sha256=CONTROL_DIGEST)
    for name in SOURCE_FILES:
        path=HERE/name;plan['source_sha256'][str(path.relative_to(ROOT))]=sha(path)
    plan['input_sha256'][str(authority.relative_to(ROOT))]=AUTHORITY_SHA
    plan['input_sha256'][str((HERE/'PLAN.md').relative_to(ROOT))]=sha(HERE/'PLAN.md')
    plan.update(policy=copy.deepcopy(POLICY),control_protocol_digest=CONTROL_DIGEST,
        preparation_provenance_sha256={str(p.relative_to(ROOT)):sha(p) for p in
            (integrity_path,PRIOR/'SUMMARY.json',PRIOR/'raw-receipts.tar.gz')},
        scope='Consumed symmetric calibration-start sensitivity; no independent validation')
    return plan


if __name__=='__main__':
    raise SystemExit('Preparation only; root review before freeze')
