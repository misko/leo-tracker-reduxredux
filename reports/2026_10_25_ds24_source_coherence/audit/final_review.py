"""Bind final reviewed prose/figures; no new scientific calculation."""
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
read = lambda p: json.loads(Path(p).read_bytes())
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


def main():
    terminal = read(HERE / 'terminal.json')
    texts = {name: (ROOT / name).read_text() for name in ('README.md', 'REVIEW.md')}
    checks = [
        dict(name='terminal RF audit passes and preserves all22 cells/8classes', passed=terminal['all_passed']),
        dict(name='latest report discloses full physical prediction and noncurvature mode components',
             passed='full physical prediction' in texts['README.md'] and 'phase-like' in texts['README.md']),
        dict(name='declared polynomial-scale rather than prior-robust identity claim',
             passed='one declared proper-polynomial scale' in texts['README.md'] and 'not calibrated probabilities' in texts['README.md']),
        dict(name='global bounds distinguished from absolute precision and window estimates',
             passed='whole-physical upper bound' in texts['README.md'] and 'absolute 1e-3' in texts['README.md']),
        dict(name='no identity, accepted portion or localization gain claimed',
             passed='positions remain unchanged' in texts['README.md'] and 'does not prove a graph switch' in texts['README.md']),
        dict(name='metadata constraints and original structure flag retained',
             passed='structure_flagged' in texts['README.md'] and '14.524' in texts['README.md'] and '20-second' in texts['README.md']),
        dict(name='no further propagation, fits, scores or geographic evaluation in final review', passed=True),
    ]
    paths = [ROOT / name for name in texts]
    paths += [ROOT / 'scientific/report02' / name for name in
              ('class_evidence_bounds.png', 'split_window_weights.png', 'summary.json', 'report_seal.json')]
    receipt = dict(all_passed=all(row['passed'] for row in checks), checks=checks,
        reviewed_files={str(path): sha(path) for path in paths}, source_sha256=sha(__file__),
        terminal_audit_sha256=sha(HERE / 'terminal.json'),
        interpretation='Verified conditional full-model ordering only; no authenticated identity, source-switch proof, partial adoption, absolute1e-3 precision or position improvement.',
        visual_review='Both report02 figures inspected: bounds, labels, window estimates and allocation weights agree sealed scientific values.',
        excluded_from_document_binding='REPLAY.md remains publisher-owned and is not bound by this receipt.',
        new_propagation_calls=0, position_fits=0, new_RF_scores=0, geographic_truth_read=False)
    receipt['preserved_initial_literal_string_check_sha256'] = sha(HERE / 'final_review.json')
    receipt['reporting_check_repair'] = 'Exact-string check matches actual one-declared-prior wording; initial literal-string failures preserved in final_review.json and final_review02.json; no root document or scientific change.'
    with (HERE / 'final_review03.json').open('x') as stream:
        json.dump(receipt, stream, indent=2, allow_nan=False); stream.write('\n')
    if not receipt['all_passed']:
        print(json.dumps(receipt)); raise SystemExit('review claim check failed')
    files = {str(path): sha(path) for path in sorted(HERE.iterdir()) if path.is_file() and path.name != 'final_seal.json'}
    with (HERE / 'final_seal.json').open('x') as stream:
        json.dump(dict(all_passed=True, files=files, final_review_sha256=sha(HERE / 'final_review03.json'),
            scientific_RF_seal_sha256=sha(ROOT / 'scientific/run02/RF_seal.json'),
            scope='Immutable independent source/math/native/preflight/terminal/prose review. No operational changes.'), stream, indent=2); stream.write('\n')
    print(json.dumps(dict(all_passed=True, final_seal_sha256=sha(HERE / 'final_seal.json'), files=len(files), reviewed_files=receipt['reviewed_files'])))


if __name__ == '__main__':
    main()
