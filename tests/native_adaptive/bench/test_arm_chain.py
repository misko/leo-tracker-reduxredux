import importlib.util
from pathlib import Path
import subprocess

import pytest

spec = importlib.util.spec_from_file_location('arm_chain',
    Path(__file__).resolve().parents[3] / 'tools/render_arm_chain.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def plan():
    return {'output_directory': '/mnt/glrtbench/trial/results', 'stages': [
        {'name': 'first', 'argv': ['/mnt/glrtbench/tool', 'space and $dollar'], 'timeout_s': 10}]}


def test_quotes_arguments_and_refuses_overwrite():
    script = module.render(plan(), {'/mnt/glrtbench/tool': 'digest'})
    assert "'space and $dollar'" in script
    assert 'set -eu\nset -C' in script
    assert 'mkdir /mnt/glrtbench/trial/results' in script and 'mkdir -p' not in script
    subprocess.run(['sh', '-n'], input=script, text=True, check=True)


@pytest.mark.parametrize('mutation', ['timeout', 'duplicate', 'unpinned', 'path', 'nul'])
def test_invalid_plan(mutation):
    p = plan()
    if mutation == 'timeout': p['stages'][0]['timeout_s'] = 601
    if mutation == 'duplicate': p['stages'] *= 2
    if mutation == 'unpinned': p['stages'][0]['argv'][0] = '/bin/other'
    if mutation == 'path': p['output_directory'] = '/mnt/glrtbench/../other'
    if mutation == 'nul': p['stages'][0]['argv'].append('bad\0argument')
    with pytest.raises(ValueError): module.render(p, {'/mnt/glrtbench/tool': 'digest'})


def test_failed_stage_stops_dependents_and_publication(tmp_path):
    p = plan()
    p['stages'] = [
        {'name': 'failure', 'argv': ['/bin/false'], 'timeout_s': 10},
        {'name': 'dependent', 'argv': ['/bin/echo', 'must not publish'], 'timeout_s': 10}]
    script = module.render(p, {'/bin/false': 'x', '/bin/echo': 'y'})
    helper = tmp_path / 'measure'
    helper.write_text('#!/bin/sh\nshift\nexec "$@"\n')
    helper.chmod(0o755)
    script = script.replace('/mnt/glrtbench/native-adaptive/current/measure-run', str(helper))
    script = script.replace(p['output_directory'], str(tmp_path / 'results'))
    result = subprocess.run(['sh'], input=script, capture_output=True, text=True)
    assert result.returncode != 0 and not result.stdout
    assert not (tmp_path / 'results/dependent.stdout').exists()
