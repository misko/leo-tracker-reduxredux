"""Validate complete guarded process forests and identify processes by their work.

PID spelling is operational; reads, denied reads, launch counts and ancestry are
evidence. The canonical forest retains all of those facts except numeric PIDs.
"""
import hashlib
import json
from collections import defaultdict
from pathlib import Path

from diff_algo07_star_evidence import normalized


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     allow_nan=False).encode()).hexdigest()


def audit_group(records, *, store_root, receipt_reference=None):
    by_pid = {}
    for filename, record in records:
        if set(record) != {'pid', 'parent_pid', 'python_spawns', 'read_paths', 'denied_paths'}:
            raise ValueError('Unknown process receipt schema')
        pid, parent = record['pid'], record['parent_pid']
        if (type(pid) is not int or type(parent) is not int or min(pid, parent) <= 0
                or pid == parent or Path(filename).name != f'{pid}.json' or pid in by_pid):
            raise ValueError('Invalid or duplicated process identity')
        if record['denied_paths'] != []:
            raise ValueError('Guarded process attempted a denied read')
        for key in ('read_paths', 'python_spawns'):
            if (not isinstance(record[key], list) or
                    any(not isinstance(p, str) or not Path(p).is_absolute() for p in record[key])):
                raise ValueError('Process reads and launches must be explicit absolute paths')
        if record['read_paths'] != sorted(set(record['read_paths'])):
            raise ValueError('Read receipt must contain the sorted unique read set')
        by_pid[pid] = record
    if not by_pid:
        raise ValueError('Empty guarded process forest')
    children = defaultdict(list)
    roots = []
    for pid, record in by_pid.items():
        parent = record['parent_pid']
        if parent in by_pid:
            children[parent].append(pid)
        else:
            roots.append(pid)
    supervisors = {by_pid[p]['parent_pid'] for p in roots}
    if len(supervisors) != 1:
        raise ValueError('Guarded forest must have one recorded supervisor')
    if any(len(children[pid]) != len(row['python_spawns']) for pid, row in by_pid.items()):
        raise ValueError('Unaccounted process launch or missing child receipt')
    visiting, fingerprints, work = set(), {}, {}

    def visit(pid):
        if pid in visiting:
            raise ValueError('Cyclic process ancestry')
        if pid in fingerprints:
            return fingerprints[pid]
        visiting.add(pid)
        row = by_pid[pid]
        reads = []
        for path in row['read_paths']:
            if receipt_reference is not None and Path(path).parent.name == 'read_receipts':
                reads.append(receipt_reference(path))
            else:
                reads.append(normalized(path, store_root))
        if len(set(reads)) != len(reads):
            raise ValueError('Read normalization collapsed distinct evidence paths')
        # The source guard emits a sorted set, not chronological read events.
        # Re-sort after verified PID-path substitution, preserving membership.
        value = dict(read_paths=sorted(reads),
                     python_spawns=row['python_spawns'], denied_paths=[],
                     children=sorted(visit(p) for p in children[pid]))
        work[pid] = value
        fingerprints[pid] = canonical_digest(value)
        visiting.remove(pid)
        return fingerprints[pid]

    for pid in by_pid:
        visit(pid)
    roles = {}

    def assign(pid, role):
        if pid in roles:
            raise ValueError('Duplicated process in guarded forest')
        roles[pid] = role
        for index, child in enumerate(sorted(children[pid], key=lambda p: (fingerprints[p], p))):
            assign(child, role+f'/child-{index}')

    for index, pid in enumerate(sorted(roots, key=lambda p: (fingerprints[p], p))):
        assign(pid, f'root-{index}')
    if len(roles) != len(by_pid):
        raise ValueError('Process forest contains an unrooted component')
    forest = {roles[pid]: dict(work[pid], parent=(roles[row['parent_pid']]
               if row['parent_pid'] in by_pid else 'supervisor')) for pid, row in by_pid.items()}
    return dict(verified=True, receipts=len(by_pid), expected=len(roots)+sum(
                len(r['python_spawns']) for r in by_pid.values()), roots=len(roots),
                supervisor=next(iter(supervisors)), roles=roles, fingerprints=fingerprints,
                forest=forest, forest_sha256=canonical_digest(forest))


def audit_catalogue(catalogue):
    """Audit every original and copied read-receipt group in a worker catalogue."""
    groups = defaultdict(list)
    for name, item in catalogue.items():
        if Path(name).parent.name == 'read_receipts' and name.endswith('.json'):
            groups[str(Path(name).parent)].append((name, json.loads(item['path'].read_text())))
    if not groups:
        raise ValueError('No guarded process receipts in worker evidence')
    sources = {}
    for name, item in catalogue.items():
        if Path(name).parent.name == 'read_receipts' and name.endswith('.json'):
            source = item['source_path']
            if source in sources:
                raise ValueError('Duplicate source receipt path')
            sources[source] = name
    results, candidates, visiting = {}, defaultdict(list), set()

    def receipt_reference(path):
        if path not in sources:
            raise ValueError('Read refers to an unexported process receipt: '+path)
        name = sources[path]
        group = str(Path(name).parent)
        proof = audit(group)
        pid = int(Path(name).stem)
        return ('<VERIFIED_RECEIPT>/'+group+'/'+proof['roles'][pid]+'/'+
                proof['fingerprints'][pid])

    def audit(group):
        if group in results:
            return results[group]
        if group in visiting:
            raise ValueError('Cyclic dependency between read-receipt groups')
        visiting.add(group)
        records = groups[group]
        store_root = catalogue[records[0][0]]['store_root']
        proof = audit_group(records, store_root=store_root, receipt_reference=receipt_reference)
        results[group] = proof
        visiting.remove(group)
        for pid, role in proof['roles'].items():
            candidates[pid].append((0, group+':'+role, proof['fingerprints'][pid]))
        candidates[proof['supervisor']].append((1, group+':supervisor', None))
        return proof

    for group in sorted(groups):
        audit(group)
    process_roles = {}
    for pid, options in candidates.items():
        # Later recovery exports legitimately relocate paths inside copied
        # receipts. Retain and compare EVERY group's forest, rather than demand
        # that these path-bearing copies have identical fingerprints. Prefer
        # the earliest original stage's role when identifying a repeated PID.
        process_roles[pid] = min(options)[1]
    return results, process_roles
