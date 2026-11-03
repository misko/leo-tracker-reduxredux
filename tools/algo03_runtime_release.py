"""Verify a qualified ALGO03 runtime without changing its scientific contract."""

import hashlib
import json
import os
from pathlib import Path

ENVIRONMENT = 'LEO_ALGO03_RUNTIME_MANIFEST_SHA256'
KIND = 'algo03-qualified-runtime-composition-v1'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify(root, expected=None):
    root = Path(root).resolve()
    expected = os.environ.get(ENVIRONMENT) if expected is None else expected
    if not expected or len(expected) != 64:
        raise ValueError('Explicit pinned ALGO03 runtime manifest required')
    path = root/'runtime-manifest.json'
    if digest(path) != expected:
        raise ValueError('ALGO03 runtime manifest changed')
    manifest = json.loads(path.read_text())
    if manifest['kind'] != KIND or not manifest['files_sha256']:
        raise ValueError('Unqualified or empty ALGO03 runtime')
    for name, sha in manifest['files_sha256'].items():
        relative = Path(name)
        member = root/relative
        if (relative.is_absolute() or '..' in relative.parts or member.is_symlink()
                or not member.resolve().is_relative_to(root) or digest(member) != sha):
            raise ValueError('ALGO03 runtime member changed: '+name)
    return manifest
