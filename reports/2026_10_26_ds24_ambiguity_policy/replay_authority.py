"""Inspect a sealed run through public read ports; never print credentials."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shlex
import time


def main():
    started = time.monotonic()
    from leo.catalog import CatalogRepository, create_catalog_engine, create_session_factory
    from leo.processing.fast_scan import implementation_identity
    from leo.scanner import fast_scan_analysis, fast_scan_detector
    from leo.storage import short_window
    run_id = 'fast-ee3becaf0eacfe1efc251c6a9dc8dc56'
    url = None
    for line in Path('/etc/leo/leo.env').read_text().splitlines():
        if line.startswith('LEO_DATABASE_URL='):
            parts = shlex.split(line.split('=', 1)[1], comments=False)
            assert len(parts) == 1
            url = parts[0]
    assert url is not None, 'database configuration unavailable'
    engine = create_catalog_engine(url)
    try:
        catalog = CatalogRepository(create_session_factory(engine))
        info = catalog.run_execution_info(run_id)
        state = catalog.run_state(run_id)
        result = {'run_id': run_id, 'run_state': state.value,
                  'execution': asdict(info)}
    finally:
        engine.dispose()
    code, environment = implementation_identity()
    result['current_deployed_implementation_digest'] = code
    result['current_deployed_environment_digest'] = environment
    result['matches_persisted_implementation'] = code == info.code_revision
    result['matches_persisted_environment'] = environment == info.environment_digest
    result['selected_source_files'] = {
        str(Path(module.__file__).resolve()): hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()
        for module in (fast_scan_analysis, fast_scan_detector, short_window)
    }
    result.update(IQ_read=False, detector_run=False, elapsed_s=time.monotonic()-started)
    print(json.dumps(result, indent=2, default=str))


if __name__ == '__main__':
    main()
