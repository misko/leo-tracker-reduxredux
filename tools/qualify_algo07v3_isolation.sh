#!/bin/sh
# External qualification only. Always create private mount/network namespaces
# before masking paths; never perform these mounts in the host namespace.
set -eu
test "$#" -eq 5 || { echo 'usage: BUNDLE OUTPUT_PARENT PYTHON INPUT_SHA256 SCAN_ID' >&2; exit 2; }
exec unshare --mount --net --propagation private sh -s -- "$@" <<'ISOLATED'
set -eu
mount --bind "$1" "$1"
mount -o remount,bind,ro "$1"
mount -t tmpfs -o ro,size=1m tmpfs /opt
mount -t tmpfs -o ro,size=1m tmpfs /srv/bulk/leo
mount -t tmpfs -o ro,size=1m tmpfs reports
"$3" -B - "$1" "$2" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
bundle, output = map(Path, sys.argv[1:])
manifest = json.loads((bundle/'input-bindings.json').read_text())
for name, sha in manifest['files'].items():
    path = (bundle/name).resolve()
    assert path.is_relative_to(bundle.resolve())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
evidence = dict(
    old_installations_hidden=not list(Path('/opt').iterdir()),
    old_bulk_data_hidden=not list(Path('/srv/bulk/leo').iterdir()),
    repository_reports_hidden=not list(Path('reports').iterdir()),
    input_bundle_read_only=bool(os.statvfs(bundle).f_flag & os.ST_RDONLY),
    separate_network_namespace=(os.stat('/proc/self/ns/net').st_ino != manifest['host_network_namespace']),
    bundle=str(bundle), snapshot_count=manifest['snapshot_count'],
    input_manifest_sha256=hashlib.sha256((bundle/'input-bindings.json').read_bytes()).hexdigest(),
)
assert all(evidence[k] for k in (
    'old_installations_hidden', 'old_bulk_data_hidden', 'repository_reports_hidden',
    'input_bundle_read_only', 'separate_network_namespace'))
with (output/'isolation.json').open('x') as stream:
    json.dump(evidence, stream, indent=2)
    stream.write('\n')
print(json.dumps(evidence), flush=True)
PY
exec env PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  "$3" -B tools/check_algo07v3_engine.py \
  --native-input "$1/native.json" --input-sha256 "$4" \
  --track-config "$1/config.json" --tle-root "$1/tle" \
  --screen-center 37.5 -122 --search-center 37.906 -122.545 \
  --scan-identities "$5" --output "$2/native"
ISOLATED
