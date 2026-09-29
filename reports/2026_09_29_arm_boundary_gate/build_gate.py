"""Build native low-margin boundary-refinement gates after replay screening."""
import importlib.util
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parent
PRIOR = ROOT.parent/'2026_09_29_arm_fused_pipeline'


def build_variant(label, threshold):
    root = ROOT/'variants'/label
    source = root/'sources'
    assert not source.exists()
    shutil.copytree(PRIOR/'sources-v4', source)
    path = source/'full_search.c'
    text = path.read_text()
    anchor = 'static int boundary_fallback_required(double residual)'
    helper = ('static int boundary_margin_allowed(double exact, double control)\n'
              '{\n    double margin=exact-control;\n'
              f'    return !isfinite(margin) || margin >= {threshold!r};\n}}\n\n')
    assert text.count(anchor) == 1
    text = text.replace(anchor, helper+anchor)
    old = 'if(boundary_fallback_required(score[2])) {'
    assert text.count(old) == 1
    text = text.replace(old, 'if(boundary_fallback_required(score[2]) && boundary_margin_allowed(score[0],score[1])) {')
    path.write_text(text)
    spec = importlib.util.spec_from_file_location('gate_builder', PRIOR/'build_v4.py')
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.ROOT = root
    builder.SOURCE = source
    records = {}
    for target in ['host', 'sanitizer', 'arm']:
        record = builder.build(target)
        receipt_path = root/record['receipt']
        receipt = json.loads(receipt_path.read_text())
        receipt.update(schema='arm-boundary-native-gate/v1', boundary_min_margin=threshold,
                       gate_scope='skip only residual-boundary refinement below initial margin; all windows/candidates retained')
        receipt_path.write_text(json.dumps(receipt, indent=2)+'\n')
        records[target] = {'receipt': str(receipt_path.relative_to(ROOT)), 'sha256': builder.sha(receipt_path)}
    return records


if __name__ == '__main__':
    records = {label: build_variant(label, threshold) for label, threshold in [('025', .025), ('100', .1)]}
    (ROOT/'gate-build-manifest.json').write_text(json.dumps(records, indent=2)+'\n')
