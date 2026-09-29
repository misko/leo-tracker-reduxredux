"""Record scores before residual-boundary refinement without changing search."""
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT.parent / '2026_09_29_arm_fused_pipeline'


def replace_once(path, old, new):
    source = path.read_text()
    assert source.count(old) == 1, (path, old)
    path.write_text(source.replace(old, new))


def prepare():
    source = ROOT / 'sources'
    assert not source.exists()
    shutil.copytree(PRIOR / 'sources-v4', source)
    replace_once(source/'full_search.h', '    double coarse_cfo_hz;',
                 '    double pre_exact, pre_control, pre_acquired, pre_tracking;\n    double coarse_cfo_hz;')
    replace_once(source/'full_search.c', '#if LEO_FULL_REFINEMENT_MODE == 2\n        if(boundary_fallback_required(score[2])) {',
                 '        dst->pre_exact=score[0]; dst->pre_control=score[1];\n'
                 '        dst->pre_acquired=dst->candidate.acquired_cfo_hz;\n'
                 '        dst->pre_tracking=dst->candidate.tracking_cfo_hz;\n'
                 '#if LEO_FULL_REFINEMENT_MODE == 2\n        if(boundary_fallback_required(score[2])) {')
    replace_once(source/'fused_probe.c',
                 '        if(LEO_FULL_REFINEMENT_MODE==1)',
                 '        printf("null,\\\"pre_exact\\\":%.17g,\\\"pre_control\\\":%.17g,\\\"pre_acquired\\\":%.17g,\\\"pre_tracking\\\":%.17g,\\\"fine_cfo_hz\\\":",v->pre_exact,v->pre_control,v->pre_acquired,v->pre_tracking);\n'
                 '        if(LEO_FULL_REFINEMENT_MODE==1)')
    # The preceding emitter ended with fine_cfo_hz:. Rename that first key
    # rather than publish duplicate keys when inserting the diagnostic values.
    replace_once(source/'fused_probe.c', '\\\"fine_cfo_hz\\\":",i?', '\\\"diagnostic_placeholder\\\":",i?')
    return source


if __name__ == '__main__':
    spec = importlib.util.spec_from_file_location('fused_build', PRIOR/'build_v4.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.ROOT = ROOT
    builder.SOURCE = prepare()
    record = builder.build('host')
    receipt_path = ROOT / record['receipt']
    receipt = json.loads(receipt_path.read_text())
    receipt['schema'] = 'arm-boundary-diagnostics-build/v1'
    receipt['experiment'] = 'Record pre-fallback scores; no decision or search changes'
    receipt_path.write_text(json.dumps(receipt, indent=2)+'\n')
