"""Resolve scientific/provenance hash edges against verified exported bytes.

Linked targets remain in the comparison inventory. Replacing a digest with its
target identity is safe only when that target is independently compared. This
module does not waive any numerical, accounting or file-content differences.
"""
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from diff_algo07_star_evidence import normalized


def digest_value(value):
    if not isinstance(value, str) or not re.fullmatch(r'(sha256:)?[0-9a-f]{64}', value):
        raise ValueError('Invalid SHA-256 binding')
    return value.removeprefix('sha256:')


def relocate_paths(value, original, relocated):
    if isinstance(value, str):
        if value == original or value.startswith(original+'/'):
            return relocated+value[len(original):]
        return value
    if isinstance(value, list):
        return [relocate_paths(v, original, relocated) for v in value]
    if isinstance(value, dict):
        result = {relocate_paths(k, original, relocated): relocate_paths(v, original, relocated)
                  for k, v in value.items()}
        if len(result) != len(value):
            raise ValueError('Relocation collapsed dictionary keys')
        return result
    return value


class HashLinks:
    def __init__(self, catalogue, process_groups):
        self.catalogue = catalogue
        self.process_groups = process_groups
        self.sources = {}
        self.verified_links = []
        self.relocations = {}
        self.historical_relocations = {}
        for name, item in catalogue.items():
            source = item['source_path']
            if source in self.sources:
                raise ValueError('Duplicate original file identity')
            self.sources[source] = name
        self._qualify_relocations()

    def read(self, name):
        item = self.catalogue[name]
        raw = item['path'].read_bytes()
        if hashlib.sha256(raw).hexdigest() != digest_value(item['sha256']):
            raise ValueError('Export changed while reading: '+name)
        return json.loads(raw)

    def identity(self, name):
        path = Path(name)
        if path.parent.name == 'read_receipts':
            proof = self.process_groups[str(path.parent)]
            role = proof['roles'][int(path.stem)].replace('/', '.')
            return str(path.parent)+'/'+role+'.json'
        return name

    def source_name(self, source, expected):
        if source not in self.sources:
            raise ValueError('Hash target is absent from exported evidence: '+source)
        name = self.sources[source]
        if digest_value(self.catalogue[name]['sha256']) != digest_value(expected):
            raise ValueError('Hash target bytes disagree: '+source)
        return name

    def bind(self, source, expected, name, pointer):
        target = self.source_name(source, expected)
        identity = self.identity(target)
        self.verified_links.append(dict(file=name, pointer=pointer, target=identity,
                                        sha256=digest_value(expected)))
        return '<VERIFIED_FILE>/'+identity

    def path(self, value, store_root):
        if value in self.sources:
            name = self.sources[value]
            if Path(name).parent.name == 'read_receipts':
                return '<VERIFIED_RECEIPT_PATH>/'+self.identity(name)
        return normalized(value, store_root)

    def _qualify_relocations(self):
        documents = {name: self.read(name) for name in self.catalogue
                     if Path(name).name in ('cache-relocation.json', 'relocation.json')}
        edges, pending = {}, {}
        for name, value in documents.items():
            if not {'source_hashes', 'relocated_hashes', 'original_root', 'relocated_root',
                    'scientific_values_unchanged'} <= value.keys():
                raise ValueError('Unknown relocation schema: '+name)
            if value['scientific_values_unchanged'] is not True:
                raise ValueError('Relocation does not claim scientific preservation')
            original, target = value['original_root'], value['relocated_root']
            if not Path(original).is_absolute() or not Path(target).is_absolute():
                raise ValueError('Absolute relocation roots required')
            a, b = value['source_hashes'], value['relocated_hashes']
            if not a or a.keys() != b.keys():
                raise ValueError('Relocation member inventories differ')
            links = []
            for relative in a:
                if Path(relative).is_absolute() or '..' in Path(relative).parts:
                    raise ValueError('Unsafe relocation member')
                try:
                    source_name = self.source_name(str(Path(original)/relative), a[relative])
                    target_name = self.source_name(str(Path(target)/relative), b[relative])
                except ValueError:
                    pending[name] = value
                    break
                links.append((target_name, source_name, original, target))
            else:
                self.relocations[name] = value
                for target_name, source_name, original, target in links:
                    edges.setdefault(target_name, []).append((source_name, original, target))
        # Nested relocation receipts retain historical digest maps even when an
        # enclosing relocation changes their path strings. Verify their outer
        # copy edge and exact path-only transform; never bless a stale digest by
        # simply removing it. The original receipt supplies the historical roots.
        while pending:
            advanced = []
            for name, value in pending.items():
                identical = next((source for source in self.relocations if
                                  self.catalogue[source]['sha256'] ==
                                  self.catalogue[name]['sha256']), None)
                if identical is not None:
                    # Opaque historical exports intentionally preserve every
                    # byte. An already verified identical receipt carries the
                    # same historical bindings, regardless of its copied path.
                    self.relocations[name] = self.relocations[identical]
                    self.historical_relocations[name] = identical
                    advanced.append(name)
                    continue
                for source, original, target in edges.get(name, []):
                    if source not in self.relocations:
                        continue
                    source_value = documents[source]
                    if relocate_paths(source_value, original, target) != value:
                        continue
                    self.relocations[name] = self.relocations[source]
                    self.historical_relocations[name] = source
                    advanced.append(name)
                    break
            if not advanced:
                raise ValueError('Unverified historical relocation: '+next(iter(pending)))
            for name in advanced:
                del pending[name]

    def document(self, name, value):
        store_root = self.catalogue[name]['store_root']
        source_path = Path(self.catalogue[name]['source_path'])

        def visit(value, pointer=''):
            if isinstance(value, str):
                return self.path(value, store_root)
            if isinstance(value, list):
                return [visit(v, pointer+'/'+str(i)) for i, v in enumerate(value)]
            if not isinstance(value, dict):
                return value
            result = {}
            for key, item in value.items():
                child = pointer+'/'+key.replace('~', '~0').replace('/', '~1')
                mapped_key = self.path(key, store_root)
                if key in ('source_hashes', 'relocated_hashes') and pointer == '' and name in \
                        self.relocations:
                    origin = self.relocations[name]
                    root = origin['original_root' if key == 'source_hashes' else 'relocated_root']
                    if item != origin[key]:
                        raise ValueError('Copied historical digest map changed')
                    result[mapped_key] = self.mapping(item, root, name, child, store_root)
                elif (key in ('source_hashes', 'source_receipts', 'source_support_receipt',
                              'input_sha256') and isinstance(item, dict)
                      and all(Path(k).is_absolute() for k in item)):
                    result[mapped_key] = self.mapping(item, None, name, child, store_root)
                elif (key == 'files' and isinstance(item, dict)
                      and isinstance(value.get('root'), str)):
                    result[mapped_key] = self.mapping(item, value['root'], name, child, store_root)
                elif key == 'sha256' and isinstance(value.get('path'), str):
                    result[mapped_key] = self.bind(value['path'], item, name, child)
                elif key == 'scientific_result_sha256':
                    target = 'ALGO02/worker/inference/family_cavity/position/SCAN.json'
                    result[mapped_key] = self.bind(self.catalogue[target]['source_path'], item,
                                                   name, child)
                elif key == 'baseline_sha256' and source_path.name == 'algo02_result.json':
                    result[mapped_key] = self.bind(str(source_path.with_name('result.json')),
                                                   item, name, child)
                elif key == 'baseline_sha256' and isinstance(value.get('baseline_source'), str):
                    result[mapped_key] = self.bind(value['baseline_source'], item, name, child)
                elif key in ('baseline_terminal_sha256', 'incumbent_terminal_sha256'):
                    job = value['source_job']
                    targets = [n for n, entry in self.catalogue.items()
                               if len(Path(n).parts) == 3 and n.endswith('/worker/terminal.json')
                               and entry['job_id'] == job['job_id']
                               and entry['model_version'] == job['model_version']]
                    if len(targets) != 1:
                        raise ValueError('Unique exported source-job terminal required')
                    result[mapped_key] = self.bind(self.catalogue[targets[0]]['source_path'],
                                                   item, name, child)
                elif key == 'source_inventory_sha256' and value.get('policy') == 'gap_conditional':
                    # This scalar digest is not rewritten by later relocations.
                    # The producer binds the original ALGO05 inventory, whose
                    # contents and all relocated copies are compared separately.
                    targets = [n for n in self.catalogue if n.startswith(
                        'ALGO05/worker/recovery/current/all-large-track-recovery/')
                        and n.endswith('/inventory.json')]
                    if len(targets) != 1:
                        raise ValueError('Unique original gap-recovery inventory required')
                    result[mapped_key] = self.bind(self.catalogue[targets[0]]['source_path'],
                                                   item, name, child)
                elif key == 'nomination_sha256' and source_path.parts[-3:] == \
                        ('family_cavity', 'position', 'SCAN.json'):
                    result[mapped_key] = self.bind(str(source_path.parent.parent/
                                                       'SCAN_nominations.json'), item, name, child)
                elif key in ('input_sha256', 'catalogue_sha256') and \
                        'catalogue_path' in value and 'input_path' in value:
                    field = 'input_path' if key == 'input_sha256' else 'catalogue_path'
                    result[mapped_key] = self.bind(value[field], item, name, child)
                else:
                    result[mapped_key] = visit(item, child)
            if len(result) != len(value):
                raise ValueError('Hash-link normalization collapsed dictionary keys')
            return result

        return visit(value)

    def mapping(self, values, root, name, pointer, store_root):
        result = {}
        for key, expected in values.items():
            if root is None:
                source = key
                mapped_key = self.path(key, store_root)
            else:
                if Path(key).is_absolute() or '..' in Path(key).parts:
                    raise ValueError('Unsafe relative hash target')
                source = str(Path(root)/key)
                mapped_key = key
                if Path(key).parent.name == 'read_receipts':
                    target = self.source_name(source, expected)
                    mapped_key = str(Path(key).parent)+'/'+Path(self.identity(target)).name
            result[mapped_key] = self.bind(source, expected, name, pointer+'/'+key)
        if len(result) != len(values):
            raise ValueError('Hash mapping collapsed distinct targets')
        return result

    def summary(self):
        return dict(verified_links=len(self.verified_links),
                    target_classes=dict(Counter(Path(r['target']).suffix
                                                for r in self.verified_links)),
                    relocation_receipts=len(self.relocations),
                    historical_relocations=self.historical_relocations)
