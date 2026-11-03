"""Research reconstruction is isolated and never described as a public replay."""

import json

import profile_algo07_research_snapshot as snapshot
import pytest

from leo.cli.algo07_profile import digest, verify


def test_research_snapshot_keeps_native_bytes_and_binds_relocated_paths(tmp_path, monkeypatch):
    research = tmp_path / 'research'
    recovery = research / 'case/recovery'
    native = recovery / 'snapshot/inference/SCAN'
    native.mkdir(parents=True)
    (native / 'observations.json').write_text('[]')
    terminal = recovery / 'terminal.json'
    terminal.write_text('{}')
    cohort = tmp_path / 'cohort'
    case = 'DS26-0006'
    z = dict(recovery_path=str(recovery), native_path=str(native),
             baseline_source=str(terminal), case=case)
    paths = {}
    for relative, value in [
        (f'inputs/{case}.json', z),
        (f'position/{case}/result.json', dict(decisions={'72h_30s': dict(status='fallback')})),
        (f'catalogues/{case}.json', dict(elements={})),
    ]:
        p = cohort / relative
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value))
        paths[str(p)] = digest(p)
    manifest = tmp_path / 'frozen.json'
    manifest.write_text(json.dumps(dict(files=[dict(path=p, sha256=s, case=case)
                                               for p, s in paths.items()])))
    kernel = tmp_path / 'kernel.py'
    kernel.write_text('# frozen reference\n')
    monkeypatch.setattr(snapshot, 'RESEARCH', research)
    output = tmp_path / 'private'
    snapshot.prepare(manifest, case, output, kernel)
    assert verify(output / 'frozen.json')['verified']
    moved = json.loads((output / 'input/inputs/SCAN.json').read_text())
    assert moved['case'] == 'SCAN'
    assert moved['native_path'] == str(output / 'input/case/recovery/snapshot/inference/SCAN')
    assert json.loads((output / 'source.json').read_text())['research_only']
    assert (native / 'observations.json').read_text() == '[]'
    (cohort / 'inputs' / (case + '.json')).write_text('{}')
    with pytest.raises(ValueError, match='frozen reference'):
        snapshot.prepare(manifest, case, tmp_path / 'rejected', kernel)
