"""Audit provenance and compare the fit against both qualified controls."""
import hashlib
import json
from pathlib import Path

from run import HERE, REPORTS, module, read


def main(filename='result.json'):
    result=read(HERE/filename)
    for name,digest in result['hashes'].items():
        assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,name
    geometry=module('union_summary',REPORTS/'2026_09_29_ds8_union40/summarize.py')
    controls={
        'original_rank':read(REPORTS/'2026_09_29_ds8_union40/rank.json')['fit'],
        'corrected':read(REPORTS/'2026_09_29_ds8_union_timing/refit_old.json')['fit']}
    fit=result['fit']
    summary=dict(qualified=fit['qualified'],message=fit['message'],elapsed_seconds=result['elapsed_seconds'],
                 projected_gradient=fit['projected_gradient'],gradient_audit=fit['gradient_audit'])
    if fit['qualified']:
        summary.update(reference_distance_m=geometry.distance(fit['estimate_deg'],geometry.REFERENCE),
                       controls={name:dict(endpoint_gap_m=geometry.distance(fit['estimate_deg'],c['estimate_deg']),
                                            training_gain=fit['score']-c['score'],held_gain=fit['held_score']-c['held_score'])
                                 for name,c in controls.items()})
    output='centered-summary.json' if filename=='centered-result.json' else 'summary.json'
    (HERE/output).write_text(json.dumps(summary,indent=2,allow_nan=False)+'\n')
    print(json.dumps(summary,indent=2))


if __name__=='__main__':
    import sys
    main(*sys.argv[1:])
