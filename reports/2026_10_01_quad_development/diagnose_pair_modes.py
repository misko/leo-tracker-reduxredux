"""Score a quad solution under each pair objective without reference coordinates."""
import argparse
import json
from pathlib import Path
import numpy as np
from run_window import prepare_window
from regression_batch import digest, verify_sources

HERE = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(); parser.add_argument('block'); args = parser.parse_args()
    directory = HERE/'independent-v2'/args.block
    audit_path = directory/'evaluation.json'
    assert digest(audit_path) == audit_path.with_suffix('.sha256').read_text().strip()
    accepted = {r['unit']:r for r in json.loads(audit_path.read_text())['rows']}
    bindings = {str(audit_path):digest(audit_path)}
    def receipt(unit):
        path = directory/(unit+'.json')
        assert accepted[unit]['accepted']
        assert digest(path) == path.with_suffix('.sha256').read_text().strip() == accepted[unit]['receipt_sha256']
        d = json.loads(path.read_text()); verify_sources(d['source_sha256']); verify_sources(d['inputs'])
        bindings[str(path)] = digest(path)
        return d
    quad = receipt(args.block+'-Q')
    qb, qs, qc, qp, ports = prepare_window(args.block+'-Q')
    assert qb == quad['binding'] and [c.tolist() for c in qc] == quad['columns']
    qstate = np.asarray(quad['best']['mean'])
    local = {scan.unit_id:qstate[indices] for (scan,_,_),indices in zip(qs,qc)}
    rows = []
    for suffix in ['-D1', '-D2']:
        unit = args.block+suffix; pair = receipt(unit)
        pb, scans, columns, precision, ports = prepare_window(unit)
        assert pb == pair['binding'] and precision.tolist() == pair['precision']
        state = np.zeros(len(precision))
        for (scan,_,_),indices in zip(scans,columns):
            state[indices] = local[scan.unit_id]
        assert np.linalg.norm(state[:2]) <= 250
        labels = [int(np.argmax(p.score_all(state))) for p in ports]
        objective = float(.5*(precision*state)@state-sum(p.score_selected(state,i) for p,i in zip(ports,labels)))
        original = np.asarray(pair['best']['mean'])
        original_labels = [int(np.argmax(p.score_all(original))) for p in ports]
        original_objective = float(.5*(precision*original)@original-sum(p.score_selected(original,i) for p,i in zip(ports,original_labels)))
        assert original_labels == pair['best']['associations']
        assert abs(original_objective-pair['best']['objectives'][-1]) < 1e-6
        rows.append(dict(unit=unit, pair_objective=original_objective,
            pair_objective_at_quad_state=objective,
            quad_state_minus_pair_objective=objective-original_objective,
            changed_assignments=sum(a!=b for a,b in zip(labels,original_labels)),
            total_tracks=len(ports), position_separation_m=float(1000*np.linalg.norm(state[:2]-original[:2])),
            qualification='No refit. Quad state uses extra scans and is diagnostic only; it is not an admissible seed for a causal pair evaluation.'))
    out = directory/'pair-mode-diagnostic-v1.json'
    result = dict(rows=rows, input_sha256=bindings, source_sha256=digest(__file__),
        qualification='Reference-free feasible-point comparison. Lower objective demonstrates a better available pair state, not global optimality or geographic correctness. Higher objective does not rule out a missed mode.')
    with out.open('x') as stream: json.dump(result,stream,indent=2,allow_nan=False)
    out.with_suffix('.sha256').write_text(digest(out)+'\n')
    print(json.dumps(result,indent=2),flush=True)


if __name__ == '__main__': main()
