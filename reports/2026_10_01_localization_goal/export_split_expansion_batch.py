"""Bounded public read-only source-split exports for the frozen12development scans."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from regression_batch import digest, execute

HERE = Path(__file__).resolve().parent
RELEASE = Path('/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8')


def main():
    selection = HERE/'student-scale-expansion-v1-freeze.json'
    assert digest(selection) == selection.with_suffix('.sha256').read_text().strip()
    units = json.loads(selection.read_text())['ordered_units']
    directory = HERE/'source-split-expansion-v1'
    directory.mkdir(exist_ok=False)

    def run(unit):
        temporary = Path('/tmp')/('leo-split-expansion-'+unit+'-v1.json')
        assert not temporary.exists()
        command = ['sudo', '-n', '-u', 'leo', str(RELEASE/'.venv/bin/python'),
                   str(HERE/'export_split_expansion.py'), unit, '--output', str(temporary)]
        launch = execute(command, directory, unit, timeout_s=60.)
        output = directory/(unit+'.json')
        if launch['returncode'] == 0 and launch['within_budget']:
            reported = json.loads((directory/(unit+'.stdout.txt')).read_text())
            assert digest(temporary) == reported['sha256']
            with output.open('xb') as stream:
                stream.write(temporary.read_bytes())
            output.with_suffix('.sha256').write_text(digest(output)+'\n')
        launch['receipt_sha256'] = digest(output) if output.exists() else None
        (directory/(unit+'.launch.json')).write_text(json.dumps(launch, indent=2))
        print(json.dumps(dict(unit=unit, returncode=launch['returncode'],
                              seconds=launch['elapsed_seconds'])), flush=True)
        return launch

    with ThreadPoolExecutor(max_workers=2) as pool:
        launches = list(pool.map(run, units))
    result = dict(ordered_units=units, launches=launches,
                  selection_sha256=digest(selection), batch_source_sha256=digest(__file__))
    (directory/'batch.json').write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
