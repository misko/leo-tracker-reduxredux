"""Compare complete exports after verifying process and named file-hash edges.

Accounting, log and font differences remain explicit. This is an intermediate
diagnostic, not a scientific-equivalence waiver.
"""
import argparse
import hashlib
import importlib
import json
from collections import Counter
from pathlib import Path

from algo07_star_accounting import classify, log_accounting
from algo07_star_links import HashLinks
from algo07_star_receipts import audit_catalogue
from compare_algo07_star_receipts import load_catalogue
from diff_algo07_star_evidence import differences

from leo.cli.algo07_profile import write_new


def execution_context(runtime_spec, manifest, reference_execution, candidate_execution, algorithms,
                      *, reference_store, candidate_binding):
    """Bind remaining-budget classification to the original paired executions."""
    spec = json.loads(runtime_spec.read_text())
    frozen = json.loads(manifest.read_text())
    digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    member = [r for r in frozen['files'] if Path(r['path']).resolve() == runtime_spec.resolve()]
    if (len(member) != 1 or member[0]['sha256'] !=
            hashlib.sha256(runtime_spec.read_bytes()).hexdigest()):
        raise ValueError('Runtime specification is not bound to the frozen manifest')
    if list(spec) != list(algorithms) or any(spec[k]['maximum_seconds'] != 1200 for k in spec):
        raise ValueError('Original six-stage 1200-second budgets required')
    records = [json.loads(p.read_text()) for p in (reference_execution, candidate_execution)]
    for record in records:
        if (record['state'] != 'scientific_complete' or record['runtime_manifest_sha256'] != digest
                or record['runtime_verification']['verified'] is not True
                or record['runtime_verification']['failed'] != []
                or [r['algorithm'] for r in record['stages']] != list(algorithms)):
            raise ValueError('Completed paired executions must bind the same frozen manifest')
    for row in records[0]['stages']:
        command = row['command']
        if (command.count('--maximum-seconds') != 1 or
                command[command.index('--maximum-seconds')+1] != '1200'
                or command.count('--bulk-root') != 1
                or command[command.index('--bulk-root')+1] != reference_store
                or row['exit_code'] not in (None, 0)):
            raise ValueError('Reference command used a different stage budget or failed')
    incumbent = records[1]['incumbent']
    if (any(incumbent[k] != candidate_binding[k] for k in
            ('job_id', 'model_version', 'input_sha256'))
            or incumbent['terminal'] != {k: candidate_binding[k] for k in ('path', 'sha256')}):
        raise ValueError('Candidate execution does not bind the compared final terminal')
    return dict(manifest_sha256=digest, runtime_spec_sha256=member[0]['sha256'],
                maximum_seconds={k: spec[k]['maximum_seconds'] for k in spec},
                reference_execution_sha256=hashlib.sha256(reference_execution.read_bytes()).hexdigest(),
                candidate_execution_sha256=hashlib.sha256(candidate_execution.read_bytes()).hexdigest(),
                reference_checkpoint_stages=[r['algorithm'] for r in records[0]['stages']
                                             if not r['executed']])


def compare(reference, candidate, *, classify_accounting=False, execution_paths=None):
    ca, ba = load_catalogue(reference)
    cb, bb = load_catalogue(candidate)
    if ba != bb:
        raise ValueError('Different stage/input bindings')
    execution = None
    if classify_accounting:
        if execution_paths is None:
            raise ValueError('Frozen paired execution evidence required for accounting')
        final = list(ba)[-1]
        candidate_file = cb[final+'/worker/terminal.json']
        execution = execution_context(*execution_paths, ba,
            reference_store=ca[final+'/worker/terminal.json']['store_root'],
            candidate_binding=dict(bb[final], path=candidate_file['source_path'],
                                   sha256=candidate_file['sha256']))
    ga, ra = audit_catalogue(ca)
    gb, rb = audit_catalogue(cb)
    if ({k: v['forest'] for k, v in ga.items()} !=
            {k: v['forest'] for k, v in gb.items()}):
        raise ValueError('Process provenance differs')
    left, right = HashLinks(ca, ga), HashLinks(cb, gb)
    validated_terminals = []
    for version, algorithm in enumerate(ba, 1):
        module = importlib.import_module('leo.contracts.fast_graph_position'+
                                        ('' if version == 1 else f'_v{version}'))
        for index in (left, right):
            terminal = index.read(algorithm+'/worker/terminal.json')
            module.validate_terminal(terminal, input_sha256=ba[algorithm]['input_sha256'])
            if terminal['state'] != 'complete':
                raise ValueError('Completed stage required for this comparison')
            if version == 1:
                launch = index.read(algorithm+'/worker/launch.json')
                if launch['maximum_seconds'] != 1200:
                    raise ValueError('Original initial-worker limit required')
        validated_terminals.append(algorithm)
    a = {left.identity(name): name for name in ca}
    b = {right.identity(name): name for name in cb}
    if len(a) != len(ca) or len(b) != len(cb):
        raise ValueError('File normalization collision')
    rows, errors, accounting = [], [], []
    checked, classes = Counter(), Counter()
    for identity in sorted(a.keys() | b.keys()):
        if identity not in a or identity not in b:
            rows.append(dict(file=identity, kind='missing_file', reference=identity in a,
                             candidate=identity in b))
            continue
        x, y = a[identity], b[identity]
        if Path(identity).parent.name == 'read_receipts':
            checked['process_receipts'] += 1
            continue
        if 'matplotlib-cache' in Path(identity).parts:
            classes['font_cache'] += 1
            # These bytes have been verified. They remain an explicit unqualified
            # presentation class, not a reason to claim scientific parity here.
            if ca[x]['sha256'] != cb[y]['sha256']:
                rows.append(dict(file=identity, kind='font_cache_bytes'))
            continue
        if not identity.endswith('.json'):
            checked['binary_or_text_files'] += 1
            if ca[x]['sha256'] != cb[y]['sha256']:
                logged = False
                if classify_accounting and identity.endswith('.log'):
                    raw = [index.catalogue[n]['path'].read_bytes()
                           for index, n in ((left, x), (right, y))]
                    if any('sha256:'+hashlib.sha256(data).hexdigest() != entry['sha256']
                           for data, entry in zip(raw, (ca[x], cb[y]), strict=True)):
                        raise ValueError('Log changed during comparison')
                    u, un = log_accounting(identity, raw[0].decode('utf-8'))
                    v, vn = log_accounting(identity, raw[1].decode('utf-8'))
                    if u == v and un == vn > 0:
                        accounting.append(dict(file=identity, kind='log_bytes',
                                               reason='reviewed_log_timing', messages=un))
                        logged = True
                if not logged:
                    rows.append(dict(file=identity, kind='bytes'))
            continue
        checked['json_documents'] += 1
        values = []
        for side, index, name in [('reference', left, x), ('candidate', right, y)]:
            try:
                values.append(index.document(name, index.read(name)))
            except (ValueError, KeyError) as error:
                errors.append(dict(file=identity, side=side, error=str(error)))
        if len(values) == 2:
            for row in differences(*values):
                reason = classify(identity, row, *values, (ra, rb)) if classify_accounting else None
                record = dict(file=identity, **row)
                if reason:
                    accounting.append(dict(reason=reason, **record))
                else:
                    rows.append(record)
    non_scientific = [r for r in rows if r['kind'] == 'font_cache_bytes']
    scientific = [r for r in rows if r not in non_scientific]
    return dict(schema_version=1, kind='algo07-star-verified-link-diagnostic', bindings=ba,
                process_provenance_equal=True, reference=left.summary(), candidate=right.summary(),
                verified_links=dict(reference=left.verified_links, candidate=right.verified_links),
                checked=dict(checked), file_classes=dict(classes), link_errors=errors,
                hash_edges_verified=not errors, differences=rows,
                difference_counts=dict(Counter(r['kind'] for r in rows)),
                validated_public_terminals=validated_terminals,
                paired_execution=execution,
                accounting_classification_enabled=classify_accounting,
                classified_accounting=accounting,
                accounting_counts=dict(Counter(r['reason'] for r in accounting)),
                scientific_differences=scientific,
                scientific_json_and_array_parity=(classify_accounting and not errors
                                                 and not scientific),
                scientific_parity_qualified=False,
                excluded_operational_file_differences=non_scientific)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--classify-accounting', action='store_true')
    for flag in ('runtime-spec', 'manifest', 'reference-execution', 'candidate-execution'):
        parser.add_argument('--'+flag, type=Path)
    args = parser.parse_args()
    execution = (args.runtime_spec, args.manifest,
                 args.reference_execution, args.candidate_execution)
    if args.classify_accounting and any(p is None for p in execution):
        parser.error('Accounting requires runtime spec, manifest and both execution receipts')
    result = compare(args.reference, args.candidate, classify_accounting=args.classify_accounting,
                     execution_paths=execution if args.classify_accounting else None)
    write_new(args.output, result)
    print(json.dumps({k: v for k, v in result.items() if k not in
                      ('verified_links', 'differences', 'bindings', 'link_errors',
                       'classified_accounting', 'scientific_differences',
                       'excluded_operational_file_differences')}))
    print('Link errors:', len(result['link_errors']))
    passed = result['hash_edges_verified'] and (
        not args.classify_accounting or result['scientific_json_and_array_parity'])
    raise SystemExit(0 if passed else 1)
