#!/bin/sh
# Private inputs and network for the external bounded-process derivative experiment.
set -eu
test "$#" -eq 4 || exit 2
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
manifest = json.loads((bundle/'input-bindings.json').read_bytes())
for name, sha in manifest['files'].items():
    path = (bundle/name).resolve()
    assert path.is_relative_to(bundle.resolve())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
checks = dict(old_installations_hidden=not list(Path('/opt').iterdir()),
              old_bulk_data_hidden=not list(Path('/srv/bulk/leo').iterdir()),
              reports_hidden=not list(Path('reports').iterdir()),
              inputs_read_only=bool(os.statvfs(bundle).f_flag & os.ST_RDONLY),
              isolated_network=os.stat('/proc/self/ns/net').st_ino != manifest['host_network_namespace'])
assert all(checks.values())
with (output/'isolation.json').open('x') as stream:
    json.dump(dict(checks=checks, input_manifest_sha256=hashlib.sha256(
        (bundle/'input-bindings.json').read_bytes()).hexdigest()), stream, indent=2)
    stream.write('\n')
PY
exec taskset -c 0,1,2 env PYTHONPATH=src:tools OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  "$3" -B tools/probe_algo07v3_native_idle_process.py --launch "$2" --variant "$4"
ISOLATED
