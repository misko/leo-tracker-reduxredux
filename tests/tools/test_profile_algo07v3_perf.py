"""Pure receipt validation; actual perf/namespace requirements are explicit in the tool."""

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from profile_algo07v3_perf import EVENTS, compare_unchanged, parse_counters, record


def rows():
    return [dict(event=e, unit='msec' if e=='task-clock' else '',
                 **{'counter-value':str(v), 'pcnt-running':100})
            for e,v in zip(EVENTS, [5e9, 2.5e9, 1000], strict=True)]


def save(tmp_path, values):
    path = tmp_path/'counts.jsonl'
    path.write_text(''.join(json.dumps(v)+'\n' for v in values))
    return path


def test_scope_units_and_derived_metrics(tmp_path):
    result = parse_counters(save(tmp_path, rows()))
    assert result['cpu_seconds'] == 1
    assert result['cycles_per_instruction'] == 2
    assert result['average_active_ghz'] == 5


@pytest.mark.parametrize('field,value', [('counter-value','<not counted>'),
    ('counter-value', 'NaN'), ('counter-value', -1), ('pcnt-running', 50),
    ('unit','seconds'), ('event','cpu_atom/cycles/')])
def test_unusable_counters_rejected(tmp_path, field, value):
    values = rows()
    values[0][field] = value
    with pytest.raises(ValueError):
        parse_counters(save(tmp_path, values))


@pytest.mark.parametrize('variant', ['missing', 'duplicate'])
def test_event_set_is_exact(tmp_path, variant):
    values = rows()
    values = values[:-1] if variant=='missing' else values + values[:1]
    with pytest.raises(ValueError):
        parse_counters(save(tmp_path, values))


def test_perf_is_pinned_before_counter_creation(tmp_path, monkeypatch):
    commands = []
    def run(command, **kwargs):
        commands.append(command)
        path = Path(command[command.index('-o')+1])
        path.write_text(''.join(json.dumps(v)+'\n' for v in rows()))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr('profile_algo07v3_perf.subprocess.run', run)
    result = record(tmp_path, 'test', ['/bin/true'], inherit=False, cpus='0,1,2')
    assert commands[0][:7] == ['sudo', '-n', 'taskset', '-c', '0,1,2', 'perf', 'stat']
    assert commands[0][-3:] == ['--no-inherit', '--', '/bin/true']
    assert result['returncode'] == 0 and result['counters']['cpu_seconds'] == 1


def test_comparison_requires_no_runtime_source_changes(monkeypatch):
    seen = []
    def compare(args):
        seen.append(args)
        return {'exact_owned_science_and_artifacts':True}
    monkeypatch.setattr('compare_algo07v3_runs.compare', compare)
    assert compare_unchanged('a', 'b', 'c', 'd')['exact_owned_science_and_artifacts']
    assert seen[0].changed_module == [] and seen[0].added_module == []
    assert seen[0].baseline_request == 'a' and seen[0].candidate_timing == 'd'
