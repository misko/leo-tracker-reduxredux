"""Retain failed/successful package-check evidence, not IQ, ELF or credentials."""
from pathlib import Path
import hashlib
import json
import shutil
import subprocess
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parent
repo = Path('/home/mouse9911/gits/leo-tracker-arm-presence')
destination = repo/'reports/evidence/2026_09_08_scanner_glrt_package_arm'
destination.mkdir(parents=True,exist_ok=False)
index = {}
def retain(source,name):
    target = destination/name
    target.parent.mkdir(parents=True,exist_ok=True)
    shutil.copyfile(source,target)
    expected = hashlib.sha256(source.read_bytes()).hexdigest()
    assert hashlib.sha256(target.read_bytes()).hexdigest() == expected
    index[name] = dict(bytes=source.stat().st_size,sha256=expected)

for path in sorted(root.rglob('*')):
    if path.is_file() and path.suffix in {'.py','.json','.jsonl','.xml'}:
        assert 'credentials' not in path.parts
        retain(path,str(path.relative_to(root)))
for rate in (2500000,5000000):
    source = Path('/tmp/leo-presence-arm-profile.UuBXXp/replay-300s')/f'{rate}-combined.manifest.json'
    retain(source,f'references/{rate}.manifest.json')

# The explicit target build command is unchanged. After execution the helper's
# default (non-package) RPATH behavior was restored for backwards compatibility.
# Retain the exact helper version identified by the build receipt, not a merely
# similar later source: reconstruct that one substitution and verify SHA-256.
current = (repo/'tools/qualify_scanner_glrt_sdk.py').read_text()
new = '''        (
            f"-Wl,--disable-new-dtags,-rpath,{runtime_rpath}"
            if runtime_rpath is not None
            else "-Wl,-rpath,$ORIGIN"
        ),'''
old = '''        f"-Wl,--disable-new-dtags,-rpath,{runtime_rpath or '$ORIGIN'}",'''
assert current.count(new) == 1
helper = current.replace(new,old).encode()
build = json.loads((root/'retry/parent/sdk-replay.build.json').read_bytes())
expected = build['sources_sha256']['tools/qualify_scanner_glrt_sdk.py']
assert hashlib.sha256(helper).hexdigest() == expected
target = destination/'build-source/qualify_scanner_glrt_sdk.py'
target.parent.mkdir()
target.write_bytes(helper)
index[str(target.relative_to(destination))] = dict(bytes=len(helper),sha256=expected)
tests = {}
for label,name in [('leo','regression.xml'),('ppu','ppu-regression.xml')]:
    suites = ET.parse(root/name).getroot().findall('testsuite')
    tests[label] = {key:sum(int(s.attrib[key]) for s in suites)
                   for key in ('tests','errors','failures','skipped')}
end = json.loads((root/'retry/end.json').read_bytes())
assert end['scratch_retained'] is None and not end['daemon_retained']
assert not end['bundle_retained'] and not end['cleanup_errors'] and end['credentials_removed']
summary = json.loads((root/'retry/summary.json').read_bytes())
assert len(summary['runs']) == 4 and sum(r['results'] for r in summary['runs']) == 278
assert all(r['verified'] and r['callback_over_nominal_period'] == 0 for r in summary['runs'])
revisions = {name:subprocess.check_output(['git','-C',str(path),'rev-parse','HEAD'],text=True).strip()
             for name,path in [('leo',repo),('ppu',repo.parent/'pluto-plus-utils-arm-glrt-host'),
                              ('libiio',repo.parent/'libiio-arm-glrt-frame-integration')]}
record = dict(schema='org.leo.research.scanner-glrt-package-arm-evidence/v1',artifacts=index,
    revisions=revisions,tests=tests,verified_results=278,live_rf=False,goal_complete=False,
    scope='Target loader/version and saved-IQ SDK replay; no IIO refill/listener/IRQ-load/duty proof',
    initial_failure='Optional stat applet absent; retained task-created files recovered after exact checks',
    final_cleanup=end)
with (destination/'index.json').open('x') as stream:
    json.dump(record,stream,indent=2)
    stream.write('\n')
print(json.dumps(dict(artifacts=len(index),bytes=sum(v['bytes'] for v in index.values()),
                     tests=tests,revisions=revisions,verified_results=278),indent=2))
