"""Bind every file of an explicitly non-production ALGO03 runtime experiment."""

import hashlib
import json
import os
from pathlib import Path


def verify(root):
    root = Path(root).resolve()
    pin = os.environ.get('LEO_ALGO03_RESEARCH_RUNTIME_SHA256')
    raw = (root/'runtime-manifest.json').read_bytes()
    if not pin or hashlib.sha256(raw).hexdigest() != pin:
        raise ValueError('Missing or changed ALGO03 research runtime pin')
    manifest = json.loads(raw)
    if manifest['kind'] != 'algo03-runtime-research-prototype-v1':
        raise ValueError('Unexpected research composition')
    if not manifest['files_sha256']:
        raise ValueError('Empty runtime inventory')
    for name, expected in manifest['files_sha256'].items():
        relative = Path(name)
        path = root/relative
        if (relative.is_absolute() or '..' in relative.parts or path.is_symlink()
                or not path.resolve().is_relative_to(root)
                or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
            raise ValueError('Changed runtime member: '+name)
    return manifest
