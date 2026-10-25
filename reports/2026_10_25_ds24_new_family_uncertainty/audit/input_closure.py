"""Trace read-only saved-context file inputs; never call a position fitter."""

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
OLD = Path('/srv/bulk/leo/research/ds24-movement-policy-r01')
SOURCE = Path('/srv/bulk/leo/research/ds25-20261024')
PUBLISHER = Path('/srv/bulk/leo/research/publish-ds23-family-cavity-sparse-20261022')
OLD_REPORT = PUBLISHER/'reports/2026_10_25_ds24_movement_policy'
COMMIT = '82e608d8d3b254e737326058e601a4775f231135'
opened = set()


def audit(event, args):
    if event != 'open' or not isinstance(args[0], (str, bytes)):
        return
    path = Path(args[0]).resolve()
    if any(path.is_relative_to(parent) for parent in (ROOT, OLD, SOURCE)):
        if path.suffix not in ('.py', '.pyc', '.so'):
            opened.add(path)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    sys.addaudithook(audit)
    import adapter
    contexts = [adapter.load_context(case) for case in adapter.CASES]
    assert len(contexts) == 2
    # Freeze the trace before reading provenance metadata or writing outputs.
    inputs = sorted(opened)
    index = json.loads((OLD_REPORT/'publication_index.json').read_text())
    old_members = {m['member']:(a, m) for a in index['assets'] for m in a['members']}
    rows = []
    for path in inputs:
        digest = sha(path)
        row = dict(path=str(path), sha256=digest, bytes=path.stat().st_size)
        if path.is_relative_to(OLD):
            member = str(path.relative_to(OLD))
            if member in old_members:
                asset, old = old_members[member]
                assert digest == old['sha256']
                row.update(delivery='prior_release_asset_member', member=member,
                    asset=asset['asset'], asset_url=asset['url'], asset_sha256=asset['sha256'])
            else:
                assert (OLD_REPORT/member).is_file() and sha(OLD_REPORT/member) == digest
                relative = 'reports/2026_10_25_ds24_movement_policy/'+member
                row.update(delivery='prior_immutable_git_file', member=relative,
                    url=f'https://raw.githubusercontent.com/misko/leo-tracker-reduxredux/{COMMIT}/{relative}')
        elif path.is_relative_to(SOURCE):
            row.update(delivery='new_frozen_input_delta', member='input/ds25/'+str(path.relative_to(SOURCE)))
        elif path.is_relative_to(ROOT):
            row.update(delivery='current_report_file', member=str(path.relative_to(ROOT)))
        else:
            raise AssertionError(path)
        rows.append(row)
    result = dict(no_position_fits=True, no_GPS=True, source_sha256=sha(Path(__file__)),
        scope='Successful read-open files under current/R1/DS25 study roots during two safe saved-context reconstructions; Python source separately bound by runtime_closure.json.',
        files=rows, actual_context_input_files=len(rows), input_bytes=sum(v['bytes'] for v in rows),
        new_input_bytes=sum(v['bytes'] for v in rows if v['delivery']=='new_frozen_input_delta'),
        delivery_counts={kind:sum(v['delivery']==kind for v in rows) for kind in sorted({v['delivery'] for v in rows})},
        raw_IQ_included=False)
    (ROOT/'audit/input_closure.json').write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps({k:v for k,v in result.items() if k != 'files'}, indent=2))


if __name__ == '__main__':
    main()
