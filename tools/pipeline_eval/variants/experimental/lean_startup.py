"""Start an isolated ALGO08 process with lazy package reexports."""

import ast
import runpy
import sys
from importlib import import_module
from importlib.abc import Loader, MetaPathFinder
from importlib.machinery import PathFinder

FACADES = frozenset({
    "leo.analysis.research", "leo.analysis.standard", "leo.analysis.starlink",
    "leo.contracts", "leo.operations", "leo.scanner", "leo.storage",
})


def reexports(source):
    """Recognize only docstrings, absolute from-imports and a literal __all__."""
    tree = ast.parse(source)
    doc = ast.get_docstring(tree, clean=False)
    routes, names = {}, None
    for i, statement in enumerate(tree.body):
        if i == 0 and doc is not None:
            continue
        if isinstance(statement, ast.ImportFrom) and statement.level == 0:
            for ref in statement.names:
                if ref.name == "*":
                    return None
                routes[ref.asname or ref.name] = statement.module, ref.name
        elif (isinstance(statement, ast.Assign) and len(statement.targets) == 1
              and isinstance(statement.targets[0], ast.Name)
              and statement.targets[0].id == "__all__" and names is None
              and isinstance(statement.value, (ast.List, ast.Tuple))
              and all(isinstance(value, ast.Constant) and isinstance(value.value, str)
                      for value in statement.value.elts)):
            names = ast.literal_eval(statement.value)
        else:
            return None
    return (doc, names, routes) if names is not None and set(names) <= routes.keys() else None


class ReexportLoader(Loader):
    def __init__(self, exports):
        self.exports = exports

    def exec_module(self, module):
        module.__doc__, module.__all__, routes = self.exports

        def lookup(name):
            if name not in routes:
                raise AttributeError(f"module {module.__name__!r} has no attribute {name!r}")
            source, export = routes[name]
            value = getattr(import_module(source), export)
            vars(module)[name] = value
            return value

        module.__getattr__ = lookup
        module.__dir__ = lambda: sorted(vars(module).keys() | routes.keys())


class ReexportFinder(MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if fullname not in FACADES:
            return None
        spec = PathFinder.find_spec(fullname, path, target)
        loader = None if spec is None else spec.loader
        if loader is None or not hasattr(loader, "get_source"):
            return None
        source = loader.get_source(fullname)
        exports = reexports(source) if source is not None else None
        if exports is None:
            return None
        spec.loader = ReexportLoader(exports)
        return spec


def install():
    """Install before any of the selected facades has been imported."""
    if FACADES & sys.modules.keys():
        raise RuntimeError("lazy reexports must start in a fresh ALGO08 process")
    sys.meta_path.insert(0, ReexportFinder())


if __name__ == "__main__":
    install()
    entry = "tools.pipeline_eval.qualification.experimental_publication"
    runpy.run_module(entry, run_name="__main__")
