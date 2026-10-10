"""Lean sealed151 continuation adapter; no new discovery or warm endpoints."""
import importlib.util
import copy
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
PRIOR = HERE.parent / '2026_10_10_position_error_iter151'
PARENT = HERE.parent / '2026_10_09_position_error_iter129'
POLICY = dict(conditions=['control', 'repair'], discovery_policies=['native', 'zero'],
              final_arms=['zero-c', 'fitted-c'], regions=3, local_radius_km=25.,
              continuation_slices=2, slice_seconds=500, workers=2, threads=1,
              own_arm_repair=dict(maximum_seconds=5, maximum_iterations=200,
                                  slope_half_width_hz_s=60, fixed_position=True),
              own_arm_newton=False, downstream='unchanged150', discovery='sealed151')


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def continuation_source(source, transform):
    source = transform.continuation_source(source)
    # Only frozen discovery uses the old digest; all new claims/stages use154.
    source = source.replace('discovery["protocol_sha256"] != digest',
                            'discovery["protocol_sha256"] != plan["discovery_digest"]')
    source = source.replace('expected["protocol_sha256"] != digest',
                            'expected["protocol_sha256"] != plan["discovery_digest"]')
    source = source.replace('value["protocol_sha256"] != digest',
                            'value["protocol_sha256"] != plan["discovery_digest"]')
    for old in ('discovery["protocol_sha256"] != digest',
                'expected["protocol_sha256"] != digest',
                'value["protocol_sha256"] != digest'):
        if old in source:
            raise ValueError('untransformed discovery binding')
    return source


def continue_slice(plan, member, branch, condition, output, loader, driver, adapter,
                   *, recovery_factory=None, **options):
    if condition not in POLICY['conditions'] or branch not in POLICY['discovery_policies']:
        raise ValueError('unknown154 condition/branch')
    previous = load('ports151_for154', PRIOR / 'ports.py')
    transition = load('transition150_for154', HERE.parent / '2026_10_10_position_error_iter150/transition.py')
    if recovery_factory is None:
        if condition == 'control':
            recovery_factory = transition.recovery_port
        else:
            recording = load('adapter154', HERE / 'adapter.py')
            recovery_factory = lambda backend, arm: recording.recovery_port(backend, arm, transition)
    source = (previous.PARENT / 'continuation.py').read_text()
    for token in ('discovery["protocol_sha256"] != digest',
                  'expected["protocol_sha256"] != digest',
                  'value["protocol_sha256"] != digest'):
        if source.count(token) != 1:
            raise ValueError('parent binding source changed')
    namespace = {'__name__': 'continue129_for154', 'RECOVERY_PORT': recovery_factory}
    exec(compile(continuation_source(source, previous), str(previous.PARENT / 'continuation.py'), 'exec'), namespace)
    search = ROOT / member['sealed_search_path']
    execution = copy.deepcopy(plan)
    execution['execution_condition'] = condition
    return namespace['continue_slice'](execution, member, branch, output, search,
                                       loader, driver, adapter, **options)
