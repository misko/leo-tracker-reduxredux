"""Read persisted execution authority through catalogue ports; no IQ access."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shlex
import time

ROOT = Path(__file__).resolve().parent
CASES = ('DS24-0010', 'DS24-0011')
BASE = Path('/srv/bulk/leo/research/ds25-20261024')


def main():
    began = time.monotonic()
    from leo.catalog import CatalogRepository, create_catalog_engine, create_session_factory
    from leo.processing.fast_scan import implementation_identity
    url = None
    for line in Path('/etc/leo/leo.env').read_text().splitlines():
        if line.startswith('LEO_DATABASE_URL='):
            values = shlex.split(line.split('=', 1)[1], comments=False)
            assert len(values) == 1
            url = values[0]
    assert url is not None, 'catalogue configuration unavailable'
    engine = create_catalog_engine(url)
    identity = implementation_identity()
    records = []
    try:
        catalog = CatalogRepository(create_session_factory(engine))
        for case in CASES:
            path = BASE/case/'tracking.json'
            content = path.read_bytes()
            tracking = json.loads(content)
            run = tracking['provenance']['run_id']
            info = catalog.run_execution_info(run)
            record = dict(case=case, tracking_path=str(path),
                          tracking_sha256=hashlib.sha256(content).hexdigest(),
                          run_id=run, run_state=catalog.run_state(run).value,
                          execution=asdict(info), runtime_identity=identity,
                          identity_matches=identity == (info.code_revision, info.environment_digest))
            assert record['identity_matches'] and record['run_state'] == 'succeeded'
            records.append(record)
    finally:
        engine.dispose()
    result = dict(records=records, metadata_seconds=time.monotonic()-began,
                  IQ_reads=0, detector_calls=0, source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
