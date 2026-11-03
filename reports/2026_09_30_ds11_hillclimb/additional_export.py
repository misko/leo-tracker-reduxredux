"""Read-only derived-input export for the frozen additional DS11 sample."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PYTHON = '/opt/leo-tracker/releases/17484895464c225ebba977487aa36d3d81658bd8/.venv/bin/python'


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def export_one(index):
    sys.path.insert(0, str(ROOT/'tools'))
    import ds7_export_baseline as exporter
    import ds7_fast_baseline_adapter as baseline
    plan = json.loads((HERE/'additional-plan.json').read_text())
    for name, expected in plan['source_sha256'].items():
        assert digest(name) == expected
    row = plan['captures'][index]
    folder = HERE/'additional'/'exports'/f'{index:02d}'
    folder.mkdir(parents=True, exist_ok=True)
    observation, bank = folder/'observations.json', folder/'banks/manifest.json'
    if observation.exists() or bank.exists():
        raise FileExistsError('Preserve partial exports; explicit recovery required')
    document = exporter.export(row, observation, Path('/srv/bulk/leo'), Path('/var/lib/leo/tle'))
    evidence = HERE.parent/'2026_09_30_ds11_post_ds10/local/analysis'/f"{row['session_id']}.json"
    assert 'sha256:'+digest(evidence) == row['analysis_evidence_sha256']
    assert document['analysis_manifest_sha256'] == json.loads(evidence.read_text())['glrt']['metrics_manifest_sha256']
    exporter.export_banks(row, observation, folder/'banks', Path('/srv/bulk/leo'), Path('/var/lib/leo/tle'))
    paths = [observation, bank, folder/'banks/banks.npz']
    entry = dict(session_id=row['session_id'], manifest_sha256=row['manifest_sha256'],
                 artifacts=[dict(kind='observations' if i==0 else 'candidates', path=str(p),
                                 sha256='sha256:'+digest(p)) for i,p in enumerate(paths)])
    docs = baseline.load_documents(dict(config=plan['config'], inputs=[entry]))
    assert docs[0]['sample_rate_hz'] == row['sample_rate_hz']
    bank_metadata = json.loads(bank.read_text())
    assert all(source['collected_utc_ns'] < docs[0]['start_utc_ns']-505_000_000_000
               for source in bank_metadata['provider_sources'])
    with (folder/'validated.json').open('x') as stream:
        json.dump(dict(index=index, input=entry, tracks=len(docs[0]['tracks']),
                       source_sha256=digest(__file__)), stream, indent=2)


def batch():
    folder = HERE/'additional'
    folder.mkdir(exist_ok=True)
    count = json.loads((HERE/'additional-plan.json').read_text())['count']
    for index in range(count):
        receipt = folder/f'export_{index:02d}.receipt.json'
        log = folder/f'export_{index:02d}.log'
        if receipt.exists():
            continue
        if log.exists():
            raise RuntimeError('Audit the unreceipted process before continuing')
        command = ['sudo','-n','env','OPENBLAS_NUM_THREADS=1','OMP_NUM_THREADS=1',
                   'timeout','--kill-after=5s','180s','nice','-n','19',PYTHON,
                   str(Path(__file__).resolve()),'one',str(index)]
        start = time.monotonic()
        with log.open('x') as stream:
            result = subprocess.run(command, stdout=stream, stderr=subprocess.STDOUT)
        row = dict(index=index, exit_code=result.returncode, wall_s=time.monotonic()-start,
                   command=command, source_sha256=digest(__file__))
        with receipt.open('x') as stream:
            json.dump(row, stream, indent=2)
        print(json.dumps(row), flush=True)


if __name__ == '__main__':
    if sys.argv[1] == 'one':
        export_one(int(sys.argv[2]))
    elif sys.argv[1] == 'batch':
        batch()
    else:
        raise ValueError(sys.argv[1])
