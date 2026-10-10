"""Pure source loading and coarse admission; importing performs no model calls."""
import copy
import hashlib
import importlib.util
import math
import ast
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
PARENT=ROOT/'reports/2026_10_09_position_error_iter123'

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def evaluation_sources():
    """Static local transitive import closure; never import numerical modules."""
    src=ROOT/'src'
    pending=[ROOT/'reports/2026_10_09_position_error_iter107/report.py']
    found={}
    while pending:
        path=pending.pop()
        name=str(path.relative_to(ROOT))
        if name in found:continue
        found[name]=sha(path)
        tree=ast.parse(path.read_text())
        for node in ast.walk(tree):
            modules=[]
            if isinstance(node,ast.Import):modules=[a.name for a in node.names]
            if isinstance(node,ast.ImportFrom) and node.module:modules=[node.module]
            if isinstance(node,ast.ImportFrom) and node.level and path.is_relative_to(src):
                package=list(path.relative_to(src).parts[:-1])
                package=package[:len(package)-node.level+1]
                modules=['.'.join(package+((node.module or '').split('.') if node.module else []))]
                modules.extend('.'.join(package+((node.module or '').split('.') if node.module else [])+[alias.name]) for alias in node.names if alias.name!='*')
            for module in modules:
                if module.startswith('leo.'):
                    target=src/Path(*module.split('.')).with_suffix('.py')
                    if not target.exists():target=src/Path(*module.split('.'))/'__init__.py'
                    if not target.exists():
                        # from package import symbol may be an attribute rather
                        # than a module; the owning module is already bound.
                        if isinstance(node,ast.ImportFrom) and module!=modules[0]:continue
                        raise ValueError('unbound evaluation import '+module)
                    pending.append(target)
    return found

def adapter():
    spec=importlib.util.spec_from_file_location('retained123_for148',PARENT/'retained_adapter.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module

def admit(point,seed,fit,bank_count,arm,trace_score):
    original=adapter().admitted_original(point,seed,fit,bank_count)
    if arm not in ('fitted-c','zero-c'):raise ValueError('unknown discovery arm')
    if not math.isfinite(trace_score) or abs(fit['objective']-trace_score)>1e-6:raise ValueError('pinned native trace differs')
    if arm=='zero-c' and fit['vector'][6]!=0:raise ValueError('zero discovery c lock violated')
    if not isinstance(fit.get('converged'),bool):raise ValueError('missing coarse qualification')
    return copy.deepcopy(original)
