import ast
import inspect
import re
from pathlib import Path

from probe_algo07v3_ordered_assembly import candidate

from leo.analysis import _ordered_assembly
from leo.analysis.localization_v3 import hierarchical


def test_owned_body_is_the_complete_training_qualified_prototype():
    _, _, source = candidate(_ordered_assembly.scatter)
    assert ast.dump(ast.parse(inspect.getsource(hierarchical.hierarchical_bound))) == (
        ast.dump(ast.parse(source)))


def test_native_code_matches_measured_external_extension():
    root = Path(__file__).resolve().parents[2]
    expected = (root / 'tools/algo07v3_ordered_scatter_module.c').read_text()
    expected = expected.replace('"algo07v3_ordered_scatter.c"', '"_ordered_scatter.c"')
    expected = expected.replace('_algo07v3_ordered_scatter', '_ordered_assembly')
    assert (root / 'src/leo/analysis/_ordered_assembly.c').read_text() == expected
    normalize = lambda text: re.sub(r'/\*.*?\*/|\s+', '', text, flags=re.S)  # noqa: E731
    assert normalize((root / 'src/leo/analysis/_ordered_scatter.c').read_text()) == normalize(
        (root / 'tools/algo07v3_ordered_scatter.c').read_text())


def test_build_retains_strict_float_flags_and_source_dependency():
    root = Path(__file__).resolve().parents[2]
    tree = ast.parse((root / 'setup.py').read_text())
    extension = next(n for n in ast.walk(tree) if isinstance(n, ast.Call)
                     and isinstance(n.func, ast.Name) and n.func.id == 'Extension'
                     and n.args[0].value == 'leo.analysis._ordered_assembly')
    keywords = {k.arg: k.value for k in extension.keywords}
    flags = ast.literal_eval(keywords['extra_compile_args'])
    assert '-fno-fast-math' in flags and '-ffp-contract=off' in flags
    assert ast.literal_eval(keywords['depends']) == ['src/leo/analysis/_ordered_scatter.c']
