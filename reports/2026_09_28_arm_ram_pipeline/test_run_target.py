import importlib.util
from pathlib import Path


def test_inventory_covers_rates_profiles_and_bounded_schedules():
    spec = importlib.util.spec_from_file_location('runner', Path(__file__).with_name('run_target.py'))
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
    rows = runner.phases()
    assert len({row['name'] for row in rows}) == len(rows) == 32
    for rate in runner.RATES:
        for method in ('D', 'goal40mag'):
            subset = [r for r in rows if r['rate_hz'] == rate and r['method'] == method]
            assert {(r['mode'], r['schedule_kind']) for r in subset} == {
                ('isolated', 'fixed-period'), ('concurrent', 'fixed-period'),
                ('concurrent', 'saved-arrival-offsets')}
            assert all(0 < r['jobs'] <= 120 for r in subset)
            assert all(r['jobs'] * 141 < 90000 for r in subset)
            assert sum(r['mode'] == 'isolated' for r in subset) == 1
            if rate == 2500000:
                assert sum(r['mode'] == 'concurrent' for r in subset) == 6
