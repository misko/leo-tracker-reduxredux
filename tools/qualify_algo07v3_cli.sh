#!/bin/sh
# External evidence harness; not a runtime dependency of the owned CLI.
# Run from the checkout root. Output parent must be a fresh, existing directory.
set -eu
test "$#" -eq 6 || {
  echo 'usage: BUNDLE OUTPUT_PARENT PYTHON REQUEST run|resume TIMEOUT' >&2
  exit 2
}
case "$5" in run|resume) ;; *) exit 2 ;; esac
exec unshare --mount --net --propagation private sh -s -- "$@" <<'ISOLATED'
set -eu
mount --bind "$1" "$1"
mount -o remount,bind,ro "$1"
mount -t tmpfs -o ro,size=1m tmpfs /opt
mount -t tmpfs -o ro,size=1m tmpfs /srv/bulk/leo
mount -t tmpfs -o ro,size=1m tmpfs reports
"$3" -B - "$1" "$2" "$5" <<'PY'
import hashlib, json, os, sys
from pathlib import Path
bundle, output = map(Path, sys.argv[1:3])
manifest = json.loads((bundle/'input-bindings.json').read_bytes())
for name, sha in manifest['files'].items():
    path = (bundle/name).resolve()
    assert path.is_relative_to(bundle.resolve())
    assert hashlib.sha256(path.read_bytes()).hexdigest() == sha
checks = dict(
    old_installations_hidden=not list(Path('/opt').iterdir()),
    old_bulk_data_hidden=not list(Path('/srv/bulk/leo').iterdir()),
    repository_reports_hidden=not list(Path('reports').iterdir()),
    input_bundle_read_only=bool(os.statvfs(bundle).f_flag & os.ST_RDONLY),
    separate_network_namespace=(os.stat('/proc/self/ns/net').st_ino != manifest['host_network_namespace']),
)
assert all(checks.values())
evidence = dict(checks=checks, action=sys.argv[3],
    input_manifest_sha256=hashlib.sha256((bundle/'input-bindings.json').read_bytes()).hexdigest())
with (output/'isolation.json').open('x') as stream:
    json.dump(evidence, stream, indent=2)
    stream.write('\n')
PY
if test "$5" = resume; then
  mount -t tmpfs -o ro,size=1m tmpfs "$1"
  test -z "$(ls -A "$1")"
  echo 'Resume: original native input, configuration and TLE bundle hidden.'
fi
exec env PYTHONPATH=src OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 \
  "$3" -B -m leo.cli.algo07v3 "$5" --request "$4" \
  --work-dir "$2/attempt" --timeout "$6"
ISOLATED
