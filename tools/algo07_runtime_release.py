"""Validate an explicitly qualified ALGO07 runtime composition, including every source file."""

import hashlib
import json
import os
from pathlib import Path

ENVIRONMENT = 'LEO_ALGO07_RUNTIME_MANIFEST_SHA256'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify(root, expected=None):
    root = Path(root).resolve()
    expected = os.environ.get(ENVIRONMENT) if expected is None else expected
    if not expected or len(expected) != 64:
        raise ValueError('Explicit pinned runtime manifest SHA256 required')
    path = root/'runtime-manifest.json'
    if digest(path) != expected:
        raise ValueError('ALGO07 runtime manifest changed')
    manifest = json.loads(path.read_text())
    if manifest['kind'] != 'algo07-qualified-runtime-composition-v1':
        raise ValueError('Unknown ALGO07 runtime composition')
    for name, sha in manifest['files_sha256'].items():
        relative = Path(name)
        target = root/relative
        if (relative.is_absolute() or '..' in relative.parts or target.is_symlink()
                or not target.resolve().is_relative_to(root) or digest(target) != sha):
            raise ValueError('ALGO07 runtime member changed: '+name)
    return manifest
